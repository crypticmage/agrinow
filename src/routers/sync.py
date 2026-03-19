"""Sync endpoints for WatermelonDB offline support."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette import status
from datetime import datetime, timezone
from datetime import date as date_type
import time, logging

from routers.attendance import _compute_compliance
from utils.timezone import get_ist_now
from fastapi.responses import JSONResponse

from database.database import SessionLocal
from models import AttendanceLog, Sites, SiteAssignments, SiteComments
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _att_dict(r):
    return {
        "id": r.local_id or str(r.id), "server_id": str(r.id),
        "user_id": r.user_id,
        "work_date": r.date.isoformat() if r.date else None,
        "check_in":  r.check_in.isoformat()  if r.check_in  else None,
        "check_out": r.check_out.isoformat()  if r.check_out else None,
        "latitude": r.latitude, "longitude": r.longitude,
        "notes": r.notes or "", "site_compliance": r.site_compliance or "pending",
    }

def _site_dict(r):
    return {
        "id": r.local_id or str(r.id), "server_id": str(r.id),
        "site_name": r.site_name or "", "site_description": r.site_description or "",
        "latitude": r.latitude, "longitude": r.longitude,
        "created_date": r.created_date.isoformat() if r.created_date else None,
        "close_date":   r.close_date.isoformat()   if r.close_date   else None,
    }

def _asgn_dict(r):
    return {
        "id": r.local_id or str(r.id), "server_id": str(r.id),
        "user_id": r.user_id, "site_server_id": str(r.site_id),
        "assigned_date": r.assigned_date.isoformat() if r.assigned_date else None,
    }

def _cmt_dict(r):
    return {
        "id": r.local_id or str(r.id), "server_id": str(r.id),
        "site_user_relation_id": r.site_user_relation_id,
        "user_id": r.user_id, "comment": r.comment or "",
        "type": r.type or "text",
        "comment_timestamp": r.timestamp.isoformat() if r.timestamp else None,
    }


def _split(rows, is_full_sync: bool):
    """Split rows into (created, updated) for WatermelonDB sync protocol.

    Full sync (lastPulledAt=0): ALL rows -> created (client has never seen them).
    Delta sync: rows without local_id (new, never pushed by a client) -> created;
                rows with local_id (previously pushed) -> updated.
    """
    if is_full_sync:
        return rows, []
    created = [r for r in rows if r.local_id is None]
    updated  = [r for r in rows if r.local_id is not None]
    return created, updated


@router.get("/pull", status_code=status.HTTP_200_OK)
async def sync_pull(
    db: db_dependency,
    lastPulledAt: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
):

    now_ms = int(time.time() * 1000)
    user_id = int(current_user["sub"])
    is_full = (lastPulledAt == 0)
    from_dt = _ms_to_dt(lastPulledAt) if not is_full else datetime(2000, 1, 1, tzinfo=timezone.utc)

    # attendance_logs
    att = db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.updated_at > from_dt,
        AttendanceLog.deleted_at.is_(None),
    ).all()
    att_del = [r.local_id for r in db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.deleted_at > from_dt,
        AttendanceLog.local_id.isnot(None),
    ).all()]
    att_c, att_u = _split(att, is_full)

    # sites (all public reference data)
    sites = db.query(Sites).filter(
        Sites.updated_at > from_dt, Sites.deleted_at.is_(None),
    ).all()
    sites_del = [r.local_id for r in db.query(Sites).filter(
        Sites.deleted_at > from_dt, Sites.local_id.isnot(None),
    ).all()]
    sites_c, sites_u = _split(sites, is_full)

    # site_assignments
    asgn = db.query(SiteAssignments).filter(
        SiteAssignments.user_id == user_id,
        SiteAssignments.updated_at > from_dt,
        SiteAssignments.deleted_at.is_(None),
    ).all()
    asgn_del = [r.local_id for r in db.query(SiteAssignments).filter(
        SiteAssignments.user_id == user_id,
        SiteAssignments.deleted_at > from_dt,
        SiteAssignments.local_id.isnot(None),
    ).all()]
    asgn_c, asgn_u = _split(asgn, is_full)

    # site_comments scoped to user's assigned sites
    user_asgn_ids = [a.id for a in db.query(SiteAssignments).filter(
        SiteAssignments.user_id == user_id,
    ).all()]
    if user_asgn_ids:
        cmts = db.query(SiteComments).filter(
            SiteComments.site_user_relation_id.in_(user_asgn_ids),
            SiteComments.updated_at > from_dt,
            SiteComments.deleted_at.is_(None),
        ).all()
        cmts_del = [r.local_id for r in db.query(SiteComments).filter(
            SiteComments.site_user_relation_id.in_(user_asgn_ids),
            SiteComments.deleted_at > from_dt,
            SiteComments.local_id.isnot(None),
        ).all()]
    else:
        cmts, cmts_del = [], []
    cmts_c, cmts_u = _split(cmts, is_full)

    return {
        "changes": {
            "attendance_logs":  {"created": [_att_dict(r)  for r in att_c],   "updated": [_att_dict(r)  for r in att_u],   "deleted": [d for d in att_del   if d]},
            "sites":            {"created": [_site_dict(r) for r in sites_c], "updated": [_site_dict(r) for r in sites_u], "deleted": [d for d in sites_del if d]},
            "site_assignments": {"created": [_asgn_dict(r) for r in asgn_c],  "updated": [_asgn_dict(r) for r in asgn_u],  "deleted": [d for d in asgn_del  if d]},
            "site_comments":    {"created": [_cmt_dict(r)  for r in cmts_c],  "updated": [_cmt_dict(r)  for r in cmts_u],  "deleted": [d for d in cmts_del  if d]},
        },
        "timestamp": now_ms,
    }


@router.post("/push", status_code=status.HTTP_200_OK)
async def sync_push(
    body: dict,
    db: db_dependency,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["sub"])
    changes = body.get("changes", {})
    errors: list[dict] = []
    accepted = 0

    att = changes.get("attendance_logs", {})

    for rec in att.get("created", []):
        row = None
        try:
            work_date = date_type.fromisoformat(rec["work_date"])
            exists = db.query(AttendanceLog).filter(
                AttendanceLog.user_id == user_id,
                AttendanceLog.date    == work_date,
            ).first()
            if exists:
                errors.append({"local_id": rec.get("id"), "table": "attendance_logs",
                               "detail": f"Check-in for {work_date} already exists."})
                continue
            compliance, _ = _compute_compliance(user_id, rec.get("latitude"), rec.get("longitude"), db)
            row = AttendanceLog(
                user_id=user_id, date=work_date,
                check_in=datetime.fromisoformat(rec["check_in"]) if rec.get("check_in") else None,
                check_out=datetime.fromisoformat(rec["check_out"]) if rec.get("check_out") else None,
                latitude=rec.get("latitude"), longitude=rec.get("longitude"),
                notes=rec.get("notes", ""), site_compliance=compliance,
                local_id=rec.get("id"),
            )
            db.add(row)
            db.flush()
            accepted += 1
        except Exception as e:
            if row is not None:
                try:
                    db.expunge(row)
                except Exception:
                    pass
            errors.append({"local_id": rec.get("id"), "table": "attendance_logs", "detail": str(e)})

    for rec in att.get("updated", []):
        try:
            row = db.query(AttendanceLog).filter(
                AttendanceLog.local_id == rec.get("id"),
                AttendanceLog.user_id  == user_id,
            ).first()
            if not row:
                errors.append({"local_id": rec.get("id"), "table": "attendance_logs",
                               "detail": "Record not found."})
                continue
            if rec.get("check_out"):
                row.check_out = datetime.fromisoformat(rec["check_out"])
            if rec.get("notes"):
                row.notes = rec["notes"]
            compliance, _ = _compute_compliance(user_id, row.latitude, row.longitude, db)
            row.site_compliance = compliance
            row.updated_at = datetime.now(timezone.utc)
            db.flush()
            accepted += 1
        except Exception as e:
            errors.append({"local_id": rec.get("id"), "table": "attendance_logs", "detail": str(e)})

    # attendance_logs.deleted intentionally ignored

    cmt = changes.get("site_comments", {})

    for rec in cmt.get("created", []):
        row = None
        try:
            rel_id = rec.get("site_user_relation_id")
            if rel_id is None:
                errors.append({"local_id": rec.get("id"), "table": "site_comments",
                               "detail": "site_user_relation_id is required."})
                continue
            asgn_row = db.query(SiteAssignments).filter(
                SiteAssignments.id == rel_id,
                SiteAssignments.user_id == user_id,
            ).first()
            if not asgn_row:
                errors.append({"local_id": rec.get("id"), "table": "site_comments",
                               "detail": "site_user_relation_id does not belong to this user."})
                continue
            row = SiteComments(
                site_user_relation_id=rel_id,
                user_id=user_id, comment=rec.get("comment",""),
                type=rec.get("type","text"),
                timestamp=datetime.fromisoformat(rec["comment_timestamp"]) if rec.get("comment_timestamp") else get_ist_now(),
                local_id=rec.get("id"),
            )
            db.add(row)
            db.flush()
            accepted += 1
        except Exception as e:
            if row is not None:
                try:
                    db.expunge(row)
                except Exception:
                    pass
            errors.append({"local_id": rec.get("id"), "table": "site_comments", "detail": str(e)})

    for rec in cmt.get("updated", []):
        try:
            row = db.query(SiteComments).filter(
                SiteComments.local_id == rec.get("id"),
                SiteComments.user_id  == user_id,
            ).first()
            if not row:
                errors.append({"local_id": rec.get("id"), "table": "site_comments",
                               "detail": "Record not found."})
                continue
            row.comment = rec.get("comment", row.comment)
            row.updated_at = datetime.now(timezone.utc)
            db.flush()
            accepted += 1
        except Exception as e:
            errors.append({"local_id": rec.get("id"), "table": "site_comments", "detail": str(e)})

    for lid in cmt.get("deleted", []):
        try:
            row = db.query(SiteComments).filter(
                SiteComments.local_id == lid,
                SiteComments.user_id  == user_id,
            ).first()
            if row:
                row.deleted_at = datetime.now(timezone.utc)
                row.updated_at = datetime.now(timezone.utc)
                db.flush()
        except Exception as e:
            errors.append({"local_id": lid, "table": "site_comments", "detail": str(e)})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB commit failed: {e}")

    if errors:
        return JSONResponse(status_code=207, content={"accepted": accepted, "errors": errors})
    return {"accepted": accepted, "errors": []}
