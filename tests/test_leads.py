def test_create_lead(client, make_lead):
    lead = make_lead(email="Ayesha@Example.com")
    assert lead["id"] > 0
    assert lead["status"] == "New"
    assert lead["email"] == "ayesha@example.com"  # normalised


def test_create_lead_validation(client):
    r = client.post("/api/leads", json={"name": "A", "email": "not-an-email"})
    assert r.status_code == 422


def test_invalid_status_rejected(client, make_lead):
    lead = make_lead()
    r = client.patch(f"/api/leads/{lead['id']}", json={"status": "Maybe"})
    assert r.status_code == 422


def test_get_update_delete(client, make_lead):
    lead = make_lead()
    lid = lead["id"]
    assert client.get(f"/api/leads/{lid}").json()["name"] == "Ayesha Khan"

    r = client.patch(f"/api/leads/{lid}", json={"status": "Contacted", "estimated_value": 1500})
    assert r.status_code == 200
    assert r.json()["status"] == "Contacted"
    assert r.json()["estimated_value"] == 1500

    kinds = [a["kind"] for a in client.get(f"/api/leads/{lid}/activities").json()]
    assert "status_change" in kinds

    assert client.delete(f"/api/leads/{lid}").status_code == 204
    assert client.get(f"/api/leads/{lid}").status_code == 404


def test_missing_lead_404(client):
    assert client.get("/api/leads/9999").status_code == 404
    assert client.patch("/api/leads/9999", json={"name": "Xyz"}).status_code == 404


def test_search_filter_and_pagination(client, make_lead):
    make_lead(name="Ali Raza", email="ali@x.com", company="Bright Ltd", source="LinkedIn")
    make_lead(name="Sara Ahmed", email="sara@y.com", company="Nova Foods", source="Website", status="Won")
    make_lead(name="Bilal Shah", email="bilal@z.com", company="Bright Ltd", source="Referral")

    r = client.get("/api/leads", params={"q": "bright"}).json()
    assert r["total"] == 2

    r = client.get("/api/leads", params={"status": "Won"}).json()
    assert [l["name"] for l in r["items"]] == ["Sara Ahmed"]

    r = client.get("/api/leads", params={"source": "LinkedIn"}).json()
    assert r["total"] == 1

    r = client.get("/api/leads", params={"page_size": 2, "page": 2, "sort": "name", "order": "asc"}).json()
    assert r["total"] == 3 and len(r["items"]) == 1
    assert r["items"][0]["name"] == "Sara Ahmed"
