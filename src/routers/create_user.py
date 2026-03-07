from datetime import timedelta, datetime, timezone, date
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from starlette import status
from database.database import SessionLocal
from models import Users
from database.database_space import store_user_keys_in_supabase
import os
import base64
# NOTE: cryptography imports are intentionally deferred to inside create_user()
# to prevent OpenSSL C-level initialization at module load time,
# which crashes the Cloudflare Workers / Pyodide WASM validation sandbox.

router = APIRouter(
    prefix='/create_user',
    tags=['user']
)

# JWT configuration (Will dynamically pull from Request Env during runtime too!)
ALGORITHM = 'HS256'

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class CreateUserRequest(BaseModel):
    username: str
    email: str
    phone: Optional[str] = None
    first_name: str
    last_name: str
    password: str
    language: str
    role: str
    manager_id: Optional[int] = None
    hire_date: date
    relive_date: Optional[date] = None
    emp_type: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    phone: Optional[str] = None
    first_name: str
    last_name: str
    language: str
    role: str
    manager_id: Optional[int] = None
    is_active: Optional[bool] = None
    hire_date: date
    relive_date: Optional[date] = None
    emp_type: Optional[str] = None
    created_dt: date

    model_config = ConfigDict(from_attributes=True)

db_dependency = Annotated[Session, Depends(get_db)]

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(req: Request, user_req: CreateUserRequest, db: db_dependency):
    # Lazy imports — deferred to request time to avoid OpenSSL init crash in Pyodide WASM
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization

    # Safely extract Cloudflare Worker `env` bindings if running in production
    cf_env = req.scope.get("env")
    
    async def get_secret(key: str, default: str = None) -> str:
        if cf_env and hasattr(cf_env, key):
            secret_binding = getattr(cf_env, key)
            # Cloudflare Secrets Store binding — has an async .get() method
            if callable(getattr(secret_binding, "get", None)):
                value = await secret_binding.get()
                if value:
                    return value
            # Standard Wrangler Secret — plain string attribute directly
            elif isinstance(secret_binding, str):
                return secret_binding
        # Fallback to local .env / OS environment
        return os.getenv(key, default)

    # FIX #6 — Duplicate user check BEFORE any crypto to prevent CPU abuse
    try:
        existing_user = db.query(Users).filter(
            (Users.username == user_req.username) | (Users.email == user_req.email)
        ).first()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[D1 DB Error] Failed to query users table: {e}"
        )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists."
        )

    # FIX #4 — Raise hard 500 if critical secrets are missing (no weak fallbacks)
    argon2_pepper_str = await get_secret("ARGON2_SECRET_PEPPER", None)
    argon2_ad_str = await get_secret("ARGON2_ASSOCIATED_DATA", None)
    jwt_secret = await get_secret("JWT_SECRET_KEY", None)
    if not argon2_pepper_str or not argon2_ad_str or not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: required secrets are missing."
        )
    argon2_pepper = argon2_pepper_str.encode('utf-8')
    argon2_ad = argon2_ad_str.encode('utf-8')

    # FIX #5 — Declare sensitive vars upfront so the finally block can always wipe them
    master_key = None
    private_key = None
    private_bytes = None

    try:
        # 1. Key Derivation: Derive 32-byte 'Master Key' using Argon2id
        salt = user_req.email.encode('utf-8')
        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=2,
            lanes=4,
            memory_cost=65536,
            ad=argon2_ad,
            secret=argon2_pepper,
        )
        master_key = kdf.derive(user_req.password.encode('utf-8'))

        # 2. Key Generation: Generate asymmetric Ed25519 key pair
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )

        # 3. Encryption: Encrypt the Private Key using derived Master Key with AES-GCM
        aesgcm = AESGCM(master_key)
        nonce = os.urandom(12)
        encrypted_private_key = aesgcm.encrypt(nonce, private_bytes, None)

        # Encode bytes to base64 for storing in database
        b64_public_key = base64.b64encode(public_bytes).decode('utf-8')
        b64_encrypted_private_key = base64.b64encode(encrypted_private_key).decode('utf-8')
        b64_nonce = base64.b64encode(nonce).decode('utf-8')

        # 4. Storage Logic — Store Public Key and user metadata in D1
        user_dict = user_req.model_dump(exclude={'password'})
        user_model = Users(**user_dict)
        user_model.public_key = b64_public_key
        user_model.is_active = user_model.relive_date is None
        user_model.created_dt = datetime.now(timezone.utc).date()

        db.add(user_model)
        try:
            db.flush()  # Flush to get the auto-increment user ID without committing yet

            # Store Encrypted Private Key blob and nonce in Supabase (DB2)
            # If this fails, we rollback the D1 transaction below to prevent an orphaned user row
            await store_user_keys_in_supabase(
                user_id=user_model.id,
                encrypted_private_key=b64_encrypted_private_key,
                nonce=b64_nonce
            )

            # Only commit D1 if Supabase insert succeeded — both DBs are now in sync
            db.commit()
        except Exception as e:
            db.rollback()  # Undo the D1 flush so no orphaned user row is left behind
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User creation failed: key vault storage error. No data was saved. ({e})"
            )

        return user_model

    finally:
        # FIX #5 — Always wipe sensitive values from memory, even if an exception occurred
        if hasattr(user_req, 'password') and user_req.password:
            pwd_len = len(user_req.password)
            user_req.password = '\x00' * pwd_len
        if master_key:
            del master_key
        if private_key:
            del private_key
        if private_bytes:
            del private_bytes
