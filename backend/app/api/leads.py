"""Leads API routes."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import Lead
from app.models.schemas import LeadListResponse, LeadResponse, LeadStatusUpdate

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadListResponse)
def list_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    postcode: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List leads with filtering and pagination."""
    query = db.query(Lead)

    if status:
        query = query.filter(Lead.status == status)
    if min_score is not None:
        query = query.filter(Lead.lead_score >= min_score)
    if postcode:
        query = query.filter(Lead.postcode.ilike(f"{postcode}%"))

    total = query.count()
    leads = (
        query.order_by(desc(Lead.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return LeadListResponse(
        leads=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: UUID, db: Session = Depends(get_db)):
    """Get a single lead by ID."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}/status", response_model=LeadResponse)
def update_lead_status(
    lead_id: UUID,
    update: LeadStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update lead status and optionally add a note."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_status = lead.status
    lead.status = update.status

    # Update timestamps based on status
    now = datetime.utcnow()
    if update.status == "contacted" and not lead.contacted_at:
        lead.contacted_at = now
    elif update.status == "quoted" and not lead.quoted_at:
        lead.quoted_at = now
    elif update.status == "won" and not lead.won_at:
        lead.won_at = now

    # Add note if provided
    if update.note:
        notes = lead.notes or []
        notes.append({
            "text": update.note,
            "timestamp": now.isoformat(),
            "action": f"Status changed: {old_status} → {update.status}",
        })
        lead.notes = notes

    db.commit()
    db.refresh(lead)
    return lead
