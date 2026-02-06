"""Dashboard API routes — stats and pipeline data."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import Lead, Letter, QRScan
from app.models.schemas import DashboardStats, PipelineResponse, PipelineStage

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get key metrics for the dashboard."""
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()

    new_leads_today = (
        db.query(func.count(Lead.id))
        .filter(func.date(Lead.created_at) == today)
        .scalar()
    ) or 0

    total_leads = db.query(func.count(Lead.id)).scalar() or 0

    letters_pending = (
        db.query(func.count(Letter.id))
        .filter(Letter.status == "draft")
        .scalar()
    ) or 0

    letters_sent = (
        db.query(func.count(Letter.id))
        .filter(Letter.status.in_(["posted", "delivered"]))
        .scalar()
    ) or 0

    qr_scans_total = db.query(func.count(QRScan.id)).scalar() or 0

    won = db.query(func.count(Lead.id)).filter(Lead.status == "won").scalar() or 0
    conversion_rate = (won / total_leads * 100) if total_leads > 0 else 0.0

    pipeline_value = (
        db.query(func.sum(Lead.property_value_estimate))
        .filter(Lead.status.in_(["new", "contacted", "quoted"]))
        .scalar()
    ) or 0.0

    avg_score = db.query(func.avg(Lead.lead_score)).scalar() or 0.0

    return DashboardStats(
        new_leads_today=new_leads_today,
        total_leads=total_leads,
        letters_pending=letters_pending,
        letters_sent=letters_sent,
        qr_scans_total=qr_scans_total,
        conversion_rate=round(conversion_rate, 1),
        pipeline_value=pipeline_value,
        avg_lead_score=round(avg_score, 1),
    )


@router.get("/pipeline", response_model=PipelineResponse)
def get_pipeline(db: Session = Depends(get_db)):
    """Get pipeline stages for funnel visualization."""
    stages = []
    for status in ["new", "contacted", "quoted", "won", "lost"]:
        count = (
            db.query(func.count(Lead.id))
            .filter(Lead.status == status)
            .scalar()
        ) or 0
        value = (
            db.query(func.sum(Lead.property_value_estimate))
            .filter(Lead.status == status)
            .scalar()
        ) or 0.0
        stages.append(PipelineStage(stage=status, count=count, value=value))

    return PipelineResponse(stages=stages)
