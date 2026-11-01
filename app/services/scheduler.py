"""APScheduler setup: runs the follow-up check in the background."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.database import SessionLocal
from app.services.followups import process_due_follow_ups

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def run_follow_up_job() -> None:
    db = SessionLocal()
    try:
        process_due_follow_ups(db)
    except Exception:  # never let the background thread die
        logger.exception("Follow-up job failed")
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> None:
    """Start the scheduler. Run the app with ONE worker, or set
    SCHEDULER_ENABLED=false on all but one instance."""
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_follow_up_job,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="process_due_follow_ups",
        max_instances=1,  # never overlap with itself
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Follow-up scheduler started (every %ss)", settings.scheduler_interval_seconds)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
