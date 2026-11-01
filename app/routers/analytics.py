from collections import OrderedDict
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FollowUp, FollowUpStatus, Lead, LeadStatus, utcnow
from app.schemas import DashboardStats
from app.security import CurrentUser

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def compute_stats(db: Session, months: int = 6) -> DashboardStats:
    now = utcnow()
    by_status = {s.value: 0 for s in LeadStatus}
    for st, count in db.execute(select(Lead.status, func.count()).group_by(Lead.status)).all():
        by_status[st.value] = count

    total = sum(by_status.values())
    won, lost = by_status[LeadStatus.WON.value], by_status[LeadStatus.LOST.value]
    closed = won + lost

    by_source = {
        (src or "Unknown"): n
        for src, n in db.execute(select(Lead.source, func.count()).group_by(Lead.source).order_by(func.count().desc()))
    }

    pipeline_value = db.scalar(
        select(func.coalesce(func.sum(Lead.estimated_value), 0)).where(Lead.status.not_in(LeadStatus.closed()))
    )
    won_value = db.scalar(select(func.coalesce(func.sum(Lead.estimated_value), 0)).where(Lead.status == LeadStatus.WON))

    # Leads created per month (last N months, zero-filled), computed in Python for DB portability.
    buckets: OrderedDict[str, int] = OrderedDict()
    y, m = now.year, now.month
    for _ in range(months):
        buckets[f"{y:04d}-{m:02d}"] = 0
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    buckets = OrderedDict(reversed(list(buckets.items())))
    start = now - timedelta(days=31 * months)
    for (created,) in db.execute(select(Lead.created_at).where(Lead.created_at >= start)):
        key = f"{created.year:04d}-{created.month:02d}"
        if key in buckets:
            buckets[key] += 1

    def count_fu(*conds) -> int:
        return db.scalar(select(func.count()).select_from(FollowUp).where(*conds)) or 0

    open_states = (FollowUpStatus.PENDING, FollowUpStatus.DUE)
    return DashboardStats(
        total_leads=total,
        open_leads=total - closed,
        won=won,
        lost=lost,
        conversion_rate=round(won / closed * 100, 1) if closed else 0.0,
        win_rate_overall=round(won / total * 100, 1) if total else 0.0,
        pipeline_value=float(pipeline_value or 0),
        won_value=float(won_value or 0),
        by_status=by_status,
        by_source=by_source,
        leads_per_month=[{"month": k, "count": v} for k, v in buckets.items()],
        upcoming_follow_ups=count_fu(FollowUp.status == FollowUpStatus.PENDING, FollowUp.scheduled_at > now,
                                     FollowUp.scheduled_at <= now + timedelta(days=7)),
        overdue_follow_ups=count_fu(FollowUp.status.in_(open_states), FollowUp.scheduled_at <= now),
        due_follow_ups=count_fu(FollowUp.status == FollowUpStatus.DUE),
    )


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Annotated[Session, Depends(get_db)], _: CurrentUser):
    return compute_stats(db)
