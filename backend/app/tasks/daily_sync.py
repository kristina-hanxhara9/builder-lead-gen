"""Daily planning application sync task.

Runs at 6 AM to fetch new planning applications from London councils,
deduplicate, insert into database, and trigger lead processing.
"""

import asyncio
import logging

from app.core.database import SessionLocal
from app.models.database import PlanningApplication
from app.services.planning_api import LondonPlanningAPI
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="daily_planning_sync", bind=True, max_retries=3)
def sync_planning_applications(self, days_back: int = 1):
    """Fetch new planning applications and trigger processing.

    Expected runtime: 10-15 minutes
    Expected new applications: 5-15 per day
    """
    logger.info(f"Starting daily planning sync (days_back={days_back})")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(_async_sync(days_back))
        return results
    finally:
        loop.close()


async def _async_sync(days_back: int) -> dict:
    """Async implementation of the planning sync."""
    api = LondonPlanningAPI()
    db = SessionLocal()

    try:
        applications = await api.fetch_recent_applications(days_back)
        logger.info(f"Fetched {len(applications)} filtered applications")

        new_count = 0
        skipped_count = 0

        for app_data in applications:
            reference = app_data.get("reference")
            if not reference:
                continue

            existing = (
                db.query(PlanningApplication)
                .filter(PlanningApplication.reference == reference)
                .first()
            )
            if existing:
                skipped_count += 1
                continue

            planning_app = PlanningApplication(
                reference=reference,
                address=app_data.get("address", ""),
                postcode=app_data.get("postcode", ""),
                description=app_data.get("description"),
                application_type=app_data.get("application_type"),
                status=app_data.get("status"),
                submitted_date=app_data.get("submitted_date"),
                decision=app_data.get("decision"),
                decision_date=app_data.get("decision_date"),
                pdf_urls=app_data.get("pdf_urls", []),
                detail_url=app_data.get("detail_url", ""),
                local_authority=app_data.get("local_authority"),
                applicant_name=app_data.get("applicant_name"),
                raw_data=app_data,
            )
            db.add(planning_app)
            db.flush()

            from app.tasks.process_lead import process_planning_application
            process_planning_application.delay(str(planning_app.id))

            new_count += 1

        db.commit()

        summary = {
            "fetched": len(applications),
            "new": new_count,
            "skipped": skipped_count,
        }
        logger.info(f"Sync complete: {summary}")
        return summary

    except Exception as e:
        db.rollback()
        logger.error(f"Sync failed: {e}")
        raise

    finally:
        db.close()
        await api.close()
