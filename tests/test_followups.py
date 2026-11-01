from datetime import timedelta

from sqlalchemy import select

from app.models import EmailDraft, FollowUp, FollowUpStatus, utcnow
from app.services.followups import process_due_follow_ups


def _schedule(client, lead_id, delta, **extra):
    when = (utcnow() + delta).isoformat()
    return client.post(f"/api/leads/{lead_id}/follow-ups", json={"scheduled_at": when, **extra})


def test_schedule_and_list(client, make_lead):
    lead = make_lead()
    r = _schedule(client, lead["id"], timedelta(days=2), channel="call", note="Discuss proposal")
    assert r.status_code == 201
    assert r.json()["status"] == "Pending"
    assert len(client.get("/api/follow-ups", params={"view": "upcoming"}).json()) == 1
    assert client.get(f"/api/leads/{lead['id']}").json()["next_follow_up"] is not None


def test_invalid_channel(client, make_lead):
    lead = make_lead()
    assert _schedule(client, lead["id"], timedelta(days=1), channel="pigeon").status_code == 422


def test_due_follow_up_processed_once(client, make_lead, db):
    lead = make_lead()
    _schedule(client, lead["id"], timedelta(minutes=-5))
    _schedule(client, lead["id"], timedelta(days=3))  # not due yet

    first = process_due_follow_ups(db)
    second = process_due_follow_ups(db)  # duplicate run must do nothing
    assert len(first) == 1
    assert second == []

    drafts = db.scalars(select(EmailDraft).where(EmailDraft.lead_id == lead["id"])).all()
    assert len(drafts) == 1
    statuses = sorted(f.status for f in db.scalars(select(FollowUp)).all())
    assert statuses == sorted([FollowUpStatus.DUE, FollowUpStatus.PENDING])


def test_concurrent_claim_only_once(client, make_lead):
    """Two sessions racing for the same due follow-up: only one wins."""
    from app.database import SessionLocal

    lead = make_lead()
    _schedule(client, lead["id"], timedelta(minutes=-1))
    s1, s2 = SessionLocal(), SessionLocal()
    try:
        results = process_due_follow_ups(s1) + process_due_follow_ups(s2)
    finally:
        s1.close()
        s2.close()
    assert len(results) == 1


def test_closed_leads_excluded(client, make_lead, db):
    lead = make_lead()
    _schedule(client, lead["id"], timedelta(days=1))
    client.patch(f"/api/leads/{lead['id']}", json={"status": "Won"})

    fus = client.get(f"/api/leads/{lead['id']}/follow-ups").json()
    assert [f["status"] for f in fus] == ["Cancelled"]
    assert _schedule(client, lead["id"], timedelta(days=1)).status_code == 409


def test_scheduler_cancels_followup_if_lead_closed(client, make_lead, db):
    lead = make_lead()
    r = _schedule(client, lead["id"], timedelta(minutes=-1))
    # Close the lead directly in the DB, bypassing the API's auto-cancel.
    from app.models import Lead, LeadStatus

    db.get(Lead, lead["id"]).status = LeadStatus.LOST
    db.commit()
    assert process_due_follow_ups(db) == []
    db.expire_all()
    assert db.get(FollowUp, r.json()["id"]).status == FollowUpStatus.CANCELLED


def test_complete_and_cancel(client, make_lead):
    lead = make_lead()
    a = _schedule(client, lead["id"], timedelta(days=1)).json()
    b = _schedule(client, lead["id"], timedelta(days=2)).json()
    assert client.post(f"/api/follow-ups/{a['id']}/complete").json()["status"] == "Completed"
    assert client.post(f"/api/follow-ups/{b['id']}/cancel").json()["status"] == "Cancelled"
    assert client.post(f"/api/follow-ups/{a['id']}/cancel").status_code == 409
