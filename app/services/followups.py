"""Follow-up automation: find due follow-ups and process each exactly once."""

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Activity, EmailDraft, FollowUp, FollowUpStatus, Lead, LeadStatus, utcnow
from app.services.ai import generate_draft

logger = logging.getLogger(__name__)


def process_due_follow_ups(db: Session) -> list[int]:
    """Mark every pending follow-up whose time has passed as Due.

    Duplicate protection: each row is claimed with a conditional UPDATE
    (`WHERE status = 'Pending'`). If two scheduler runs overlap, only one
    UPDATE matches the row, so only one run creates the draft.

    Follow-ups for Won/Lost leads are cancelled instead of processed.
    Returns the ids that this run processed.
    """
    now = utcnow()
    candidates = db.scalars(
        select(FollowUp.id).where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.scheduled_at <= now)
    ).all()

    processed: list[int] = []
    for fu_id in candidates:
        fu = db.get(FollowUp, fu_id)
        if fu is None:
            continue
        lead = fu.lead
        closed = lead.status in LeadStatus.closed()
        new_status = FollowUpStatus.CANCELLED if closed else FollowUpStatus.DUE

        claimed = db.execute(
            update(FollowUp)
            .where(FollowUp.id == fu_id, FollowUp.status == FollowUpStatus.PENDING)
            .values(status=new_status, processed_at=now)
        ).rowcount
        if claimed != 1:
            db.rollback()
            continue  # another worker already took it

        if closed:
            db.add(Activity(lead_id=lead.id, kind="follow_up",
                            description=f"Follow-up auto-cancelled: lead is {lead.status.value}."))
        else:
            draft = generate_draft(lead, purpose="follow-up", extra_context=fu.note)
            db.add(EmailDraft(lead_id=lead.id, follow_up_id=fu.id, subject=draft.subject,
                              body=draft.body, generated_by=draft.generated_by))
            db.add(Activity(lead_id=lead.id, kind="follow_up",
                            description=f"Follow-up due ({fu.channel}). Draft email prepared for review."))
            processed.append(fu_id)
        db.commit()

    if processed:
        logger.info("Processed %d due follow-up(s): %s", len(processed), processed)
    return processed


def cancel_open_follow_ups(db: Session, lead: Lead) -> int:
    """Cancel all pending/due follow-ups of a lead (used when it becomes Won/Lost)."""
    count = 0
    for fu in lead.follow_ups:
        if fu.status in (FollowUpStatus.PENDING, FollowUpStatus.DUE):
            fu.status = FollowUpStatus.CANCELLED
            fu.completed_at = utcnow()
            count += 1
    return count
