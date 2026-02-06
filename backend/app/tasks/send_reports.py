"""Email reporting tasks: daily summary and weekly report."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.database import Lead, Letter, QRScan
from app.services.email_service import EmailService
from app.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="send_daily_summary")
def send_daily_summary():
    """Send daily summary email at 8 AM."""
    db = SessionLocal()
    email_service = EmailService()

    try:
        yesterday = datetime.utcnow().date() - timedelta(days=1)

        new_leads = (
            db.query(func.count(Lead.id))
            .filter(func.date(Lead.created_at) >= yesterday)
            .scalar()
        ) or 0

        letters_pending = (
            db.query(func.count(Letter.id))
            .filter(Letter.status == "draft")
            .scalar()
        ) or 0

        letters_sent = (
            db.query(func.count(Letter.id))
            .filter(
                Letter.status.in_(["posted", "delivered"]),
                func.date(Letter.sent_at) >= yesterday,
            )
            .scalar()
        ) or 0

        qr_scans = (
            db.query(func.count(QRScan.id))
            .filter(func.date(QRScan.scanned_at) >= yesterday)
            .scalar()
        ) or 0

        success = email_service.send_daily_summary(
            new_leads=new_leads,
            letters_pending=letters_pending,
            letters_sent=letters_sent,
            qr_scans=qr_scans,
        )

        logger.info(
            f"Daily summary: {new_leads} leads, {letters_pending} pending, "
            f"{letters_sent} sent, {qr_scans} scans"
        )
        return {"sent": success}

    finally:
        db.close()


@celery_app.task(name="send_weekly_report")
def send_weekly_report():
    """Send weekly performance report every Monday at 9 AM."""
    db = SessionLocal()
    email_service = EmailService()

    try:
        week_ago = datetime.utcnow() - timedelta(days=7)

        leads_generated = (
            db.query(func.count(Lead.id))
            .filter(Lead.created_at >= week_ago)
            .scalar()
        ) or 0

        letters_sent = (
            db.query(func.count(Letter.id))
            .filter(Letter.sent_at >= week_ago)
            .scalar()
        ) or 0

        qr_scans = (
            db.query(func.count(QRScan.id))
            .filter(QRScan.scanned_at >= week_ago)
            .scalar()
        ) or 0

        total_leads = db.query(func.count(Lead.id)).scalar() or 0
        won_leads = (
            db.query(func.count(Lead.id)).filter(Lead.status == "won").scalar()
        ) or 0
        conversion_rate = (won_leads / total_leads * 100) if total_leads > 0 else 0.0

        pipeline_value = (
            db.query(func.sum(Lead.property_value_estimate))
            .filter(Lead.status.in_(["new", "contacted", "quoted"]))
            .scalar()
        ) or 0.0

        total_cost = (
            db.query(func.sum(Letter.generation_cost_gbp + Letter.print_cost_gbp))
            .filter(Letter.created_at >= week_ago)
            .scalar()
        ) or 0.0

        cost_per_lead = (total_cost / leads_generated) if leads_generated > 0 else 0.0

        stats = {
            "leads_generated": leads_generated,
            "letters_sent": letters_sent,
            "qr_scans": qr_scans,
            "conversion_rate": conversion_rate,
            "pipeline_value": pipeline_value,
            "cost_per_lead": cost_per_lead,
        }

        success = email_service.send_weekly_report(stats)
        logger.info(f"Weekly report: {stats}")
        return {"sent": success, "stats": stats}

    finally:
        db.close()
