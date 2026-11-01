import os

# Configure a clean, isolated environment BEFORE the app is imported.
os.environ.update(
    DATABASE_URL="sqlite://",
    SCHEDULER_ENABLED="false",
    SECRET_KEY="test-secret-key-that-is-long-enough-123456",
    ADMIN_EMAIL="admin@test.com",
    ADMIN_PASSWORD="password123",
    ANTHROPIC_API_KEY="",
    EMAIL_SENDING_ENABLED="false",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import ensure_admin_user  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin_user(db)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        token = c.post("/api/auth/login", data={"username": "admin@test.com", "password": "password123"}).json()
        c.headers["Authorization"] = f"Bearer {token['access_token']}"
        yield c


@pytest.fixture
def make_lead(client):
    def _make(**overrides):
        payload = {"name": "Ayesha Khan", "email": "ayesha@example.com", "company": "Acme", "source": "Website"}
        payload.update(overrides)
        r = client.post("/api/leads", json=payload)
        assert r.status_code == 201, r.text
        return r.json()

    return _make
