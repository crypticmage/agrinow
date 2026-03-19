from typing import Annotated, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, load_only
from starlette import status
from datetime import date, datetime
import calendar
import math
import os
import logging

logger = logging.getLogger(__name__)

from database.database import SessionLocal
from models import AttendanceLog, Users, SiteAssignments, Sites
from dependencies import get_current_user
from tools.gmail import GmailSender
from utils.timezone import get_ist_now, get_ist_date


def _compliance_radius_km() -> float:
    """Read the site compliance radius from env (default 10 km)."""
    return float(os.getenv("SITE_COMPLIANCE_RADIUS_KM", "10"))


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in km between two GPS coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_compliance(user_id: int, lat: Optional[float], lng: Optional[float], db: Session) -> Tuple[str, Optional[float]]:
    """Return (compliance_status, distance_km) for a check-in location."""
    if lat is None or lng is None:
        return "no_location", None
    assignments = db.query(SiteAssignments).filter(SiteAssignments.user_id == user_id).all()
    if not assignments:
        return "no_site", None
    site_ids = [a.site_id for a in assignments]
    sites = db.query(Sites).filter(
        Sites.id.in_(site_ids),
        Sites.latitude.isnot(None),
        Sites.longitude.isnot(None),
    ).all()
    if not sites:
        return "no_site", None
    distances = [_haversine_km(lat, lng, s.latitude, s.longitude) for s in sites]
    min_dist = min(distances)
    dist_rounded = float(f"{min_dist:.2f}")
    radius = _compliance_radius_km()
    return ("compliant" if min_dist <= radius else "non_compliant"), dist_rounded


async def send_attendance_notification(
    email: str,
    name: str,
    date_str: str,
    time_str: str,
    action: str,
    language: str,
    notes: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    compliance: Optional[str] = None,
    distance_km: Optional[float] = None,
):
    try:
        sender = GmailSender()
        logger.info(f"Sending attendance email to {email} | SMTP: {sender.smtp_server}:{sender.smtp_port} | password_set={bool(sender.smtp_password)}")
        await sender.send_attendance_email(
            sender=sender.smtp_username,
            to=email,
            name=name,
            date_str=date_str,
            time_str=time_str,
            action_type=action,
            language=language,
            notes=notes,
            latitude=latitude,
            longitude=longitude,
            compliance=compliance,
            distance_km=distance_km,
        )
        logger.info(f"Attendance email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Background attendance email FAILED for {email}: {type(e).__name__}: {e}", exc_info=True)

router = APIRouter(prefix='/attendance', tags=['Attendance'])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckInRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None


class CheckOutRequest(BaseModel):
    notes: Optional[str] = None


class AttendanceResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    # Compliance: "compliant" | "non_compliant" | "no_location" | "no_site"
    site_compliance: Optional[str] = None
    site_distance_km: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/check-in", response_model=AttendanceResponse, status_code=status.HTTP_200_OK)
def check_in(
    req: CheckInRequest,
    background_tasks: BackgroundTasks,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    """Record check-in for today. Only one check-in allowed per day."""
    user_id = int(current_user["sub"])
    today = get_ist_date()

    existing = db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.date == today,
    ).first()

    if existing:
        if existing.check_in:
            raise HTTPException(status_code=400, detail="Already checked in today.")
        existing.check_in = get_ist_now()
        existing.latitude = req.latitude
        existing.longitude = req.longitude
        existing.notes = req.notes
        db.commit()
        db.refresh(existing)
        
        user = db.query(Users).options(load_only(Users.id, Users.email, Users.first_name, Users.username, Users.language)).filter(Users.id == user_id).first()
        if user and user.email:
            compliance, dist = _compute_compliance(user_id, req.latitude, req.longitude, db)
            background_tasks.add_task(
                send_attendance_notification,
                user.email,
                user.first_name or user.username,
                str(today),
                existing.check_in.strftime("%I:%M %p IST"),
                "Check-In",
                user.language or "en",
                req.notes,
                req.latitude,
                req.longitude,
                compliance,
                dist,
            )

        return _with_username(existing, db)

    record = AttendanceLog(
        user_id=user_id,
        date=today,
        check_in=get_ist_now(),
        latitude=req.latitude,
        longitude=req.longitude,
        notes=req.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    
    user = db.query(Users).options(load_only(Users.id, Users.email, Users.first_name, Users.username, Users.language)).filter(Users.id == user_id).first()
    if user and user.email:
        compliance, dist = _compute_compliance(user_id, req.latitude, req.longitude, db)
        background_tasks.add_task(
            send_attendance_notification,
            user.email,
            user.first_name or user.username,
            str(today),
            record.check_in.strftime("%I:%M %p IST"),
            "Check-In",
            user.language or "en",
            req.notes,
            req.latitude,
            req.longitude,
            compliance,
            dist,
        )

    return _with_username(record, db)


@router.post("/check-out", response_model=AttendanceResponse, status_code=status.HTTP_200_OK)
def check_out(
    req: CheckOutRequest,
    background_tasks: BackgroundTasks,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    """Record check-out for today. Must have checked in first."""
    user_id = int(current_user["sub"])
    today = get_ist_date()

    record = db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.date == today,
    ).first()

    if not record or not record.check_in:
        raise HTTPException(status_code=400, detail="No check-in found for today.")
    if record.check_out:
        raise HTTPException(status_code=400, detail="Already checked out today.")

    record.check_out = get_ist_now()
    if req.notes:
        record.notes = req.notes
    db.commit()
    db.refresh(record)
    
    user = db.query(Users).options(load_only(Users.id, Users.email, Users.first_name, Users.username, Users.language)).filter(Users.id == user_id).first()
    if user and user.email:
        compliance, dist = _compute_compliance(user_id, record.latitude, record.longitude, db)
        background_tasks.add_task(
            send_attendance_notification,
            user.email,
            user.first_name or user.username,
            str(today),
            record.check_out.strftime("%I:%M %p IST"),
            "Check-Out",
            user.language or "en",
            req.notes,
            record.latitude,
            record.longitude,
            compliance,
            dist,
        )

    return _with_username(record, db)


@router.get("/today", response_model=Optional[AttendanceResponse], status_code=status.HTTP_200_OK)
def get_today(
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's attendance record for today (or null)."""
    user_id = int(current_user["sub"])
    record = db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.date == get_ist_date(),
    ).first()
    if not record:
        return None
    return _with_username(record, db)


@router.get("/my", response_model=List[AttendanceResponse], status_code=status.HTTP_200_OK)
def get_my_history(
    db: db_dependency,
    limit: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's recent attendance history."""
    user_id = int(current_user["sub"])
    records = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.user_id == user_id)
        .order_by(AttendanceLog.date.desc())
        .limit(limit)
        .all()
    )
    return [_with_username(r, db) for r in records]


@router.get("/all", response_model=List[AttendanceResponse], status_code=status.HTTP_200_OK)
def get_all(
    db: db_dependency,
    target_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
):
    """Admin/Manager: get all attendance for a given date (defaults to today)."""
    role = current_user.get("role", "")
    if role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admins and managers only.")
    filter_date = target_date or get_ist_date()
    records = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.date == filter_date)
        .order_by(AttendanceLog.check_in.asc())
        .all()
    )
    return [_with_username(r, db) for r in records]


@router.get("/team-month", response_model=List[AttendanceResponse], status_code=status.HTTP_200_OK)
def get_team_month(
    year: int,
    month: int,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    """Admin/Manager: get all team attendance for a full calendar month."""
    role = current_user.get("role", "")
    user_id = int(current_user["sub"])
    if role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admins and managers only.")

    _, days_in_month = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, days_in_month)

    query = db.query(AttendanceLog).filter(
        AttendanceLog.date >= start,
        AttendanceLog.date <= end,
    )

    if role == "manager":
        # Only include the manager's direct subordinates + the manager themselves
        sub_ids = [r.id for r in db.query(Users.id).filter(Users.manager_id == user_id).all()]
        sub_ids.append(user_id)
        query = query.filter(AttendanceLog.user_id.in_(sub_ids))

    records = query.order_by(AttendanceLog.date.asc(), AttendanceLog.check_in.asc()).all()
    return [_with_username(r, db) for r in records]


# ── Helper ────────────────────────────────────────────────────────────────────

def _with_username(record: AttendanceLog, db: Session) -> dict:
    user = db.query(Users).options(load_only(Users.id, Users.username)).filter(Users.id == record.user_id).first()

    # Compute site compliance (within 10 km of any assigned site)
    site_compliance = None
    site_distance_km = None
    if record.latitude is not None and record.longitude is not None:
        # Get user's assigned sites with GPS coordinates
        assignments = (
            db.query(SiteAssignments)
            .filter(SiteAssignments.user_id == record.user_id)
            .all()
        )
        if not assignments:
            site_compliance = "no_site"
        else:
            site_ids = [a.site_id for a in assignments]
            sites = db.query(Sites).filter(
                Sites.id.in_(site_ids),
                Sites.latitude.isnot(None),
                Sites.longitude.isnot(None),
            ).all()
            if not sites:
                site_compliance = "no_site"
            else:
                distances = [
                    _haversine_km(record.latitude, record.longitude, s.latitude, s.longitude)
                    for s in sites
                ]
                min_dist = min(distances)
                site_distance_km = float(f"{min_dist:.2f}")
                site_compliance = "compliant" if min_dist <= _compliance_radius_km() else "non_compliant"
    else:
        site_compliance = "no_location"

    return {
        "id": record.id,
        "user_id": record.user_id,
        "username": user.username if user else None,
        "date": record.date,
        "check_in": record.check_in,
        "check_out": record.check_out,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "notes": record.notes,
        "site_compliance": site_compliance,
        "site_distance_km": site_distance_km,
    }
