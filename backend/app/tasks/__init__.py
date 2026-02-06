"""Celery app factory and beat schedule."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "builder_leads",
    broker=settings.redis_url,
    backend=settings.database_url,
    include=[
        "app.tasks.daily_sync",
        "app.tasks.process_lead",
        "app.tasks.send_reports",
        "app.tasks.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/London",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,
    task_routes={
        "daily_planning_sync": {"queue": "sync"},
        "process_lead": {"queue": "processing"},
        "send_daily_summary": {"queue": "reports"},
        "send_weekly_report": {"queue": "reports"},
        "cleanup_old_data": {"queue": "maintenance"},
    },
)

celery_app.conf.beat_schedule = {
    "daily-planning-sync": {
        "task": "daily_planning_sync",
        "schedule": crontab(hour=6, minute=0),
    },
    "daily-summary-email": {
        "task": "send_daily_summary",
        "schedule": crontab(hour=8, minute=0),
    },
    "weekly-report": {
        "task": "send_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    "monthly-cleanup": {
        "task": "cleanup_old_data",
        "schedule": crontab(hour=2, minute=0, day_of_month=1),
    },
}
