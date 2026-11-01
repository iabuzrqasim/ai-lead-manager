"""FastAPI application entry point.

Run locally:  fastapi dev app/main.py
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.routers import analytics, auth, emails, followups, leads
from app.security import ensure_admin_user
from app.services.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).parent / "static"
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_admin_user(db)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    description=f"Lead management and follow-up automation by {settings.company_name}",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(followups.router)
app.include_router(emails.router)
app.include_router(analytics.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": app.version}


PAGES = {"login": "login.html", "dashboard": "dashboard.html", "leads": "leads.html",
         "lead": "lead.html", "follow-ups": "followups.html"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard")


@app.get("/{page}", include_in_schema=False)
def page(page: str):
    filename = PAGES.get(page)
    if not filename:
        return FileResponse(STATIC_DIR / "404.html", status_code=404)
    return FileResponse(STATIC_DIR / filename)
