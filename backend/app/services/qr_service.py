"""QR code generation for letter tracking."""

import io
import uuid

import qrcode
from qrcode.image.styledpil import StyledPilImage

from app.core.config import settings


class QRService:
    """Generate unique QR codes for tracking letter responses."""

    @staticmethod
    def generate_tracking_url(letter_id: str) -> str:
        """Create a unique tracking URL for a letter."""
        code = uuid.uuid4().hex[:12]
        return f"{settings.backend_url}/api/qr/{code}?letter={letter_id}"

    @staticmethod
    def generate_qr_image(url: str, size: int = 200) -> bytes:
        """Generate a QR code PNG image as bytes."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="#1a365d", back_color="white")
        img = img.resize((size, size))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
