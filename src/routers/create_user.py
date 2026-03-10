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
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from dependencies import get_current_user
from pydantic.networks import EmailStr

router = APIRouter(
    prefix='/create_user',
    tags=['User Management']
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
    """
    Payload for registering a new Agrinow user.
    A password is required but is never stored — it is stretched into a master key via Argon2id.
    """
    username:   str            = Field(..., description="Unique username.", examples=["john_doe"])
    email:      EmailStr            = Field(..., description="Unique email address. Used as the Argon2id salt.", examples=["john@example.com"])
    phone:      Optional[str]  = Field(None, description="Optional phone number.", examples=["+91 98765 43210"])
    first_name: str            = Field(..., description="User's first name.", examples=["John"])
    last_name:  str            = Field(..., description="User's last name.", examples=["Doe"])
    password:   str            = Field(..., description="Plaintext password. Stretched via Argon2id; never stored.", examples=["MySecureP@ssw0rd"])
    language:   str            = Field(..., description="Preferred language code (e.g. 'en', 'hi', 'kn').", examples=["en"])
    role:       str            = Field(..., description="User role: admin | manager | farmer | agent | analyst.", examples=["farmer"])
    manager_id: Optional[int]  = Field(None, description="ID of the user's direct manager, if any.", examples=[5])
    hire_date:  date           = Field(..., description="Date the user was hired (YYYY-MM-DD).", examples=["2024-01-15"])
    relive_date: Optional[date]= Field(None, description="Date the user was relieved. If set, account is marked inactive.", examples=["2025-06-30"])
    emp_type:   Optional[str]  = Field(None, description="Employment type: full_time | part_time | contract | intern.", examples=["full_time"])

class UserResponse(BaseModel):
    """
    Public user profile returned after successful registration.
    Sensitive fields (password, private key, master key) are excluded.
    """
    id:          int           = Field(description="Auto-assigned user ID.")
    username:    str           = Field(description="Unique username.")
    email:       EmailStr      = Field(description="Registered email address.")
    phone:       Optional[str] = Field(None, description="Phone number, if provided.")
    first_name:  str           = Field(description="First name.")
    last_name:   str           = Field(description="Last name.")
    language:    str           = Field(description="Preferred language code.")
    role:        str           = Field(description="Assigned role.")
    manager_id:  Optional[int] = Field(None, description="Manager's user ID, if set.")
    is_active:   Optional[bool]= Field(None, description="True if the user has no relieve date.")
    hire_date:   date          = Field(description="Hire date.")
    relive_date: Optional[date]= Field(None, description="Relieve date, if set.")
    emp_type:    Optional[str] = Field(None, description="Employment type.")
    created_dt:  date          = Field(description="UTC date the account was created.")

    model_config = ConfigDict(from_attributes=True)

db_dependency = Annotated[Session, Depends(get_db)]


def role_checker(allowed_roles: list):
    def check(user: dict = Depends(get_current_user)):
        if user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Operation not permitted"
            )
        return user
    return check

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    summary="Register a new user",
    description=(
        "Creates a new Agrinow user with a zero-knowledge key scheme:\n\n"
        "1. Check for duplicate username/email.\n"
        "2. Derive a 32-byte **master key** from the password using Argon2id "
        "(`salt=email`, `secret=ARGON2_SECRET_PEPPER`, `ad=ARGON2_ASSOCIATED_DATA`).\n"
        "3. Generate an **Ed25519 key pair** (private + public).\n"
        "4. **AES-GCM encrypt** the private key with the master key.\n"
        "5. Store the **public key** + user metadata in the primary PostgreSQL database.\n"
        "6. Store the **encrypted private key + nonce** in the Supabase key vault.\n"
        "7. Return the created user profile (no sensitive data).\n\n"
        "The password and private key are wiped from memory in a `finally` block."
    ),
    responses={
        201: {"description": "User created successfully."},
        409: {"description": "A user with this username or email already exists."},
        500: {"description": "Server misconfiguration or key vault storage error."},
    }
)
#current_user: dict = Depends(get_current_user)
async def create_user(req: Request, user_req: CreateUserRequest, db: db_dependency, current_user = Depends(role_checker(["admin"]))):
    # Duplicate user check BEFORE any crypto to prevent CPU abuse
    try:
        existing_user = db.query(Users).filter(
            (Users.username == user_req.username) | (Users.email == user_req.email)
        ).first()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[DB Error] Failed to query users table: {e}"
        )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username or email already exists."
        )

    # Raise hard 500 if critical secrets are missing (no weak fallbacks)
    argon2_pepper_str = os.getenv("ARGON2_SECRET_PEPPER")
    argon2_ad_str = os.getenv("ARGON2_ASSOCIATED_DATA")
    jwt_secret = os.getenv("JWT_SECRET_KEY")
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

        # 4. Storage Logic — Store Public Key and user metadata in PostgreSQL (Render)
        user_dict = user_req.model_dump(exclude={'password'})
        user_model = Users(**user_dict)
        user_model.public_key = b64_public_key
        user_model.is_active = user_model.relive_date is None
        user_model.created_dt = datetime.now(timezone.utc).date()

        db.add(user_model)
        try:
            db.flush()  # Flush to get the auto-increment user ID without committing yet

            # Store Encrypted Private Key and nonce in Supabase (key vault)
            # If this fails, rollback the primary DB transaction — no orphaned user rows
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
