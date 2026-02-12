"""Batch processing orchestrator — processes unprocessed planning applications.

Runs at 7 AM daily, after the 6 AM sync has populated the database.
Processes applications in priority order with rate limiting to avoid
hammering the Gemini API.

Schedule:
    6:00 AM — daily_sync fetches new applications (processing_status='new')
    7:00 AM — THIS TASK processes them through the 5-agent pipeline
    8:00 AM — daily_summary reports the results
"""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import case, desc, func

from app.core.config import client_config
from app.core.database import SessionLocal
from app.models.database import PlanningApplication
from app.tasks import celery_app

logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 50            # Max applications to process per batch run
DELAY_BETWEEN_APPS = 5     # Seconds between dispatching each app
PROCESSING_TIMEOUT = 600   # Seconds before a "processing" app is considered stuck


@celery_app.task(name="batch_process_leads", bind=True, max_retries=1)
def batch_process_leads(self, batch_size: int = BATCH_SIZE):
    """Process all unprocessed planning applications in priority order.

    Priority ordering:
    1. Target postcode districts first (SW11, SW12, SW15, SW17, SW18)
    2. Within each group, newer applications first
    3. Adjacent postcodes after target postcodes

    Rate limiting: dispatches one app every DELAY_BETWEEN_APPS seconds
    to avoid overwhelming the Gemini API.
    """
    logger.info(f"Starting batch processing (max {batch_size} applications)")
    db = SessionLocal()

    try:
        # Reset any stuck "processing" tasks
        stuck_cutoff = datetime.utcnow() - timedelta(seconds=PROCESSING_TIMEOUT)
        stuck_count = (
            db.query(PlanningApplication)
            .filter(
                PlanningApplication.processing_status == "processing",
                PlanningApplication.processing_started_at < stuck_cutoff,
            )
            .update({
                PlanningApplication.processing_status: "new",
                PlanningApplication.processing_started_at: None,
                PlanningApplication.processing_error: "Reset: timed out",
            })
        )
        if stuck_count:
            db.commit()
            logger.warning(f"Reset {stuck_count} stuck processing tasks")

        # Build priority ordering: target postcodes first, then newest
        target_postcodes = client_config.target_postcodes

        # Build CASE expression for postcode priority
        postcode_cases = [
            (PlanningApplication.postcode.ilike(f"{pc}%"), 0)
            for pc in target_postcodes
        ]

        apps = (
            db.query(PlanningApplication)
            .filter(PlanningApplication.processing_status == "new")
            .order_by(
                case(*postcode_cases, else_=1),
                desc(PlanningApplication.submitted_date),
                desc(PlanningApplication.created_at),
            )
            .limit(batch_size)
            .all()
        )

        if not apps:
            logger.info("No unprocessed applications found")
            return {"dispatched": 0, "remaining": 0}

        logger.info(f"Found {len(apps)} applications to process")

        # Dispatch each application with rate limiting
        dispatched = 0
        for app in apps:
            # Mark as "processing" before dispatching
            app.processing_status = "processing"
            app.processing_started_at = datetime.utcnow()
            db.commit()

            # Dispatch the wrapper task
            process_and_update_status.delay(str(app.id))
            dispatched += 1

            logger.info(
                f"Dispatched {dispatched}/{len(apps)}: "
                f"{app.reference} ({app.postcode})"
            )

            # Rate limit between dispatches
            if dispatched < len(apps):
                time.sleep(DELAY_BETWEEN_APPS)

        # Count remaining unprocessed
        remaining = (
            db.query(func.count(PlanningApplication.id))
            .filter(PlanningApplication.processing_status == "new")
            .scalar()
        )

        summary = {
            "dispatched": dispatched,
            "remaining": remaining,
            "batch_size": batch_size,
        }
        logger.info(f"Batch processing complete: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise

    finally:
        db.close()


@celery_app.task(name="process_and_update_status", bind=True, max_retries=2)
def process_and_update_status(self, planning_app_id: str):
    """Wrapper around process_planning_application that tracks status.

    Runs the existing 5-agent pipeline for one application, then updates
    the processing_status column:
        - On success: "processed"
        - On failure: "failed" + error message

    The existing process_planning_application task is called directly
    (not via .delay()) so we can track its result and update status.
    """
    db = SessionLocal()
    try:
        # Import here to avoid circular imports
        from app.tasks.process_lead import _async_process
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_async_process(planning_app_id))
        finally:
            loop.close()

        # Update status based on result
        app = db.query(PlanningApplication).filter(
            PlanningApplication.id == planning_app_id
        ).first()

        if app:
            if result and not result.get("error"):
                app.processing_status = "processed"
                app.processing_error = None
                logger.info(
                    f"Processed {app.reference}: "
                    f"score={result.get('lead_score', 0)}, "
                    f"letter={'yes' if result.get('letter_generated') else 'no'}"
                )
            else:
                app.processing_status = "failed"
                app.processing_error = str(result.get("error", "Unknown error"))
                logger.warning(f"Failed {app.reference}: {app.processing_error}")
            db.commit()

        return result

    except Exception as e:
        # Mark as failed
        try:
            app = db.query(PlanningApplication).filter(
                PlanningApplication.id == planning_app_id
            ).first()
            if app:
                app.processing_status = "failed"
                app.processing_error = str(e)
                db.commit()
        except Exception:
            pass

        logger.error(f"Processing failed for {planning_app_id}: {e}")
        raise self.retry(exc=e, countdown=120)

    finally:
        db.close()
