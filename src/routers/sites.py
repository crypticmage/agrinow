from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, load_only
from starlette import status
from datetime import date, datetime, timezone, timedelta

from database.database import SessionLocal
from models import Sites, SiteAssignments, SiteComments, Users
from dependencies import get_current_user
from tools.gmail import GmailSender

async def send_site_assignment_notification(email: str, name: str, site_name: str, assigned_date: str, language: str):
    try:
        sender = GmailSender()
        await sender.send_site_assignment_email(
            sender=sender.smtp_username,
            to=email,
            name=name,
            site_name=site_name,
            assigned_date=assigned_date,
            language=language
        )
    except Exception as e:
        print(f"Background email failed: {e}")

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
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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
    image_id: Optional[int] = None
    type: Optional[str] = "text"

class SiteCommentResponse(BaseModel):
    id: int
    site_user_relation_id: int
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    comment: str
    image_id: Optional[int] = None
    type: Optional[str] = None
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Routes ---

@router.get("/my", response_model=List[SiteResponse], status_code=status.HTTP_200_OK)
def get_my_sites(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch all sites assigned to the current logged-in user."""
    user_id = int(current_user.get("sub"))
    sites = (
        db.query(Sites)
        .join(SiteAssignments, SiteAssignments.site_id == Sites.id)
        .filter(SiteAssignments.user_id == user_id)
        .all()
    )
    return sites

@router.get("/my-assignments", status_code=status.HTTP_200_OK)
def get_my_assignments(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch all site assignment rows for the current user."""
    user_id = int(current_user.get("sub"))
    assignments = db.query(SiteAssignments).filter(SiteAssignments.user_id == user_id).all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "site_id": a.site_id,
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        }
        for a in assignments
    ]
    
@router.get("/all-assignments", status_code=status.HTTP_200_OK)
def get_all_assignments(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch all site assignment rows in the system (for managers/admins)."""
    assignments = db.query(SiteAssignments).all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "site_id": a.site_id,
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        }
        for a in assignments
    ]

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
def assign_user_to_site(
    assign_req: SiteAssignmentCreate,
    background_tasks: BackgroundTasks,
    db: db_dependency,
    current_user: dict = Depends(get_current_user)
):
    """Assign a user to a specific site."""
    # Validate user exists
    user = db.query(Users).options(load_only(Users.id, Users.email, Users.first_name, Users.username, Users.language)).filter(Users.id == assign_req.user_id).first()
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

    if user.email:
        background_tasks.add_task(
            send_site_assignment_notification,
            user.email,
            user.first_name or user.username,
            site.site_name,
            str(new_assignment.assigned_date),
            user.language or "en"
        )
        
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
        image_id=comment_req.image_id,
        type=comment_req.type,
        timestamp=datetime.utcnow()
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment

@router.get("/assignments/user/{user_id}", status_code=status.HTTP_200_OK)
def get_user_assignments(user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Get all site assignments for a specific user."""
    assignments = db.query(SiteAssignments).filter(SiteAssignments.user_id == user_id).all()
    result = []
    for a in assignments:
        site = db.query(Sites).filter(Sites.id == a.site_id).first()
        result.append({
            "id": a.id,
            "user_id": a.user_id,
            "site_id": a.site_id,
            "site_name": site.site_name if site else None,
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        })
    return result

@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_site_assignment(assignment_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Remove a site assignment."""
    assignment = db.query(SiteAssignments).filter(SiteAssignments.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()

_IST = timezone(timedelta(hours=5, minutes=30))

@router.get("/{site_id}/comments", response_model=List[SiteCommentResponse], status_code=status.HTTP_200_OK)
def get_site_comments(site_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Retrieve all comments/chat for a specific site, with user name/role and IST timestamps."""
    comments = (
        db.query(SiteComments)
        .join(SiteAssignments, SiteAssignments.id == SiteComments.site_user_relation_id)
        .filter(SiteAssignments.site_id == site_id)
        .order_by(SiteComments.timestamp.asc())
        .all()
    )

    # Batch-fetch users to avoid N+1
    user_ids = list({c.user_id for c in comments})
    users_map = {u.id: u for u in db.query(Users).filter(Users.id.in_(user_ids)).all()} if user_ids else {}

    result = []
    for c in comments:
        u = users_map.get(c.user_id)
        # Convert naive UTC timestamp → IST
        ts = c.timestamp
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc).astimezone(_IST)
        result.append({
            "id": c.id,
            "site_user_relation_id": c.site_user_relation_id,
            "user_id": c.user_id,
            "username": u.username if u else None,
            "first_name": u.first_name if u else None,
            "last_name": u.last_name if u else None,
            "role": u.role if u else None,
            "comment": c.comment,
            "image_id": c.image_id,
            "type": c.type,
            "timestamp": ts,
        })
    return result
