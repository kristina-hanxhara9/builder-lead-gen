"""Letters API routes."""

import asyncio
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import Lead, Letter
from app.models.schemas import LetterListResponse, LetterResponse
from app.services.stannp_service import StannpService

router = APIRouter(prefix="/letters", tags=["letters"])


@router.get("", response_model=LetterListResponse)
def list_letters(
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """List all letters, optionally filtered by status."""
    query = db.query(Letter)
    if status:
        query = query.filter(Letter.status == status)

    letters = query.order_by(Letter.created_at.desc()).all()
    return LetterListResponse(
        letters=[LetterResponse.model_validate(l) for l in letters],
        total=len(letters),
    )


@router.get("/{letter_id}", response_model=LetterResponse)
def get_letter(letter_id: UUID, db: Session = Depends(get_db)):
    """Get a single letter."""
    letter = db.query(Letter).filter(Letter.id == letter_id).first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    return letter


@router.post("/{letter_id}/approve", response_model=LetterResponse)
def approve_letter(letter_id: UUID, db: Session = Depends(get_db)):
    """Approve a draft letter for sending."""
    letter = db.query(Letter).filter(Letter.id == letter_id).first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    if letter.status != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot approve letter with status '{letter.status}'")

    letter.status = "approved"
    letter.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(letter)
    return letter


@router.post("/{letter_id}/send", response_model=LetterResponse)
def send_letter(letter_id: UUID, db: Session = Depends(get_db)):
    """Send an approved letter via Royal Mail (Stannp)."""
    letter = db.query(Letter).filter(Letter.id == letter_id).first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    if letter.status not in ("approved", "draft"):
        raise HTTPException(status_code=400, detail=f"Cannot send letter with status '{letter.status}'")

    lead = db.query(Lead).filter(Lead.id == letter.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Associated lead not found")

    # For now, mark as queued. Actual Stannp sending done via Celery task.
    letter.status = "queued"
    letter.sent_at = datetime.utcnow()
    db.commit()
    db.refresh(letter)
    return letter


@router.get("/{letter_id}/download")
def download_letter_pdf(letter_id: UUID, db: Session = Depends(get_db)):
    """Download the letter as a PDF file."""
    letter = db.query(Letter).filter(Letter.id == letter_id).first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")

    # Try to serve from stored PDF file
    if letter.pdf_storage_path:
        pdf_path = Path(letter.pdf_storage_path)
        if pdf_path.exists():
            # Build a nice filename from the lead address
            lead = db.query(Lead).filter(Lead.id == letter.lead_id).first()
            filename = f"letter-{letter_id}.pdf"
            if lead and lead.address:
                # e.g. "Smith-Sons-Letter-76-Upper-Tulse-Hill.pdf"
                safe_addr = lead.address.split(",")[0].strip().replace(" ", "-")
                filename = f"Smith-Sons-Letter-{safe_addr}.pdf"
            return FileResponse(
                path=str(pdf_path),
                media_type="application/pdf",
                filename=filename,
            )

    # Fallback: generate PDF on-the-fly from letter content
    if not letter.content:
        raise HTTPException(status_code=404, detail="No PDF or content available for this letter")

    from app.services.pdf_generator import PDFGenerator

    generator = PDFGenerator()
    lead = db.query(Lead).filter(Lead.id == letter.lead_id).first()
    address = lead.address if lead else "Homeowner"

    pdf_bytes = generator.generate_letter_pdf(
        letter_content=letter.content,
        recipient_address=address,
        case_studies=[],
        qr_url=letter.qr_code_url,
    )

    safe_addr = address.split(",")[0].strip().replace(" ", "-")
    filename = f"Smith-Sons-Letter-{safe_addr}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
