from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Activity, FollowUp, FollowUpStatus, Lead, LeadStatus, utcnow
from app.routers.leads import get_lead_or_404
from app.schemas import FollowUpCreate, FollowUpOut, FollowUpUpdate
from app.security import CurrentUser
from app.services.followups import process_due_follow_ups

router = APIRouter(prefix="/api", tags=["follow-ups"])
DB = Annotated[Session, Depends(get_db)]
OPEN = (FollowUpStatus.PENDING, FollowUpStatus.DUE)


def to_out(fu: FollowUp) -> FollowUpOut:
    out = FollowUpOut.model_validate(fu)
    out.lead_name = fu.lead.name
    out.lead_company = fu.lead.company
    return out


def _naive_utc(dt):
    """Store all datetimes as naive UTC."""
    if dt.tzinfo is not None:
        from datetime import UTC
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def get_follow_up_or_404(db: Session, fu_id: int) -> FollowUp:
    fu = db.get(FollowUp, fu_id)
    if not fu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up not found")
    return fu


@router.get("/follow-ups", response_model=list[FollowUpOut])
def list_follow_ups(
    db: DB,
    _: CurrentUser,
    view: Literal["all", "open", "upcoming", "overdue", "due", "completed", "cancelled"] = "open",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    now = utcnow()
    stmt = select(FollowUp).options(joinedload(FollowUp.lead))
    if view == "open":
        stmt = stmt.where(FollowUp.status.in_(OPEN))
    elif view == "upcoming":
        stmt = stmt.where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.scheduled_at > now)
    elif view == "overdue":
        stmt = stmt.where(FollowUp.status.in_(OPEN), FollowUp.scheduled_at <= now)
    elif view == "due":
        stmt = stmt.where(FollowUp.status == FollowUpStatus.DUE)
    elif view == "completed":
        stmt = stmt.where(FollowUp.status == FollowUpStatus.COMPLETED)
    elif view == "cancelled":
        stmt = stmt.where(FollowUp.status == FollowUpStatus.CANCELLED)
    order = FollowUp.scheduled_at.desc() if view in ("completed", "cancelled", "all") else FollowUp.scheduled_at.asc()
    return [to_out(f) for f in db.scalars(stmt.order_by(order).limit(limit)).all()]


@router.get("/leads/{lead_id}/follow-ups", response_model=list[FollowUpOut])
def lead_follow_ups(lead_id: int, db: DB, _: CurrentUser):
    return [to_out(f) for f in get_lead_or_404(db, lead_id).follow_ups]


@router.post("/leads/{lead_id}/follow-ups", response_model=FollowUpOut, status_code=status.HTTP_201_CREATED)
def create_follow_up(lead_id: int, payload: FollowUpCreate, db: DB, _: CurrentUser):
    lead = get_lead_or_404(db, lead_id)
    if lead.status in LeadStatus.closed():
        raise HTTPException(status_code=409, detail=f"Cannot schedule follow-ups for a {lead.status.value} lead")
    fu = FollowUp(lead_id=lead.id, scheduled_at=_naive_utc(payload.scheduled_at),
                  channel=payload.channel, note=payload.note)
    db.add(fu)
    db.add(Activity(lead_id=lead.id, kind="follow_up",
                    description=f"Follow-up scheduled ({payload.channel}) for {fu.scheduled_at:%Y-%m-%d %H:%M} UTC."))
    db.commit()
    db.refresh(fu)
    return to_out(fu)


@router.patch("/follow-ups/{fu_id}", response_model=FollowUpOut)
def update_follow_up(fu_id: int, payload: FollowUpUpdate, db: DB, _: CurrentUser):
    fu = get_follow_up_or_404(db, fu_id)
    if fu.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"Follow-up is already {fu.status.value}")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("scheduled_at"):
        fu.scheduled_at = _naive_utc(changes.pop("scheduled_at"))
        fu.status, fu.processed_at = FollowUpStatus.PENDING, None  # rescheduled
    for k, v in changes.items():
        if v is not None:
            setattr(fu, k, v)
    db.commit()
    db.refresh(fu)
    return to_out(fu)


def _close(db: Session, fu_id: int, new_status: FollowUpStatus) -> FollowUp:
    fu = get_follow_up_or_404(db, fu_id)
    if fu.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"Follow-up is already {fu.status.value}")
    fu.status = new_status
    fu.completed_at = utcnow()
    db.add(Activity(lead_id=fu.lead_id, kind="follow_up",
                    description=f"Follow-up ({fu.channel}) marked {new_status.value.lower()}."))
    db.commit()
    db.refresh(fu)
    return fu


@router.post("/follow-ups/{fu_id}/complete", response_model=FollowUpOut)
def complete_follow_up(fu_id: int, db: DB, _: CurrentUser):
    return to_out(_close(db, fu_id, FollowUpStatus.COMPLETED))


@router.post("/follow-ups/{fu_id}/cancel", response_model=FollowUpOut)
def cancel_follow_up(fu_id: int, db: DB, _: CurrentUser):
    return to_out(_close(db, fu_id, FollowUpStatus.CANCELLED))


@router.post("/follow-ups/run-now", response_model=dict)
def run_now(db: DB, _: CurrentUser):
    """Run the scheduler job immediately (handy for demos)."""
    return {"processed": process_due_follow_ups(db)}
