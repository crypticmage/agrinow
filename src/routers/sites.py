from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, load_only
from starlette import status
from datetime import date, datetime, timezone, timedelta
import asyncio

from database.database import SessionLocal
from models import Sites, SiteAssignments, SiteComments, Users
from dependencies import get_current_user
from tools.gmail import GmailSender
from googletrans import Translator, LANGUAGES
from utils.timezone import get_ist_date

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


def _accessible_site_ids(user_id: int, role: str, db: Session) -> list[int] | None:
    """Return the set of site_ids the current user may access, or None for unrestricted (admin)."""
    if role == "admin":
        return None  # no restriction

    # Own assignments
    own = db.query(SiteAssignments.site_id).filter(SiteAssignments.user_id == user_id).all()
    site_ids = {row.site_id for row in own}

    # If manager: also include sites assigned to direct subordinates
    if role == "manager":
        subordinate_ids = [
            row.id for row in db.query(Users.id).filter(Users.manager_id == user_id).all()
        ]
        if subordinate_ids:
            sub_sites = db.query(SiteAssignments.site_id).filter(
                SiteAssignments.user_id.in_(subordinate_ids)
            ).all()
            site_ids.update(row.site_id for row in sub_sites)

    return list(site_ids)

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
    rows = (
        db.query(SiteAssignments, Sites.site_name)
        .join(Sites, Sites.id == SiteAssignments.site_id)
        .filter(SiteAssignments.user_id == user_id)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "site_id": a.site_id,
            "site_name": site_name,
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        }
        for a, site_name in rows
    ]
    
@router.get("/all-assignments", status_code=status.HTTP_200_OK)
def get_all_assignments(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch all site assignment rows in the system (for managers/admins)."""
    assignments = db.query(SiteAssignments).all()
    user_ids = {a.user_id for a in assignments}
    users = {u.id: u.username for u in db.query(Users.id, Users.username).filter(Users.id.in_(user_ids)).all()}
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "username": users.get(a.user_id),
            "site_id": a.site_id,
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        }
        for a in assignments
    ]

@router.post("/", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(site_request: SiteCreate, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Create a new site and auto-assign all active admin users to it."""
    new_site = Sites(**site_request.model_dump())
    db.add(new_site)
    db.flush()  # populate new_site.id before creating assignments

    admins = db.query(Users).filter(Users.role == "admin", Users.is_active == True).all()
    for admin in admins:
        db.add(SiteAssignments(
            user_id=admin.id,
            site_id=new_site.id,
            assigned_date=get_ist_date(),
        ))

    db.commit()
    db.refresh(new_site)
    return new_site

@router.get("/", response_model=List[SiteResponse], status_code=status.HTTP_200_OK)
def get_all_sites(db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Fetch sites accessible to the current user (all for admin, own+subordinates for manager, own for others)."""
    user_id = int(current_user["sub"])
    role = current_user.get("role", "")
    allowed = _accessible_site_ids(user_id, role, db)
    if allowed is None:
        return db.query(Sites).all()
    if not allowed:
        return []
    return db.query(Sites).filter(Sites.id.in_(allowed)).all()

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
    requester_id = int(current_user["sub"])
    role = current_user.get("role", "")

    # Verify assignment exists
    assignment = db.query(SiteAssignments).filter(SiteAssignments.id == comment_req.site_user_relation_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Site assignment relation not found")

    # Verify the requester has access to this site (admins can comment on all sites)
    if role != "admin":
        allowed = _accessible_site_ids(requester_id, role, db)
        if allowed is not None and assignment.site_id not in allowed:
            raise HTTPException(status_code=403, detail="You do not have access to this site.")

    new_comment = SiteComments(
        site_user_relation_id=assignment.id,
        user_id=requester_id,
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
    site_ids = [a.site_id for a in assignments]
    sites_map = {s.id: s.site_name for s in db.query(Sites.id, Sites.site_name).filter(Sites.id.in_(site_ids)).all()} if site_ids else {}
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "site_id": a.site_id,
            "site_name": sites_map.get(a.site_id),
            "assigned_date": str(a.assigned_date) if a.assigned_date else None,
        }
        for a in assignments
    ]

@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_site_assignment(assignment_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Remove a site assignment."""
    assignment = db.query(SiteAssignments).filter(SiteAssignments.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assignment)
    db.commit()

_IST = timezone(timedelta(hours=5, minutes=30))

async def _translate(text: str, lang_code: str) -> str:
    """Translate text to lang_code; falls back to original on error."""
    if not text or not lang_code or lang_code in ("en", "english"):
        return text
    LANGUAGE_NAMES = {v: k for k, v in LANGUAGES.items()}
    dest = LANGUAGE_NAMES.get(lang_code.strip().lower(), lang_code.strip().lower())
    try:
        translator = Translator()
        result = await asyncio.wait_for(translator.translate(text, dest=dest), timeout=5.0)
        return result.text
    except Exception:
        return text


@router.get("/{site_id}/comments", response_model=List[SiteCommentResponse], status_code=status.HTTP_200_OK)
async def get_site_comments(site_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    """Retrieve all comments/chat for a specific site, translated to the requesting user's language."""
    user_id = int(current_user["sub"])
    role = current_user.get("role", "")
    allowed = _accessible_site_ids(user_id, role, db)
    if allowed is not None and site_id not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to this site.")

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

    # Resolve requesting user's preferred language
    requester = db.query(Users.language).filter(Users.id == user_id).first()
    lang = (requester.language or "en") if requester else "en"

    result = []
    for c in comments:
        u = users_map.get(c.user_id)
        # Convert naive UTC timestamp → IST
        ts = c.timestamp
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc).astimezone(_IST)
        translated_comment = await _translate(c.comment or "", lang)
        result.append({
            "id": c.id,
            "site_user_relation_id": c.site_user_relation_id,
            "user_id": c.user_id,
            "username": u.username if u else None,
            "first_name": u.first_name if u else None,
            "last_name": u.last_name if u else None,
            "role": u.role if u else None,
            "comment": translated_comment,
            "image_id": c.image_id,
            "type": c.type,
            "timestamp": ts,
        })
    return result
