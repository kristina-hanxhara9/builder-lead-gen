"""QR code tracking routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import client_config, settings
from app.core.database import get_db
from app.models.database import Letter, QRScan

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/{code}")
def track_qr_scan(
    code: str,
    request: Request,
    letter: str | None = None,
    db: Session = Depends(get_db),
):
    """Track a QR code scan and redirect to website.

    Each scan is logged for analytics. The letter_id comes from
    the query param embedded in the QR URL.
    """
    redirect_url = f"https://{client_config.website}"

    if letter:
        # Log the scan
        try:
            letter_record = db.query(Letter).filter(Letter.id == letter).first()
            if letter_record:
                scan = QRScan(
                    letter_id=letter_record.id,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    redirect_url=redirect_url,
                )
                db.add(scan)

                # Update letter scan count
                letter_record.qr_scan_count = (letter_record.qr_scan_count or 0) + 1
                if not letter_record.first_scan_at:
                    from datetime import datetime
                    letter_record.first_scan_at = datetime.utcnow()

                db.commit()
        except Exception:
            db.rollback()  # Don't let tracking errors block the redirect

    return RedirectResponse(url=redirect_url, status_code=302)
