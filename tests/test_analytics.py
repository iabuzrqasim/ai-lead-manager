from datetime import timedelta

from app.models import utcnow


def test_empty_dashboard(client):
    s = client.get("/api/analytics/dashboard").json()
    assert s["total_leads"] == 0
    assert s["conversion_rate"] == 0
    assert len(s["leads_per_month"]) == 6


def test_dashboard_calculations(client, make_lead):
    make_lead(email="a@x.com", status="Won", estimated_value=1000)
    make_lead(email="b@x.com", status="Won", estimated_value=500)
    make_lead(email="c@x.com", status="Lost", estimated_value=300)
    open_lead = make_lead(email="d@x.com", status="Qualified", estimated_value=2000, source="LinkedIn")

    client.post(f"/api/leads/{open_lead['id']}/follow-ups",
                json={"scheduled_at": (utcnow() + timedelta(days=2)).isoformat()})
    client.post(f"/api/leads/{open_lead['id']}/follow-ups",
                json={"scheduled_at": (utcnow() - timedelta(days=1)).isoformat()})

    s = client.get("/api/analytics/dashboard").json()
    assert s["total_leads"] == 4
    assert s["open_leads"] == 1
    assert s["by_status"]["Won"] == 2
    assert s["conversion_rate"] == 66.7  # 2 won / 3 closed
    assert s["win_rate_overall"] == 50.0
    assert s["pipeline_value"] == 2000
    assert s["won_value"] == 1500
    assert s["by_source"]["LinkedIn"] == 1
    assert s["upcoming_follow_ups"] == 1
    assert s["overdue_follow_ups"] == 1
    assert s["leads_per_month"][-1]["count"] == 4
