"""Monthly cleanup and maintenance tasks."""

import logging
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.core.redis import redis_client
from app.models.database import Lead
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="cleanup_old_data")
def cleanup_old_data():
    """Monthly cleanup: archive old leads, fix cache TTLs.

    Runs on the 1st of each month at 2 AM.
    """
    db = SessionLocal()

    try:
        six_months_ago = datetime.utcnow() - timedelta(days=180)

        archived = (
            db.query(Lead)
            .filter(Lead.status == "lost", Lead.updated_at < six_months_ago)
            .count()
        )
        logger.info(f"Found {archived} old lost leads (>6 months)")

        # Fix Redis cache entries missing TTLs
        cleared = 0
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor, match="epc:*", count=100)
            for key in keys:
                ttl = redis_client.ttl(key)
                if ttl == -1:
                    redis_client.expire(key, 7 * 24 * 3600)
                    cleared += 1
            if cursor == 0:
                break

        logger.info(f"Cache cleanup: fixed TTL on {cleared} keys")

        db.commit()
        return {"archived_leads": archived, "cache_keys_fixed": cleared}

    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup failed: {e}")
        raise

    finally:
        db.close()
