from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from starlette import status
from database.database import SessionLocal
from models import Users
from datetime import date, datetime
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


class UserUpdateRequest(BaseModel):
    """Payload to update an existing user."""
    role: Optional[str] = Field(None, description="New role for the user.")
    phone: Optional[str] = Field(None, description="New phone number.")
    is_active: Optional[bool] = Field(None, description="Set active status.")
    relive_date: Optional[date] = Field(None, description="Set the relieve date.")
    manager_id: Optional[int] = Field(None, description="Set the new manager.")


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

# ── GET /users/logs ────────────────────────────────────────────────────────────

class UserLogResponse(BaseModel):
    id: int
    user_id: int
    username: str
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)

@router.get(
    "/logs",
    response_model=List[UserLogResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all user login activity logs",
)
def get_user_logs(
    db: db_dependency,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    from models import UserLogs
    logs = db.query(UserLogs, Users.username).join(Users, UserLogs.user_id == Users.id).order_by(UserLogs.timestamp.desc()).limit(limit).all()
    
    results = []
    for log, username in logs:
        results.append({
            "id": log.id,
            "user_id": log.user_id,
            "username": username,
            "timestamp": log.timestamp
        })
    return results

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


# ── PUT /users/{user_id} ──────────────────────────────────────────────────────

@router.put(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a user's record",
    description="Updates specific fields for a user like role, phone, is_active, and relive_date."
)
def update_user(
    user_id: int,
    update_data: UserUpdateRequest,
    db: db_dependency,
    current_user: dict = Depends(get_current_user)
):
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found."
        )
    
    if update_data.role is not None:
        user.role = update_data.role
    if update_data.phone is not None:
        user.phone = update_data.phone
    if update_data.manager_id is not None:
        user.manager_id = update_data.manager_id
        
    # Auto-calculate active status based on relive date if it is updated
    if update_data.relive_date is not None:
        user.relive_date = update_data.relive_date
        if user.relive_date <= date.today():
            user.is_active = False
        else:
            user.is_active = True
    elif update_data.is_active is not None:
        user.is_active = update_data.is_active
        
    db.commit()
    return {"message": "User updated successfully"}


# ── DELETE /users/{user_id} ───────────────────────────────────────────────────

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a user",
    description="Completely removes a user from the primary database."
)
def delete_user(
    user_id: int,
    db: db_dependency,
    current_user: dict = Depends(get_current_user)
):
    user = db.query(Users).filter(Users.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found."
        )
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


# ── GET /users/org ────────────────────────────────────────────────────────────

@router.get(
    "/org/chart",
    response_model=OrgNode,
    status_code=status.HTTP_200_OK,
    summary="Get user organizational chart",
    description=(
        "Returns the organizational chart starting from a specific user. "
        "If neither username nor email is provided, it defaults to the current user."
    ),
    responses={
        200: {"description": "Organizational chart returned successfully."},
        401: {"description": "Missing or invalid JWT token."},
        404: {"description": "User not found in the database."},
    }
)
def get_user_org_chart(
    db: db_dependency,
    username: Optional[str] = None,
    email: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    if username:
        root_user = db.query(Users).filter(Users.username == username).first()
    elif email:
        root_user = db.query(Users).filter(Users.email == email).first()
    else:
        root_user = db.query(Users).filter(Users.id == int(current_user.get("sub"))).first()

    if not root_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Fetch all active users to build the tree efficiently in memory
    # instead of hitting the database for each node's children.
    all_users = db.query(Users).filter(Users.is_active == True).all()
    
    children_map = {}
    for u in all_users:
        if u.manager_id not in children_map:
            children_map[u.manager_id] = []
        children_map[u.manager_id].append(u)

    def build_node(user):
        node = OrgNode(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            subordinates=[]
        )
        children = children_map.get(user.id, [])
        for child in children:
            node.subordinates.append(build_node(child))
        return node

    return build_node(root_user)
