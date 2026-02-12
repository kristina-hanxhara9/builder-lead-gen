"""Planning applications API routes."""

import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.database import Lead, Letter, PlanningApplication
from app.models.schemas import PlanningAppResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/planning", tags=["planning"])


@router.get("", response_model=list[PlanningAppResponse])
def list_planning_applications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    postcode: Optional[str] = None,
    local_authority: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List planning applications with pagination and filters."""
    query = db.query(PlanningApplication)

    if postcode:
        query = query.filter(PlanningApplication.postcode.ilike(f"{postcode}%"))
    if local_authority:
        query = query.filter(PlanningApplication.local_authority.ilike(f"%{local_authority}%"))

    apps = (
        query.order_by(desc(PlanningApplication.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return [PlanningAppResponse.model_validate(a) for a in apps]


@router.post("/sync")
async def trigger_sync(
    days_back: int = Query(1, ge=1, le=30),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Manually trigger planning application sync.

    In dev mode runs inline (no Celery needed).
    In production delegates to Celery worker.
    """
    if settings.app_env == "development" or settings.debug:
        # Run inline — no Celery needed
        from app.services.planning_api import LondonPlanningAPI
        from app.core.database import SessionLocal
        from app.models.database import PlanningApplication as PA

        api = LondonPlanningAPI()
        db = SessionLocal()
        try:
            applications = await api.fetch_recent_applications(days_back)
            new_count = 0
            skipped_count = 0
            for app_data in applications:
                reference = app_data.get("reference")
                if not reference:
                    continue
                existing = db.query(PA).filter(PA.reference == reference).first()
                if existing:
                    skipped_count += 1
                    continue
                planning_app = PA(
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
                    processing_status="new",
                )
                db.add(planning_app)
                new_count += 1
            db.commit()
            return {
                "status": "sync_complete",
                "days_back": days_back,
                "fetched": len(applications),
                "new": new_count,
                "skipped": skipped_count,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Sync failed: {e}")
            return {"status": "sync_failed", "error": str(e), "days_back": days_back}
        finally:
            db.close()
            await api.close()
    else:
        # Production — use Celery
        from app.tasks.daily_sync import sync_planning_applications
        sync_planning_applications.delay(days_back)
        return {"status": "sync_started", "days_back": days_back}


@router.post("/add")
async def add_planning_application(
    reference: str = Query(...),
    address: str = Query(...),
    postcode: str = Query(...),
    description: str = Query(""),
    detail_url: str = Query(""),
    local_authority: str = Query(""),
    db: Session = Depends(get_db),
):
    """Manually add a planning application (e.g. from a portal URL)."""
    existing = db.query(PlanningApplication).filter(
        PlanningApplication.reference == reference
    ).first()
    if existing:
        return {
            "status": "exists",
            "id": str(existing.id),
            "reference": reference,
        }

    app = PlanningApplication(
        reference=reference,
        address=address,
        postcode=postcode,
        description=description,
        detail_url=detail_url,
        local_authority=local_authority,
        application_type="Householder",
        status="Submitted",
        pdf_urls=[],
        raw_data={"source": "manual"},
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {
        "status": "created",
        "id": str(app.id),
        "reference": reference,
    }


@router.post("/process/{app_id}")
async def process_single_application(app_id: UUID, db: Session = Depends(get_db)):
    """Run the full 5-agent pipeline on a single planning application.

    This is the core endpoint that turns a planning application into a
    scored lead with a personalised letter — all in one request.
    """
    planning_app = db.query(PlanningApplication).filter(
        PlanningApplication.id == app_id
    ).first()
    if not planning_app:
        raise HTTPException(status_code=404, detail="Application not found")

    from app.agents.agent_graph import run_pipeline

    app_data = {
        "reference": planning_app.reference,
        "address": planning_app.address,
        "postcode": planning_app.postcode,
        "description": planning_app.description,
        "application_type": planning_app.application_type,
        "status": planning_app.status,
        "submitted_date": (
            planning_app.submitted_date.isoformat()
            if planning_app.submitted_date else None
        ),
        "decision": planning_app.decision,
        "decision_date": (
            planning_app.decision_date.isoformat()
            if planning_app.decision_date else None
        ),
        "pdf_urls": planning_app.pdf_urls or [],
        "detail_url": planning_app.detail_url or (planning_app.raw_data or {}).get("detail_url", ""),
        "local_authority": planning_app.local_authority,
        "applicant_name": planning_app.applicant_name,
    }

    # Mark as processing
    planning_app.processing_status = "processing"
    planning_app.processing_started_at = __import__("datetime").datetime.utcnow()
    db.commit()

    result = await run_pipeline(str(app_id), app_data)

    # Save results to database
    from app.models.database import PlanningExtracted, Lead as LeadModel, Letter as LetterModel

    # Save extracted data
    extracted = result.get("extracted_data", {})
    if extracted:
        from app.models.database import PlanningExtracted
        ext = db.query(PlanningExtracted).filter(
            PlanningExtracted.planning_app_id == app_id
        ).first()
        if not ext:
            ext = PlanningExtracted(planning_app_id=app_id)
            db.add(ext)
        ext.property_type = extracted.get("property_type")
        ext.work_description = extracted.get("work_description")
        ext.work_category = extracted.get("work_category")
        ext.estimated_cost = extracted.get("estimated_cost")
        ext.bedrooms_before = extracted.get("bedrooms_before")
        ext.bedrooms_after = extracted.get("bedrooms_after")
        ext.floor_area_added_m2 = extracted.get("floor_area_added_m2")
        ext.materials = extracted.get("materials", [])
        ext.confidence_score = result.get("extraction_confidence", 0.0)
        db.flush()

    # Save lead
    unified = result.get("unified_data", {})
    lead_score = result.get("lead_score", 0)
    if lead_score > 0:
        lead = db.query(LeadModel).filter(
            LeadModel.planning_app_id == app_id
        ).first()
        if not lead:
            lead = LeadModel(planning_app_id=app_id)
            db.add(lead)
        lead.address = planning_app.address
        lead.postcode = planning_app.postcode
        lead.work_type = unified.get("work_category")
        lead.work_description = unified.get("work_description")
        lead.lead_score = lead_score
        lead.score_breakdown = result.get("score_breakdown", {})
        lead.property_value_estimate = unified.get("property_value_estimate", 0)
        lead.distance_km = unified.get("distance_from_office_km", 0)
        lead.unified_data = unified
        lead.status = "new"
        db.flush()

        # Save letter
        if result.get("letter_content"):
            letter = db.query(LetterModel).filter(
                LetterModel.lead_id == lead.id
            ).first()
            if not letter:
                letter = LetterModel(lead_id=lead.id)
                db.add(letter)
            letter.content = result.get("letter_content")
            letter.status = "draft"
            letter.generation_cost_gbp = result.get("total_cost_gbp", 0)
            letter.qr_code_url = result.get("qr_url")

            # Save PDF to disk
            if result.get("letter_pdf_bytes"):
                import os
                pdf_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "pdfs")
                os.makedirs(pdf_dir, exist_ok=True)
                pdf_path = os.path.join(pdf_dir, f"{letter.id}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(result["letter_pdf_bytes"])
                letter.pdf_url = f"/data/pdfs/{letter.id}.pdf"
            db.flush()

    # Mark as processed
    planning_app.processing_status = "processed"
    planning_app.processing_error = None
    db.commit()

    return {
        "status": "complete",
        "planning_app_id": str(app_id),
        "reference": planning_app.reference,
        "extraction_confidence": result.get("extraction_confidence", 0),
        "fields_extracted": len([v for v in extracted.values() if v]) if extracted else 0,
        "epc_found": bool(result.get("epc_data")),
        "lead_score": lead_score,
        "should_generate_letter": result.get("should_generate_letter", False),
        "letter_generated": bool(result.get("letter_content")),
        "pdf_size_kb": round(len(result.get("letter_pdf_bytes") or b"") / 1024, 1),
        "total_cost_gbp": result.get("total_cost_gbp", 0),
        "agent_logs": result.get("agent_logs", []),
    }


@router.get("/stats/summary")
def planning_stats(db: Session = Depends(get_db)):
    """Quick statistics about planning applications in the database."""
    total = db.query(func.count(PlanningApplication.id)).scalar()
    with_detail_url = db.query(func.count(PlanningApplication.id)).filter(
        PlanningApplication.detail_url.isnot(None)
    ).scalar()
    councils = db.query(
        PlanningApplication.local_authority,
        func.count(PlanningApplication.id),
    ).group_by(PlanningApplication.local_authority).all()

    return {
        "total_applications": total,
        "with_detail_url": with_detail_url,
        "by_council": {c: n for c, n in councils if c},
    }


@router.post("/batch-process")
def trigger_batch_process(
    batch_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Manually trigger batch processing of unprocessed applications.

    In dev mode runs inline. In production delegates to Celery.
    """
    # Count unprocessed first
    unprocessed = (
        db.query(func.count(PlanningApplication.id))
        .filter(PlanningApplication.processing_status == "new")
        .scalar()
    )

    if unprocessed == 0:
        return {"status": "nothing_to_process", "unprocessed": 0}

    if settings.app_env == "development" or settings.debug:
        from app.tasks.batch_process import batch_process_leads
        result = batch_process_leads(batch_size)
        return {"status": "batch_complete", **result}
    else:
        from app.tasks.batch_process import batch_process_leads
        batch_process_leads.delay(batch_size)
        return {
            "status": "batch_started",
            "batch_size": batch_size,
            "unprocessed": unprocessed,
        }


@router.get("/stats/processing")
def processing_stats(db: Session = Depends(get_db)):
    """Statistics about the processing pipeline status."""
    status_counts = (
        db.query(
            PlanningApplication.processing_status,
            func.count(PlanningApplication.id),
        )
        .group_by(PlanningApplication.processing_status)
        .all()
    )

    counts = {s: c for s, c in status_counts if s}
    total = sum(c for _, c in status_counts)

    return {
        "new": counts.get("new", 0),
        "processing": counts.get("processing", 0),
        "processed": counts.get("processed", 0),
        "failed": counts.get("failed", 0),
        "total": total,
    }


@router.get("/{app_id}", response_model=PlanningAppResponse)
def get_planning_application(app_id: UUID, db: Session = Depends(get_db)):
    """Get a single planning application."""
    app = db.query(PlanningApplication).filter(PlanningApplication.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app
