from fastapi.testclient import TestClient

from app.main import app


def test_health_is_public():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"


def test_api_requires_login():
    with TestClient(app) as c:
        assert c.get("/api/leads").status_code == 401


def test_wrong_password_rejected():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", data={"username": "admin@test.com", "password": "nope"})
        assert r.status_code == 401


def test_login_and_me(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "admin@test.com"


def test_invalid_token_rejected():
    with TestClient(app) as c:
        r = c.get("/api/leads", headers={"Authorization": "Bearer not-a-token"})
        assert r.status_code == 401
