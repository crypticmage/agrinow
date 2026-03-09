from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from starlette import status
from datetime import date, datetime

from database.database import SessionLocal
from models import Sites, SiteAssignments, SiteComments, Users
from dependencies import get_current_user

router = APIRouter(
    prefix='/sites',
    tags=['Sites & Chat']
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

# --- Schemas ---
class SiteCreate(BaseModel):
    site_name: str
    site_description: str
    created_date: date
    close_date: Optional[date] = None

class SiteResponse(SiteCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class SiteAssignmentCreate(BaseModel):
    user_id: int
    site_id: int
    assigned_date: date

class SiteAssignmentResponse(SiteAssignmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class SiteCommentCreate(BaseModel):
    site_user_relation_id: int
    comment: str

class SiteCommentResponse(BaseModel):
    id: int
    site_user_relation_id: int
    user_id: int
    comment: str
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Routes ---

@router.post("/", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(site_request: SiteCreate, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Create a new site."""
    new_site = Sites(**site_request.model_dump())
    db.add(new_site)
    db.commit()
    db.refresh(new_site)
    return new_site

@router.get("/", response_model=List[SiteResponse], status_code=status.HTTP_200_OK)
def get_all_sites(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch all sites."""
    return db.query(Sites).all()

@router.post("/assign", response_model=SiteAssignmentResponse, status_code=status.HTTP_201_CREATED)
def assign_user_to_site(assign_req: SiteAssignmentCreate, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Assign a user to a specific site."""
    # Validate user exists
    user = db.query(Users).filter(Users.id == assign_req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Validate site exists
    site = db.query(Sites).filter(Sites.id == assign_req.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
        
    new_assignment = SiteAssignments(**assign_req.model_dump())
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)
    return new_assignment

@router.post("/comments", response_model=SiteCommentResponse, status_code=status.HTTP_201_CREATED)
def add_site_comment(comment_req: SiteCommentCreate, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Add a chat comment associated with a user's site assignment."""
    # Verify assignment exists
    assignment = db.query(SiteAssignments).filter(SiteAssignments.id == comment_req.site_user_relation_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Site assignment relation not found")

    new_comment = SiteComments(
        site_user_relation_id=assignment.id,
        user_id=assignment.user_id,
        comment=comment_req.comment,
        timestamp=datetime.utcnow()
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment

@router.get("/{site_id}/comments", response_model=List[SiteCommentResponse], status_code=status.HTTP_200_OK)
def get_site_comments(site_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Retrieve all comments/chat for a specific site."""
    # Join SiteComments with SiteAssignments to filter by site_id
    comments = db.query(SiteComments).join(SiteAssignments, SiteAssignments.id == SiteComments.site_user_relation_id)\
                 .filter(SiteAssignments.site_id == site_id)\
                 .order_by(SiteComments.timestamp.asc()).all()
    return comments
