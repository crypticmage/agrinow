"""
Shared FastAPI dependencies for the Agrinow API.
Import get_current_user into any router that requires authentication.
"""
import os
import jwt
from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from starlette import status

from database.database import SessionLocal

ALGORITHM = "HS256"

# Tells FastAPI/Swagger UI to expect a Bearer token in the Authorization header
bearer_scheme = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Validates the JWT Bearer token from the Authorization header.
    Returns the decoded token payload: { "sub", "username", "role", "exp" }
    Raises HTTP 401 if the token is missing, expired, invalid, or force-logged-out.
    """
    jwt_secret = os.getenv("JWT_SECRET_KEY")
    if not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfiguration: JWT secret is missing.",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if an admin has force-logged-out this user since the token was issued
    user_id = payload.get("sub")
    if user_id:
        from models import Users
        user = db.query(Users.force_logout_at).filter(Users.id == int(user_id)).first()
        if user and user.force_logout_at is not None:
            token_iat = payload.get("iat")
            if token_iat is not None:
                # force_logout_at is naive UTC; compare with iat (unix timestamp)
                force_ts = user.force_logout_at.replace(tzinfo=timezone.utc).timestamp()
                if token_iat < force_ts:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Session terminated by administrator. Please log in again.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

    return payload
