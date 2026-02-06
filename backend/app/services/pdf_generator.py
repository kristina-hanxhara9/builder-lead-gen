"""ReportLab PDF generator for branded sales letters."""

import io
import logging
import re
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

    @staticmethod
    def _strip_ai_signature(text: str) -> str:
        """Remove AI-generated signature block from letter content.

        The AI often appends 'Yours sincerely/faithfully, Name, Title, Company...'
        at the end of the letter. We strip this because the PDF generator adds
        its own branded signature block with a handwritten image.
        """
        # Match common sign-off patterns at the end of the text
        patterns = [
            # "Yours sincerely," followed by name/title lines
            r'\n*Yours\s+(sincerely|faithfully),?\s*\n.*$',
            # "Kind regards," followed by name/title lines
            r'\n*Kind\s+regards,?\s*\n.*$',
            # "Best regards," followed by name/title lines
            r'\n*Best\s+regards,?\s*\n.*$',
            # "Warm regards," followed by name/title lines
            r'\n*Warm\s+regards,?\s*\n.*$',
        ]
        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
        return text.rstrip()

    def _setup_styles(self):
        """Define custom paragraph styles."""
        self.styles.add(
            ParagraphStyle(
                "LetterBody",
                parent=self.styles["Normal"],
                fontName="Times-Roman",
                fontSize=10.5,
                leading=14,
                spaceAfter=6,
            )
        )
        self.styles.add(
            ParagraphStyle(
                "LetterHeading",
                parent=self.styles["Heading2"],
                fontName="Times-Bold",
                fontSize=12,
                textColor=NAVY,
                spaceAfter=4,
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
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        story = []

        # --- Letterhead ---
        story.append(self._build_letterhead())
        story.append(Spacer(1, 5 * mm))

        # --- Horizontal rule ---
        story.append(self._gold_rule())
        story.append(Spacer(1, 3 * mm))

        # --- Property images (Street View + map side by side) ---
        if street_view_image or static_map_image:
            story.append(self._build_property_images(street_view_image, static_map_image))
            story.append(Spacer(1, 3 * mm))

        # --- Recipient address ---
        for line in recipient_address.split(","):
            story.append(
                Paragraph(line.strip(), self.styles["LetterBody"])
            )
        story.append(Spacer(1, 4 * mm))

        # --- Letter content (strip AI-generated signature) ---
        cleaned_content = self._strip_ai_signature(letter_content)
        paragraphs = cleaned_content.split("\n\n")
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # Replace newlines within paragraph with <br/>
            para = para.replace("\n", "<br/>")
            story.append(Paragraph(para, self.styles["LetterBody"]))

        story.append(Spacer(1, 2 * mm))

        # --- Signature area (branded, with handwritten signature image) ---
        story.append(self._build_signature())
        story.append(Spacer(1, 3 * mm))

        # --- Gold rule ---
        story.append(self._gold_rule())
        story.append(Spacer(1, 3 * mm))

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

        # --- QR Code + Footer (side by side to save space) ---
        story.append(self._build_qr_footer(qr_url))

        doc.build(story)
        return buf.getvalue()

    def _build_letterhead(self) -> Table:
        """Build the letterhead with logo and contact info."""
        assets_dir = Path(__file__).parent.parent.parent.parent / "assets"
        logo_path = assets_dir / "logos" / "logo.png"

        left = []
        if logo_path.exists():
            try:
                logo = Image(str(logo_path), width=65 * mm, height=20 * mm)
                left.append(logo)
            except Exception:
                left.append(Paragraph(client_config.company_name, self.styles["CompanyName"]))
                left.append(
                    Paragraph(
                        f"Est. {client_config.trading_since} | Specialists in Extensions & Loft Conversions",
                        self.styles["CompanyTagline"],
                    )
                )
        else:
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
        right.append(Paragraph(client_config.phone, contact_style))
        right.append(Paragraph(client_config.email, contact_style))
        right.append(Paragraph(client_config.website, contact_style))
        right.append(Paragraph(client_config.office_address, contact_style))

        table_data = [[left, right]]
        t = Table(table_data, colWidths=[100 * mm, 60 * mm])
        t.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ])
        )
        return t

    def _build_signature(self) -> Table:
        """Build signature block with optional handwritten signature image."""
        assets_dir = Path(__file__).parent.parent.parent.parent / "assets"
        sig_path = assets_dir / "signatures" / "signature.png"

        elements = []
        elements.append(Paragraph("Yours sincerely,", self.styles["LetterBody"]))
        elements.append(Spacer(1, 1 * mm))

        if sig_path.exists():
            try:
                sig_img = Image(str(sig_path), width=35 * mm, height=9 * mm)
                elements.append(sig_img)
            except Exception:
                elements.append(Spacer(1, 6 * mm))
        else:
            elements.append(Spacer(1, 6 * mm))

        sig_style = ParagraphStyle(
            "SignatureText",
            parent=self.styles["LetterBody"],
            fontSize=10,
            leading=13,
            spaceAfter=0,
        )
        elements.append(
            Paragraph(
                f"<b>{client_config.owner_name}</b><br/>"
                f"Director, {client_config.company_name}",
                sig_style,
            )
        )

        # Wrap in a single-cell table to keep together
        t = Table([[elements]], colWidths=[160 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def _build_qr_footer(self, qr_url: Optional[str] = None) -> Table:
        """Build QR code and footer combined in a compact layout."""
        story_parts = []

        # Gold rule above footer area
        story_parts.append(self._gold_rule())
        story_parts.append(Spacer(1, 2 * mm))

        if qr_url:
            # QR code on the left, footer text on the right
            qr_bytes = QRService.generate_qr_image(qr_url, size=100)
            qr_image = Image(io.BytesIO(qr_bytes), width=22 * mm, height=22 * mm)

            qr_label_style = ParagraphStyle(
                "QRLabel",
                parent=self.styles["Normal"],
                fontName="Times-Italic",
                fontSize=7.5,
                textColor=LIGHT_BLUE,
                leading=10,
            )
            qr_cell = [
                qr_image,
                Spacer(1, 1 * mm),
                Paragraph("Scan for a free quote", qr_label_style),
            ]

            footer_style = ParagraphStyle(
                "FooterRight",
                parent=self.styles["Normal"],
                fontName="Times-Roman",
                fontSize=7,
                textColor=colors.gray,
                alignment=2,  # right
                leading=10,
            )
            footer_text = (
                f"{client_config.company_name}<br/>"
                f"{client_config.phone} | {client_config.website}<br/>"
                f"Company Reg: {client_config.legal['company_registration']}<br/>"
                f"VAT: {client_config.legal['vat_number']}<br/>"
                f"Public Liability: £{client_config.legal['public_liability_amount']}"
            )
            footer_cell = [Paragraph(footer_text, footer_style)]

            row = Table([[qr_cell, footer_cell]], colWidths=[35 * mm, 125 * mm])
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story_parts.append(row)
        else:
            # No QR — just centered footer
            footer_text = (
                f"{client_config.company_name} | {client_config.phone} | "
                f"{client_config.website}<br/>"
                f"Company Reg: {client_config.legal['company_registration']} | "
                f"VAT: {client_config.legal['vat_number']} | "
                f"Public Liability: £{client_config.legal['public_liability_amount']}"
            )
            story_parts.append(Paragraph(footer_text, self.styles["Footer"]))

        # Wrap everything so it stays together
        wrapper_data = [[part] for part in story_parts]
        wrapper = Table(wrapper_data, colWidths=[160 * mm])
        wrapper.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ]))
        return wrapper

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
