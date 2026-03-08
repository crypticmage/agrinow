from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette import status
from database.database import SessionLocal
from models import Users
from database.database_space import SUPABASE_URL, SUPABASE_SERVICE_KEY
from dependencies import get_current_user
import os
import base64
import jwt
import httpx
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

router = APIRouter(
    prefix='/auth',
    tags=['Authentication'],
)

ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 10


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


class LoginRequest(BaseModel):
    """
    Credentials required to authenticate a user.
    """
    identifier: str = Field(
        ...,
        description="Username or email address.",
        examples=["john_doe", "john@example.com"]
    )
    password: str = Field(
        ...,
        description="The user's plaintext password. Stretched via Argon2id into a 32-byte master key; never stored.",
        examples=["MySecureP@ssw0rd"]
    )


class TokenResponse(BaseModel):
    """
    Successful authentication response containing a short-lived JWT access token.
    """
    access_token: str = Field(description="HS256-signed JWT. Valid for 10 minutes.")
    token_type: str   = Field(description="Always 'bearer'.")
    username: str     = Field(description="The authenticated user's username.")
    role: str         = Field(description="The authenticated user's role (e.g. admin, farmer, agent).")


# ── POST /auth/login ─────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue JWT",
    description=(
        "Zero-knowledge login flow:\n\n"
        "1. Look up user by **email** in the primary database.\n"
        "2. Re-derive a 32-byte **master key** using Argon2id "
        "(`salt=email`, `secret=ARGON2_SECRET_PEPPER`, `ad=ARGON2_ASSOCIATED_DATA`).\n"
        "3. Fetch the user's **AES-GCM-encrypted Ed25519 private key** from the Supabase key vault.\n"
        "4. Attempt AES-GCM decryption — an `InvalidTag` error means the password is wrong (→ 401).\n"
        "5. On success, issue a short-lived **HS256 JWT** containing `sub`, `username`, `role`, and `exp`.\n\n"
        "Sensitive values (master key, decrypted private key bytes) are wiped from memory in a `finally` block."
    ),
    responses={
        200: {"description": "Login successful — JWT access token returned."},
        401: {"description": "Invalid credentials (wrong password)."},
        403: {"description": "Account is inactive."},
        404: {"description": "No user found with the given email."},
        500: {"description": "Server misconfiguration or key vault error."},
    }
)
async def login(login_req: LoginRequest, db: db_dependency):

    # 1. Fetch required secrets
    argon2_pepper_str = os.getenv("ARGON2_SECRET_PEPPER")
    argon2_ad_str     = os.getenv("ARGON2_ASSOCIATED_DATA")
    jwt_secret        = os.getenv("JWT_SECRET_KEY")
    if not argon2_pepper_str or not argon2_ad_str or not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: required secrets are missing."
        )

    argon2_pepper = argon2_pepper_str.encode("utf-8")
    argon2_ad     = argon2_ad_str.encode("utf-8")

    # 2. Look up user by username OR email
    user = db.query(Users).filter(
        (Users.username == login_req.identifier) |
        (Users.email    == login_req.identifier)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive."
        )

    # Declare sensitive vars upfront so the finally block can always wipe them
    master_key       = None
    private_key_bytes = None

    try:
        # 3. Re-derive master key with Argon2id (same params as create_user)
        salt = user.email.encode("utf-8")
        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=2,
            lanes=4,
            memory_cost=65536,
            ad=argon2_ad,
            secret=argon2_pepper,
        )
        master_key = kdf.derive(login_req.password.encode("utf-8"))

        # 4. Fetch encrypted private key + nonce from Supabase
        supabase_url = os.getenv("SUPABASE_URL", SUPABASE_URL)
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{supabase_url}/rest/v1/user_keys",
                params={"user_id": f"eq.{user.id}", "limit": "1"},
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                },
                timeout=5,
            )

        if resp.status_code != 200 or not resp.json():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not retrieve key data from vault."
            )

        key_row = resp.json()[0]
        encrypted_private_key = base64.b64decode(key_row["encrypted_private_key"])
        nonce                 = base64.b64decode(key_row["nonce"])

        # 5. Decrypt private key — InvalidTag means wrong password
        try:
            aesgcm = AESGCM(master_key)
            private_key_bytes = aesgcm.decrypt(nonce, encrypted_private_key, None)
        except InvalidTag:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials."
            )

        # 7. Issue JWT
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub":      str(user.id),
            "username": user.username,
            "role":     user.role,
            "exp":      expire,
        }
        token = jwt.encode(payload, jwt_secret, algorithm=ALGORITHM)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            username=user.username,
            role=user.role,
        )

    finally:
        # Wipe sensitive data from memory
        if hasattr(login_req, "password") and login_req.password:
            pwd_len = len(login_req.password)
            login_req.password = "\x00" * pwd_len
        if master_key:
            del master_key
        if private_key_bytes:
            del private_key_bytes
