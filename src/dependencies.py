"""
Shared FastAPI dependencies for the Agrinow API.
Import get_current_user into any router that requires authentication.
"""
import os
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

ALGORITHM = "HS256"

# Tells FastAPI/Swagger UI to expect a Bearer token in the Authorization header
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Validates the JWT Bearer token from the Authorization header.
    Returns the decoded token payload: { "sub", "username", "role", "exp" }
    Raises HTTP 401 if the token is missing, expired, or invalid.
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
        return payload
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
