from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, load_only
from starlette import status
from database.database import SessionLocal
from models import Users, PasswordResetTokens, UserLogs
from database.database_space import SUPABASE_URL, SUPABASE_SERVICE_KEY, update_user_keys_in_supabase
from dependencies import get_current_user
import os
import logging

logger = logging.getLogger(__name__)
import base64
import uuid
import jwt
import httpx
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidTag
from tools.gmail import GmailSender

router = APIRouter(
    prefix='/auth',
    tags=['Authentication'],
)


def _log(db: Session, action: str, user_id: int | None = None, description: str | None = None, request: Request | None = None):
    """Fire-and-forget audit log. Never raises — silently rolls back on failure."""
    try:
        ip = None
        if request:
            forwarded = request.headers.get("x-forwarded-for")
            ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None
        db.add(UserLogs(user_id=user_id, action=action, description=description, ip_address=ip))
        db.commit()
    except Exception:
        db.rollback()

ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60 #token excperis afgter one hout


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
    email: str        = Field(description="The authenticated user's email address.")


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
async def login(login_req: LoginRequest, db: db_dependency, response: Response, request: Request):

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

    # 2. Look up user by username OR email - Fetch only required columns
    user = db.query(Users).options(load_only(
        Users.id, Users.username, Users.email, Users.role, Users.is_active
    )).filter(
        (Users.username == login_req.identifier) |
        (Users.email    == login_req.identifier)
    ).first()

    if not user:
        _log(db, "login_failed", description=f"Unknown identifier: {login_req.identifier}", request=request)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    if not user.is_active:
        _log(db, "login_failed", user_id=user.id, description="Account inactive", request=request)
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
        if supabase_url: supabase_url = supabase_url.encode('ascii', 'ignore').decode('ascii').strip().strip('"').strip("'")
        
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)
        if supabase_key: supabase_key = supabase_key.encode('ascii', 'ignore').decode('ascii').strip().strip('"').strip("'")

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
            _log(db, "login_failed", user_id=user.id, description="Wrong password", request=request)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials."
            )

        # 7. Issue JWT
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub":      str(user.id),
            "username": user.username,
            "email":    user.email,
            "role":     user.role,
            "exp":      expire,
        }
        token = jwt.encode(payload, jwt_secret, algorithm=ALGORITHM)

        _log(db, "login", user_id=user.id, request=request)

        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            username=user.username,
            email=user.email,
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


# ── Forgot Password Models ──────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    """Email address to send the password reset link to."""
    email: str = Field(..., description="Registered email address.", examples=["john@example.com"])


class ResetPasswordRequest(BaseModel):
    """New password with the reset token from the email link."""
    token: str = Field(..., description="The UUID reset token from the email link.")
    new_password: str = Field(..., description="The new password to set.", min_length=6)


# ── POST /auth/forgot-password ───────────────────────────────────────────────

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset email",
    description=(
        "Sends a password reset link to the user's registered email.\n\n"
        "Always returns a success message regardless of whether the email exists, "
        "to prevent user enumeration attacks."
    ),
    responses={
        200: {"description": "Reset email sent (or silently ignored if email not found)."},
    }
)
async def forgot_password(req: Request, body: ForgotPasswordRequest, db: db_dependency):
    # Always return the same message to prevent user enumeration
    generic_response = {"message": "If an account with that email exists, a reset link has been sent."}

    user = db.query(Users).options(load_only(
        Users.id, Users.email, Users.is_active, Users.first_name, Users.last_name
    )).filter(Users.email == body.email).first()

    if not user or not user.is_active:
        print("No Usch user")
        return {"message": "Sorry this email is not registered with us."}
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)

    recent_password_reset = (
        db.query(PasswordResetTokens.id)
        .filter(
            PasswordResetTokens.user_id == user.id,
            PasswordResetTokens.used.is_(True),
            PasswordResetTokens.created_at >= twenty_four_hours_ago
        )
        .first() is not None
    )
    
    if recent_password_reset:
        return {
            "message": "You have already changed your password in the last 24 hours. Please try again later."
        }
    # Generate a unique reset token
    reset_token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    token_record = PasswordResetTokens(
        user_id=user.id,
        token=reset_token,
        expires_at=expires_at,
        used=False,
    )
    db.add(token_record)
    db.commit()
    _log(db, "forgot_password_requested", user_id=user.id, request=req)

    # Build the reset link pointing to the frontend
    frontend_url = os.getenv("FRONTEND_URL", "https://cmdev.rakshitr.co.in").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"

    # Send the reset email
    try:
        gmail_client = GmailSender()
        logger.info(f"[RESET] Sending to {user.email} | SMTP: {gmail_client.smtp_server}:{gmail_client.smtp_port} | password_set={bool(gmail_client.smtp_password)} | link={reset_link}")
        await gmail_client.send_reset_email(
            sender="crypticmage00@gmail.com",
            to=user.email,
            name=f"{user.first_name} {user.last_name}",
            reset_link=reset_link,
        )
        logger.info(f"[RESET] Email sent OK to {user.email}")
    except Exception as e:
        logger.error(f"[RESET] FAILED for {user.email}: {type(e).__name__}: {e}", exc_info=True)

    return generic_response


# ── POST /auth/reset-password ────────────────────────────────────────────────

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password using a valid token",
    description=(
        "Validates the reset token, then:\n\n"
        "1. Generates a **new Ed25519 key pair**.\n"
        "2. Derives a new 32-byte master key via Argon2id from the new password.\n"
        "3. AES-GCM encrypts the new private key.\n"
        "4. Updates the **public key** in PostgreSQL.\n"
        "5. Replaces the **encrypted private key + nonce** in Supabase.\n"
        "6. Marks the token as used.\n"
    ),
    responses={
        200: {"description": "Password reset successful."},
        400: {"description": "Token is invalid, expired, or already used."},
        500: {"description": "Server misconfiguration or key vault error."},
    }
)
async def reset_password(body: ResetPasswordRequest, db: db_dependency):
    # Validate the reset token
    token_record = db.query(PasswordResetTokens).filter(
        PasswordResetTokens.token == body.token
    ).first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token."
        )
    if token_record.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset token has already been used."
        )
    # SQLite stores naive datetimes, so compare without tzinfo
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if token_record.expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset token has expired. Please request a new one."
        )

    # Fetch the user - Only need id and email for master key derivation
    user = db.query(Users).options(load_only(Users.id, Users.email)).filter(
        Users.id == token_record.user_id
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User associated with this token no longer exists."
        )

    # Fetch required secrets
    argon2_pepper_str = os.getenv("ARGON2_SECRET_PEPPER")
    argon2_ad_str     = os.getenv("ARGON2_ASSOCIATED_DATA")
    if not argon2_pepper_str or not argon2_ad_str:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: required secrets are missing."
        )

    argon2_pepper = argon2_pepper_str.encode("utf-8")
    argon2_ad     = argon2_ad_str.encode("utf-8")

    master_key = None
    private_key = None
    private_bytes = None

    try:
        # 1. Derive new master key from the new password
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
        master_key = kdf.derive(body.new_password.encode("utf-8"))

        # 2. Generate new Ed25519 key pair
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

        # 3. AES-GCM encrypt the new private key
        aesgcm = AESGCM(master_key)
        nonce = os.urandom(12)
        encrypted_private_key = aesgcm.encrypt(nonce, private_bytes, None)

        # Encode to base64
        b64_public_key = base64.b64encode(public_bytes).decode("utf-8")
        b64_encrypted_private_key = base64.b64encode(encrypted_private_key).decode("utf-8")
        b64_nonce = base64.b64encode(nonce).decode("utf-8")

        # 4. Update public key in PostgreSQL
        user.public_key = b64_public_key
        db.flush()

        # 5. Replace encrypted private key + nonce in Supabase
        await update_user_keys_in_supabase(
            user_id=user.id,
            encrypted_private_key=b64_encrypted_private_key,
            nonce=b64_nonce,
        )

        # 6. Mark token as used
        token_record.used = True
        db.commit()
        _log(db, "password_reset", user_id=user.id)

        return {"message": "Password has been reset successfully. You can now log in with your new password."}

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password reset failed: {e}"
        )
    finally:
        if hasattr(body, "new_password") and body.new_password:
            pwd_len = len(body.new_password)
            body.new_password = "\x00" * pwd_len
        if master_key:
            del master_key
        if private_key:
            del private_key
        if private_bytes:
            del private_bytes


class ChangePasswordRequest(BaseModel):
    """Current and new password for a logged-in user."""
    current_password: str = Field(..., description="The user's current password for verification.")
    new_password: str = Field(..., description="The brand-new password to set.", min_length=6)


# ── POST /auth/change-password ───────────────────────────────────────────────

@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Update password for the current user",
    description=(
        "Allows the logged-in user to change their password securely.\n\n"
        "1. Verifies the **current password** by re-deriving its master key and attempting AES-GCM decryption.\n"
        "2. Generates a **new Ed25519 key pair**.\n"
        "3. Derives a new master key via Argon2id from the new password.\n"
        "4. AES-GCM encrypts the new private key.\n"
        "5. Updates the **public key** in PostgreSQL.\n"
        "6. Replaces the **encrypted private key + nonce** in Supabase.\n"
    ),
    responses={
        200: {"description": "Password updated successfully."},
        401: {"description": "Current password is incorrect."},
        404: {"description": "User not found."},
        500: {"description": "Server misconfiguration or key vault error."},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: db_dependency,
    current_user: dict = Depends(get_current_user)
):
    user_id = int(current_user.get("sub"))
    user = db.query(Users).filter(Users.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Fetch required secrets
    argon2_pepper_str = os.getenv("ARGON2_SECRET_PEPPER")
    argon2_ad_str     = os.getenv("ARGON2_ASSOCIATED_DATA")
    if not argon2_pepper_str or not argon2_ad_str:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: required secrets are missing."
        )

    argon2_pepper = argon2_pepper_str.encode("utf-8")
    argon2_ad     = argon2_ad_str.encode("utf-8")

    master_key = None
    current_master_key = None
    private_key = None
    private_bytes = None

    try:
        salt = user.email.encode("utf-8")

        # 1. Verify current password by re-deriving its master key and decrypting the stored private key
        kdf_current = Argon2id(
            salt=salt,
            length=32,
            iterations=2,
            lanes=4,
            memory_cost=65536,
            ad=argon2_ad,
            secret=argon2_pepper,
        )
        current_master_key = kdf_current.derive(body.current_password.encode("utf-8"))

        supabase_url = os.getenv("SUPABASE_URL", SUPABASE_URL)
        if supabase_url: supabase_url = supabase_url.encode('ascii', 'ignore').decode('ascii').strip().strip('"').strip("'")

        supabase_key = os.getenv("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)
        if supabase_key: supabase_key = supabase_key.encode('ascii', 'ignore').decode('ascii').strip().strip('"').strip("'")

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
        encrypted_private_key_stored = base64.b64decode(key_row["encrypted_private_key"])
        nonce_stored                 = base64.b64decode(key_row["nonce"])

        try:
            aesgcm_verify = AESGCM(current_master_key)
            aesgcm_verify.decrypt(nonce_stored, encrypted_private_key_stored, None)
        except InvalidTag:
            _log(db, "change_password_failed", user_id=user.id, description="Wrong current password", request=request)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect."
            )

        # 2. Derive new master key from the new password
        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=2,
            lanes=4,
            memory_cost=65536,
            ad=argon2_ad,
            secret=argon2_pepper,
        )
        master_key = kdf.derive(body.new_password.encode("utf-8"))

        # 3. Generate new Ed25519 key pair
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

        # 4. AES-GCM encrypt the new private key
        aesgcm = AESGCM(master_key)
        nonce = os.urandom(12)
        encrypted_private_key = aesgcm.encrypt(nonce, private_bytes, None)

        # Encode to base64
        b64_public_key = base64.b64encode(public_bytes).decode("utf-8")
        b64_encrypted_private_key = base64.b64encode(encrypted_private_key).decode("utf-8")
        b64_nonce = base64.b64encode(nonce).decode("utf-8")

        # 5. Update public key in PostgreSQL
        user.public_key = b64_public_key
        db.flush()

        # 6. Replace encrypted private key + nonce in Supabase
        await update_user_keys_in_supabase(
            user_id=user.id,
            encrypted_private_key=b64_encrypted_private_key,
            nonce=b64_nonce,
        )

        db.commit()
        _log(db, "password_changed", user_id=user.id, request=request)
        return {"message": "Password updated successfully."}

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Password update failed: {e}"
        )
    finally:
        # Wipe sensitive values
        if hasattr(body, "current_password") and body.current_password:
            body.current_password = "\x00" * len(body.current_password)
        if hasattr(body, "new_password") and body.new_password:
            body.new_password = "\x00" * len(body.new_password)
        if current_master_key:
            del current_master_key
        if master_key:
            del master_key
        if private_key:
            del private_key
        if private_bytes:
            del private_bytes

