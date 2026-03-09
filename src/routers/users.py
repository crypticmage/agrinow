from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from starlette import status
from database.database import SessionLocal
from models import Users
from datetime import date
from dependencies import get_current_user
router = APIRouter(
    prefix='/users',
    tags=['User Management']
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


class UserSummary(BaseModel):
    """Public user profile. Sensitive fields (private key, password) are never returned."""
    id:          int            = Field(description="Auto-assigned user ID.")
    username:    str            = Field(description="Unique username.")
    email:       str            = Field(description="Registered email address.")
    phone:       Optional[str]  = Field(None, description="Phone number, if provided.")
    first_name:  str            = Field(description="First name.")
    last_name:   str            = Field(description="Last name.")
    language:    str            = Field(description="Preferred language code.")
    role:        str            = Field(description="Assigned role.")
    manager_id:  Optional[int]  = Field(None, description="Manager's user ID, if set.")
    is_active:   Optional[bool] = Field(None, description="Whether the account is active.")
    hire_date:   date           = Field(description="Hire date.")
    relive_date: Optional[date] = Field(None, description="Relieve date, if set.")
    emp_type:    Optional[str]  = Field(None, description="Employment type.")
    created_dt:  date           = Field(description="UTC date the account was created.")

    model_config = ConfigDict(from_attributes=True)


class UserDropdown(BaseModel):
    """Minimal user payload for dropdown menus (active users only)."""
    id:         int = Field(description="Auto-assigned user ID.")
    username:   str = Field(description="Unique username.")
    first_name: str = Field(description="First name.")
    last_name:  str = Field(description="Last name.")

    model_config = ConfigDict(from_attributes=True)


class OrgNode(BaseModel):
    """Recursive organizational chart node."""
    id: int
    username: str
    first_name: str
    last_name: str
    role: str
    subordinates: List['OrgNode'] = []

    model_config = ConfigDict(from_attributes=True)


# ── GET /users/ ───────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[UserSummary],
    status_code=status.HTTP_200_OK,
    summary="List all users",
    description=(
        "Returns a paginated list of all registered users from the primary PostgreSQL database.\n\n"
        "Use `skip` and `limit` to paginate through results. "
        "Sensitive fields (password, private key) are never included."
    ),
    responses={
        200: {"description": "List of users returned successfully."},
        401: {"description": "Missing or invalid JWT token."},
        404: {"description": "No users found in the database."},
    }
)
def get_all_users(
    db: db_dependency,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch all users with optional pagination.
    - **skip**: number of records to skip (default 0)
    - **limit**: max records to return (default 50, max recommended 100)
    """
    users = db.query(Users).offset(skip).limit(limit).all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No users found."
        )
    return users


# ── GET /users/manager_dropdown ───────────────────────────────────────────────────────
@router.get(
    "/manager_dropdown",
    response_model=List[UserDropdown],
    status_code=status.HTTP_200_OK,
    summary="List active users for manager dropdown options",
    description=(
        "Returns a lightweight list of active users intended for frontend dropdowns "
        "when selecting a manager. Does not paginate the results."
    ),
)
def get_manager_dropdown(
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch all active users for dropdowns.
    """
    users = db.query(Users).filter(Users.is_active == True).all()
    return users


# ── GET /users/{user_id} ──────────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=UserSummary,
    status_code=status.HTTP_200_OK,
    summary="Get a single user by ID",
    description="Fetches a single user's public profile from the primary database by their numeric ID.",
    responses={
        200: {"description": "User profile returned successfully."},
        401: {"description": "Missing or invalid JWT token."},
        404: {"description": "No user found with the given ID."},
    }
)
def get_user(user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found."
        )
    return user
