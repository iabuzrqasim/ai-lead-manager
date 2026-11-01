import httpx

from app.config import get_settings


def test_template_draft_without_api_key(client, make_lead):
    lead = make_lead(name="Hamza Ali")
    r = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={})
    assert r.status_code == 201
    draft = r.json()["draft"]
    assert draft["generated_by"] == "template"
    assert draft["body"].startswith("Hi Hamza")


def test_ai_failure_falls_back_to_template(client, make_lead, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "fake-key")

    def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr("app.services.ai.httpx.post", boom)
    lead = make_lead()
    r = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={"purpose": "follow-up"}).json()
    assert r["draft"]["generated_by"] == "template"
    assert r["warning"]


def test_ai_success(client, make_lead, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "fake-key")

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": '{"subject": "Quick check-in", "body": "Hi Ayesha, ..."}'}]}

    monkeypatch.setattr("app.services.ai.httpx.post", lambda *a, **k: Resp())
    lead = make_lead()
    draft = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={}).json()["draft"]
    assert draft["generated_by"] == "ai"
    assert draft["subject"] == "Quick check-in"


def test_edit_draft(client, make_lead):
    lead = make_lead()
    draft = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={}).json()["draft"]
    r = client.put(f"/api/drafts/{draft['id']}", json={"subject": "New subject", "body": "New body"})
    assert r.json()["subject"] == "New subject"
    assert r.json()["generated_by"] == "template+edited"


def test_sending_disabled_by_default(client, make_lead):
    lead = make_lead()
    draft = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={}).json()["draft"]
    r = client.post(f"/api/drafts/{draft['id']}/send")
    assert r.status_code == 502
    assert "disabled" in r.json()["detail"]
    drafts = client.get(f"/api/leads/{lead['id']}/drafts").json()
    assert drafts[0]["status"] == "Failed"


def test_send_redirects_to_test_inbox(client, make_lead, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "email_sending_enabled", True)
    monkeypatch.setattr(s, "smtp_host", "smtp.test")
    monkeypatch.setattr(s, "smtp_from", "bot@technestnova.com")
    monkeypatch.setattr(s, "email_test_inbox", "inbox@test.com")
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, **k):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg["To"])

    monkeypatch.setattr("app.services.email_sender.smtplib.SMTP", FakeSMTP)
    lead = make_lead(email="real.client@company.com")
    draft = client.post(f"/api/leads/{lead['id']}/drafts/generate", json={}).json()["draft"]
    r = client.post(f"/api/drafts/{draft['id']}/send")
    assert r.status_code == 200
    assert sent == ["inbox@test.com"]
    assert client.post(f"/api/drafts/{draft['id']}/send").status_code == 409  # no double send
