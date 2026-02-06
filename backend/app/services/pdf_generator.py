"""ReportLab PDF generator for branded sales letters."""

import io
import logging
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import client_config
from app.services.qr_service import QRService

logger = logging.getLogger(__name__)

# Brand colors
NAVY = colors.HexColor("#1a365d")
LIGHT_BLUE = colors.HexColor("#2c5282")
GOLD = colors.HexColor("#d4a574")
WHITE = colors.white


class PDFGenerator:
    """Generate branded PDF sales letters with letterhead, content, and QR code."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Define custom paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                "LetterBody",
                parent=self.styles["Normal"],
                fontName="Times-Roman",
                fontSize=11,
                leading=16,
                spaceAfter=8,
            )
        )
        self.styles.add(
            ParagraphStyle(
                "LetterHeading",
                parent=self.styles["Heading2"],
                fontName="Times-Bold",
                fontSize=13,
                textColor=NAVY,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                "CompanyName",
                parent=self.styles["Title"],
                fontName="Times-Bold",
                fontSize=18,
                textColor=NAVY,
                spaceAfter=2,
            )
        )
        self.styles.add(
            ParagraphStyle(
                "CompanyTagline",
                parent=self.styles["Normal"],
                fontName="Times-Italic",
                fontSize=9,
                textColor=LIGHT_BLUE,
            )
        )
        self.styles.add(
            ParagraphStyle(
                "Footer",
                parent=self.styles["Normal"],
                fontName="Times-Roman",
                fontSize=7,
                textColor=colors.gray,
                alignment=1,  # center
            )
        )

    def generate_letter_pdf(
        self,
        letter_content: str,
        recipient_address: str,
        case_studies: list[dict],
        qr_url: Optional[str] = None,
        street_view_image: Optional[bytes] = None,
        static_map_image: Optional[bytes] = None,
    ) -> bytes:
        """Generate a complete branded letter PDF.

        Args:
            letter_content: The letter text.
            recipient_address: Comma-separated address lines.
            case_studies: List of case study dicts.
            qr_url: QR code tracking URL.
            street_view_image: Optional Street View JPEG bytes.
            static_map_image: Optional static map PNG bytes.

        Returns PDF as bytes.
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=25 * mm,
            rightMargin=25 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        story = []

        # --- Letterhead ---
        story.append(self._build_letterhead())
        story.append(Spacer(1, 8 * mm))

        # --- Horizontal rule ---
        story.append(self._gold_rule())
        story.append(Spacer(1, 4 * mm))

        # --- Property images (Street View + map side by side) ---
        if street_view_image or static_map_image:
            story.append(self._build_property_images(street_view_image, static_map_image))
            story.append(Spacer(1, 4 * mm))

        # --- Recipient address ---
        for line in recipient_address.split(","):
            story.append(
                Paragraph(line.strip(), self.styles["LetterBody"])
            )
        story.append(Spacer(1, 6 * mm))

        # --- Letter content ---
        paragraphs = letter_content.split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # Replace newlines within paragraph with <br/>
            para = para.replace("\n", "<br/>")
            story.append(Paragraph(para, self.styles["LetterBody"]))

        story.append(Spacer(1, 4 * mm))

        # --- Signature area ---
        story.append(self._build_signature())
        story.append(Spacer(1, 6 * mm))

        # --- Gold rule ---
        story.append(self._gold_rule())
        story.append(Spacer(1, 4 * mm))

        # --- Case studies ---
        if case_studies:
            story.append(
                Paragraph(
                    "Recent Projects Near You",
                    self.styles["LetterHeading"],
                )
            )
            for cs in case_studies[:3]:
                cs_text = (
                    f"<b>{cs['title']}</b> — {cs['work_type']}<br/>"
                    f"<i>\"{cs['testimonial']}\"</i> — {cs['client_name']}"
                )
                story.append(Paragraph(cs_text, self.styles["LetterBody"]))
                story.append(Spacer(1, 2 * mm))

        # --- QR Code ---
        if qr_url:
            story.append(Spacer(1, 4 * mm))
            story.append(
                Paragraph(
                    "Scan to visit our website and see more projects:",
                    self.styles["LetterBody"],
                )
            )
            qr_bytes = QRService.generate_qr_image(qr_url, size=120)
            qr_image = Image(io.BytesIO(qr_bytes), width=30 * mm, height=30 * mm)
            story.append(qr_image)

        # --- Footer ---
        story.append(Spacer(1, 6 * mm))
        story.append(self._gold_rule())
        footer_text = (
            f"{client_config.company_name} | {client_config.phone} | "
            f"{client_config.website}<br/>"
            f"Company Reg: {client_config.legal['company_registration']} | "
            f"VAT: {client_config.legal['vat_number']} | "
            f"Public Liability: £{client_config.legal['public_liability_amount']}"
        )
        story.append(Paragraph(footer_text, self.styles["Footer"]))

        doc.build(story)
        return buf.getvalue()

    def _build_letterhead(self) -> Table:
        """Build the letterhead with company name and contact info."""
        left = []
        left.append(Paragraph(client_config.company_name, self.styles["CompanyName"]))
        left.append(
            Paragraph(
                f"Est. {client_config.trading_since} | Specialists in Extensions & Loft Conversions",
                self.styles["CompanyTagline"],
            )
        )

        right = []
        contact_style = ParagraphStyle(
            "ContactInfo",
            parent=self.styles["Normal"],
            fontName="Times-Roman",
            fontSize=8,
            textColor=LIGHT_BLUE,
            alignment=2,  # right
        )
        right.append(
            Paragraph(client_config.phone, contact_style)
        )
        right.append(
            Paragraph(client_config.email, contact_style)
        )
        right.append(
            Paragraph(client_config.website, contact_style)
        )
        right.append(
            Paragraph(client_config.office_address, contact_style)
        )

        from reportlab.platypus import KeepInFrame

        table_data = [[left, right]]
        t = Table(table_data, colWidths=[100 * mm, 60 * mm])
        t.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )
        return t

    def _build_signature(self) -> Paragraph:
        """Build signature block."""
        sig_text = (
            f"Yours sincerely,<br/><br/>"
            f"<b>{client_config.owner_name}</b><br/>"
            f"Director, {client_config.company_name}<br/>"
            f"Tel: {client_config.phone}"
        )
        return Paragraph(sig_text, self.styles["LetterBody"])

    def _build_property_images(
        self,
        street_view: Optional[bytes] = None,
        static_map: Optional[bytes] = None,
    ) -> Table:
        """Build a table with property Street View photo and/or map side by side."""
        img_width = 75 * mm
        img_height = 47 * mm

        cells = []
        col_widths = []

        if street_view:
            sv_img = Image(io.BytesIO(street_view), width=img_width, height=img_height)
            cells.append(sv_img)
            col_widths.append(80 * mm)

        if static_map:
            map_img = Image(io.BytesIO(static_map), width=img_width, height=img_height)
            cells.append(map_img)
            col_widths.append(80 * mm)

        if not cells:
            return Spacer(1, 0)

        # If only one image, center it
        if len(cells) == 1:
            col_widths = [160 * mm]

        t = Table([cells], colWidths=col_widths)
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        # Add a subtle caption
        caption_style = ParagraphStyle(
            "ImageCaption",
            parent=self.styles["Normal"],
            fontName="Times-Italic",
            fontSize=7,
            textColor=colors.gray,
            alignment=1,  # center
        )
        parts = []
        if street_view:
            parts.append("Street View")
        if static_map:
            parts.append("Location Map")
        caption = Paragraph(
            " | ".join(parts) + " — Your Property",
            caption_style,
        )

        # Wrap in a table to keep together
        wrapper = Table([[t], [caption]], colWidths=[160 * mm])
        wrapper.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        return wrapper

    def _gold_rule(self) -> Table:
        """Create a gold horizontal rule."""
        t = Table([[""]], colWidths=[160 * mm], rowHeights=[0.5 * mm])
        t.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), GOLD),
                ("LINEBELOW", (0, 0), (-1, -1), 0, GOLD),
            ])
        )
        return t
