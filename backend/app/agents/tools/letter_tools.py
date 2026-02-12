"""LangChain tools for letter generation and PDF creation.

These tools are used by Agent 5 (Letter Generator) to create
personalised sales letters and branded PDFs with property imagery.
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from app.core.config import client_config
from app.services.gemini_service import GeminiService
from app.services.google_maps_service import GoogleMapsService
from app.services.pdf_generator import PDFGenerator
from app.services.qr_service import QRService

logger = logging.getLogger(__name__)

# Module-level service instances
_gemini: Optional[GeminiService] = None


def _get_gemini() -> GeminiService:
    global _gemini
    if _gemini is None:
        _gemini = GeminiService()
    return _gemini


def reset_gemini():
    """Reset the module-level Gemini service."""
    global _gemini
    _gemini = None


@tool
def select_case_studies(
    work_type: str,
    district: str = "",
    max_studies: int = 3,
) -> str:
    """Select the most relevant case studies for a personalised letter.

    Matches case studies from our portfolio to the type of work the
    homeowner is planning. Prioritises projects in the same area.

    Args:
        work_type: Standardised work type (e.g. "EXTENSION", "CONVERSION_LOFT").
        district: Postcode district for local relevance (e.g. "SW11").
        max_studies: Maximum number of case studies to include (default 3).

    Returns:
        JSON with selected case studies and personalisation notes.
    """
    all_studies = client_config.get_case_studies_for_work_type(work_type)

    # Sort by local relevance if district provided
    if district:
        def relevance(cs):
            location = cs.get("location", "").upper()
            if district.upper() in location:
                return 0  # Same district — best
            if location.startswith("SW"):
                return 1  # Same area
            return 2  # Different area

        all_studies.sort(key=relevance)

    selected = all_studies[:max_studies]

    return json.dumps({
        "case_studies": selected,
        "count": len(selected),
        "total_available": len(all_studies),
        "message": (
            f"Selected {len(selected)} case studies matching work type '{work_type}'. "
            + (f"Prioritised projects near {district}." if district else "")
        ),
    })


@tool
async def generate_letter_content(
    address: str,
    planning_reference: str,
    work_description: str,
    property_type: str = "residential property",
    planning_status: str = "submitted",
    postcode_area: str = "",
    case_studies_json: str = "[]",
    property_facts_json: str = "{}",
) -> str:
    """Generate a personalised sales letter using Gemini AI.

    Creates a professional, warm letter grounded in real data from
    the homeowner's planning application and EPC records. The letter
    only references facts that are actually provided.

    Args:
        address: Full property address.
        planning_reference: Council planning reference number.
        work_description: Description of the planned building work.
        property_type: E.g. "detached", "semi-detached", "terraced".
        planning_status: E.g. "approved", "pending", "submitted".
        postcode_area: Postcode district for local references.
        case_studies_json: JSON string of case studies to reference.
        property_facts_json: JSON string of real property data from
            EPC and planning extraction (floor area, energy rating,
            building age, materials, bedrooms, etc.)

    Returns:
        JSON with letter content, word count, and cost.
    """
    # LLM may pass strings or already-parsed dicts/lists
    if isinstance(case_studies_json, dict):
        # LLM sometimes passes the full select_case_studies output
        case_studies = case_studies_json.get("case_studies", [])
    elif isinstance(case_studies_json, list):
        case_studies = case_studies_json
    else:
        try:
            parsed = json.loads(case_studies_json) if case_studies_json else []
            if isinstance(parsed, dict):
                case_studies = parsed.get("case_studies", [])
            else:
                case_studies = parsed
        except (json.JSONDecodeError, TypeError):
            case_studies = []

    if isinstance(property_facts_json, dict):
        property_facts = property_facts_json
    else:
        try:
            property_facts = json.loads(property_facts_json) if property_facts_json else {}
        except (json.JSONDecodeError, TypeError):
            property_facts = {}

    gemini = _get_gemini()
    letter_text = await gemini.generate_letter(
        address=address,
        planning_reference=planning_reference,
        work_description=work_description,
        property_type=property_type,
        planning_status=planning_status,
        postcode_area=postcode_area,
        case_studies=case_studies,
        property_facts=property_facts,
    )

    if letter_text:
        word_count = len(letter_text.split())
        return json.dumps({
            "success": True,
            "letter_content": letter_text,
            "word_count": word_count,
            "cost_gbp": gemini.total_cost_gbp,
            "message": f"Generated {word_count}-word personalised letter.",
        })
    else:
        return json.dumps({
            "success": False,
            "letter_content": None,
            "word_count": 0,
            "cost_gbp": gemini.total_cost_gbp,
            "message": "Letter generation failed — Gemini returned no content.",
        })


@tool
def create_branded_pdf(
    letter_content: str,
    recipient_address: str,
    case_studies_json: str = "[]",
    qr_url: str = "",
) -> str:
    """Create a professionally branded PDF letter with company letterhead.

    Generates a print-ready A4 PDF with:
    - Company letterhead (Smith & Sons branding)
    - Gold horizontal rules
    - Formatted letter content
    - Case study section
    - QR code for response tracking
    - Legal footer

    Args:
        letter_content: The letter text to include.
        recipient_address: Comma-separated address lines.
        case_studies_json: JSON string of case studies for the PDF.
        qr_url: QR code tracking URL.

    Returns:
        JSON with success status and PDF size. The PDF bytes are stored
        internally for retrieval.
    """
    try:
        case_studies = json.loads(case_studies_json) if case_studies_json else []
    except json.JSONDecodeError:
        case_studies = []

    try:
        # Pull property images if available from fetch_property_images
        street_view = getattr(fetch_property_images, "_street_view", None)
        static_map = getattr(fetch_property_images, "_static_map", None)

        pdf_gen = PDFGenerator()
        pdf_bytes = pdf_gen.generate_letter_pdf(
            letter_content=letter_content,
            recipient_address=recipient_address,
            case_studies=case_studies,
            qr_url=qr_url,
            street_view_image=street_view,
            static_map_image=static_map,
        )

        # Store internally for retrieval
        create_branded_pdf._last_pdf = pdf_bytes

        return json.dumps({
            "success": True,
            "pdf_size_bytes": len(pdf_bytes),
            "pdf_size_kb": round(len(pdf_bytes) / 1024, 1),
            "message": f"Created branded PDF ({len(pdf_bytes) / 1024:.1f} KB). Ready for sending.",
        })
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return json.dumps({
            "success": False,
            "pdf_size_bytes": 0,
            "message": f"PDF generation error: {str(e)}",
        })


# Initialise storage
create_branded_pdf._last_pdf = None


@tool
def generate_qr_tracking_url(letter_id: str) -> str:
    """Generate a unique QR code tracking URL for a letter.

    Each letter gets a unique URL so we can track when homeowners
    scan the QR code — indicating interest.

    Args:
        letter_id: The planning application or letter ID.

    Returns:
        JSON with the tracking URL.
    """
    url = QRService.generate_tracking_url(letter_id)
    return json.dumps({
        "qr_url": url,
        "message": f"Generated tracking URL for letter {letter_id}.",
    })


@tool
async def fetch_property_images(address: str, postcode: str = "") -> str:
    """Fetch Google Street View image and static map for a property.

    Geocodes the address, then fetches:
    1. Street View photo of the property (if available)
    2. Static map showing property location with office marker

    The images are stored internally for use by create_branded_pdf.
    This makes the PDF letter much more professional and personal.

    Args:
        address: Full property address.
        postcode: UK postcode for disambiguation.

    Returns:
        JSON with street_view_available, map_available, and geocode info.
    """
    maps = GoogleMapsService()

    try:
        # Geocode the address
        geo = await maps.geocode_address(address, postcode)
        if not geo:
            return json.dumps({
                "street_view_available": False,
                "map_available": False,
                "geocoded": False,
                "message": "Could not geocode address — no images fetched.",
            })

        lat, lon = geo["lat"], geo["lon"]
        distance_km = maps.haversine_distance(lat, lon, 51.4550, -0.1910)

        # Fetch Street View
        sv_bytes = await maps.get_street_view_image(lat, lon, width=400, height=250)
        if sv_bytes:
            fetch_property_images._street_view = sv_bytes
        else:
            fetch_property_images._street_view = None

        # Fetch Static Map
        sm_bytes = await maps.get_static_map_image(lat, lon, width=400, height=250)
        if sm_bytes:
            fetch_property_images._static_map = sm_bytes
        else:
            fetch_property_images._static_map = None

        return json.dumps({
            "street_view_available": sv_bytes is not None,
            "street_view_size_bytes": len(sv_bytes) if sv_bytes else 0,
            "map_available": sm_bytes is not None,
            "map_size_bytes": len(sm_bytes) if sm_bytes else 0,
            "geocoded": True,
            "lat": lat,
            "lon": lon,
            "formatted_address": geo.get("formatted_address", ""),
            "distance_from_office_km": distance_km,
            "message": (
                f"Geocoded to {lat:.6f}, {lon:.6f} ({distance_km:.1f}km from office). "
                f"Street View: {'yes' if sv_bytes else 'no'}, "
                f"Map: {'yes' if sm_bytes else 'no'}."
            ),
        })

    except Exception as e:
        logger.error(f"Property image fetch failed: {e}")
        return json.dumps({
            "street_view_available": False,
            "map_available": False,
            "geocoded": False,
            "message": f"Image fetch error: {str(e)}",
        })
    finally:
        await maps.close()


# Initialise image storage
fetch_property_images._street_view = None
fetch_property_images._static_map = None


@tool
def get_company_context() -> str:
    """Get company background information for letter personalisation.

    Returns company details, services, and trading history that
    the letter generation prompt needs.

    Returns:
        JSON with company name, background text, services, and contact info.
    """
    return json.dumps({
        "company_name": client_config.company_name,
        "owner_name": client_config.owner_name,
        "trading_since": client_config.trading_since,
        "background": client_config.get_company_background(),
        "primary_services": client_config.primary_services,
        "secondary_services": client_config.secondary_services,
        "phone": client_config.phone,
        "email": client_config.email,
        "website": client_config.website,
    })


# Convenience list for agent construction
LETTER_TOOLS = [
    select_case_studies,
    generate_letter_content,
    fetch_property_images,
    create_branded_pdf,
    generate_qr_tracking_url,
    get_company_context,
]
