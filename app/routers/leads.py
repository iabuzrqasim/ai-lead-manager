from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Activity, FollowUp, FollowUpStatus, Lead, LeadStatus
from app.schemas import ActivityCreate, ActivityOut, LeadCreate, LeadOut, LeadPage, LeadUpdate
from app.security import CurrentUser
from app.services.followups import cancel_open_follow_ups

router = APIRouter(prefix="/api/leads", tags=["leads"])
DB = Annotated[Session, Depends(get_db)]

SORT_COLUMNS = {
    "created_at": Lead.created_at,
    "updated_at": Lead.updated_at,
    "name": Lead.name,
    "company": Lead.company,
    "status": Lead.status,
    "estimated_value": Lead.estimated_value,
}


def get_lead_or_404(db: Session, lead_id: int) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


def _next_follow_up_map(db: Session, lead_ids: list[int]) -> dict[int, object]:
    if not lead_ids:
        return {}
    rows = db.execute(
        select(FollowUp.lead_id, func.min(FollowUp.scheduled_at))
        .where(FollowUp.lead_id.in_(lead_ids), FollowUp.status.in_([FollowUpStatus.PENDING, FollowUpStatus.DUE]))
        .group_by(FollowUp.lead_id)
    ).all()
    return dict(rows)


def to_out(lead: Lead, next_fu=None) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.next_follow_up = next_fu
    return out


@router.get("", response_model=LeadPage)
def list_leads(
    db: DB,
    _: CurrentUser,
    q: Annotated[str | None, Query(max_length=100, description="Search name, email or company")] = None,
    status_filter: Annotated[LeadStatus | None, Query(alias="status")] = None,
    source: Annotated[str | None, Query(max_length=60)] = None,
    sort: Literal["created_at", "updated_at", "name", "company", "status", "estimated_value"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    stmt = select(Lead)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Lead.name.ilike(like), Lead.email.ilike(like), Lead.company.ilike(like)))
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    if source:
        stmt = stmt.where(Lead.source == source)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORT_COLUMNS[sort]
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc(), Lead.id.desc())
    leads = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    next_map = _next_follow_up_map(db, [l.id for l in leads])
    return LeadPage(items=[to_out(l, next_map.get(l.id)) for l in leads], total=total, page=page, page_size=page_size)


@router.get("/sources", response_model=list[str])
def list_sources(db: DB, _: CurrentUser):
    return [s for s in db.scalars(select(Lead.source).distinct().order_by(Lead.source)) if s]


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(payload: LeadCreate, db: DB, user: CurrentUser):
    lead = Lead(**payload.model_dump())
    lead.email = lead.email.lower()
    db.add(lead)
    db.flush()
    db.add(Activity(lead_id=lead.id, kind="created", description=f"Lead created by {user.email}."))
    db.commit()
    db.refresh(lead)
    return to_out(lead)


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: DB, _: CurrentUser):
    lead = get_lead_or_404(db, lead_id)
    return to_out(lead, _next_follow_up_map(db, [lead.id]).get(lead.id))


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, payload: LeadUpdate, db: DB, user: CurrentUser):
    lead = get_lead_or_404(db, lead_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if "email" in changes and changes["email"] is None:
        raise HTTPException(status_code=422, detail="Email cannot be empty")

    old_status = lead.status
    for field, value in changes.items():
        setattr(lead, field, value.lower() if field == "email" and value else value)

    if "status" in changes and lead.status != old_status:
        db.add(Activity(lead_id=lead.id, kind="status_change",
                        description=f"Status changed from {old_status.value} to {lead.status.value}."))
        if lead.status in LeadStatus.closed():
            n = cancel_open_follow_ups(db, lead)
            if n:
                db.add(Activity(lead_id=lead.id, kind="follow_up",
                                description=f"{n} open follow-up(s) cancelled because lead is {lead.status.value}."))
    elif changes:
        db.add(Activity(lead_id=lead.id, kind="updated",
                        description=f"Updated {', '.join(sorted(changes))} ({user.email})."))
    db.commit()
    db.refresh(lead)
    return to_out(lead, _next_follow_up_map(db, [lead.id]).get(lead.id))


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lead(lead_id: int, db: DB, _: CurrentUser):
    lead = get_lead_or_404(db, lead_id)
    db.delete(lead)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{lead_id}/activities", response_model=list[ActivityOut])
def list_activities(lead_id: int, db: DB, _: CurrentUser):
    return get_lead_or_404(db, lead_id).activities


@router.post("/{lead_id}/activities", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def add_activity(lead_id: int, payload: ActivityCreate, db: DB, _: CurrentUser):
    get_lead_or_404(db, lead_id)
    activity = Activity(lead_id=lead_id, kind=payload.kind, description=payload.description.strip())
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity
