from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Activity, DraftStatus, EmailDraft, FollowUp, utcnow
from app.routers.leads import get_lead_or_404
from app.schemas import DraftGenerate, DraftOut, DraftUpdate
from app.security import CurrentUser
from app.services.ai import generate_draft
from app.services.email_sender import send_email

router = APIRouter(prefix="/api", tags=["emails"])
DB = Annotated[Session, Depends(get_db)]


def get_draft_or_404(db: Session, draft_id: int) -> EmailDraft:
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft


@router.get("/email/config")
def email_config(_: CurrentUser):
    s = get_settings()
    return {
        "ai_enabled": s.ai_enabled,
        "sending_enabled": s.email_sending_enabled,
        "test_inbox": s.email_test_inbox or None,
    }


@router.get("/leads/{lead_id}/drafts", response_model=list[DraftOut])
def list_drafts(lead_id: int, db: DB, _: CurrentUser):
    return get_lead_or_404(db, lead_id).email_drafts


@router.post("/leads/{lead_id}/drafts/generate", status_code=status.HTTP_201_CREATED)
def generate(lead_id: int, payload: DraftGenerate, db: DB, _: CurrentUser):
    lead = get_lead_or_404(db, lead_id)
    if payload.follow_up_id is not None:
        fu = db.get(FollowUp, payload.follow_up_id)
        if not fu or fu.lead_id != lead.id:
            raise HTTPException(status_code=404, detail="Follow-up not found for this lead")
    result = generate_draft(lead, payload.purpose, payload.extra_context)
    draft = EmailDraft(lead_id=lead.id, follow_up_id=payload.follow_up_id, subject=result.subject,
                       body=result.body, generated_by=result.generated_by)
    db.add(draft)
    db.add(Activity(lead_id=lead.id, kind="email",
                    description=f"Email draft generated ({result.generated_by})."))
    db.commit()
    db.refresh(draft)
    return {"draft": DraftOut.model_validate(draft), "warning": result.warning}


@router.put("/drafts/{draft_id}", response_model=DraftOut)
def update_draft(draft_id: int, payload: DraftUpdate, db: DB, _: CurrentUser):
    draft = get_draft_or_404(db, draft_id)
    if draft.status == DraftStatus.SENT:
        raise HTTPException(status_code=409, detail="A sent email cannot be edited")
    draft.subject, draft.body = payload.subject.strip(), payload.body.strip()
    if draft.generated_by != "manual":
        draft.generated_by = f"{draft.generated_by}+edited" if "+edited" not in draft.generated_by else draft.generated_by
    db.commit()
    db.refresh(draft)
    return draft


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(draft_id: int, db: DB, _: CurrentUser):
    draft = get_draft_or_404(db, draft_id)
    if draft.status == DraftStatus.SENT:
        raise HTTPException(status_code=409, detail="Sent emails are kept as a record")
    db.delete(draft)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/drafts/{draft_id}/send", response_model=DraftOut)
def send_draft(draft_id: int, db: DB, user: CurrentUser):
    """Send one reviewed draft. Only ever triggered manually by a user."""
    draft = get_draft_or_404(db, draft_id)
    if draft.status == DraftStatus.SENT:
        raise HTTPException(status_code=409, detail="This draft was already sent")
    result = send_email(draft.lead.email, draft.subject, draft.body)
    if result.ok:
        draft.status, draft.sent_to, draft.sent_at, draft.error = DraftStatus.SENT, result.recipient, utcnow(), None
        db.add(Activity(lead_id=draft.lead_id, kind="email",
                        description=f"Email '{draft.subject}' sent to {result.recipient} by {user.email}."))
    else:
        draft.status, draft.error = DraftStatus.FAILED, result.error
        db.add(Activity(lead_id=draft.lead_id, kind="email", description=f"Email sending failed: {result.error}"))
    db.commit()
    db.refresh(draft)
    if not result.ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error)
    return draft
