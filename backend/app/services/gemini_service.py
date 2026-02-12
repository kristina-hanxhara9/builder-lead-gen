"""Google Gemini API wrapper using the new google.genai SDK.

Uses the Gemini Files API for native PDF upload — Google reads PDFs natively
with full document understanding (layout, tables, images, text).
"""

import base64
import io
import json
import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from google import genai
from google.genai import types

from app.core.config import client_config, settings

logger = logging.getLogger(__name__)

# Lazy-initialised client (avoid crash if API key not set at import time)
_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client (lazy init)."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

# Cost tracking (approximate per-token costs in GBP)
COST_PER_1K_INPUT = {
    "gemini-2.0-flash": 0.000075,
    "gemini-2.5-flash-preview-04-17": 0.000075,
}
COST_PER_1K_OUTPUT = {
    "gemini-2.0-flash": 0.0003,
    "gemini-2.5-flash-preview-04-17": 0.0003,
}

# Comprehensive extraction prompt — more fields, better structure
EXTRACTION_PROMPT = """You are an expert at reading UK planning application documents.
Analyse this PDF thoroughly and extract ALL available information.

Return a JSON object with these fields (use null if not found):

{
  "property_type": "detached | semi-detached | terraced | flat | bungalow | maisonette | other",
  "work_description": "detailed summary of ALL proposed work — be thorough",
  "work_category": "extension | loft_conversion | garage_conversion | kitchen_extension | basement | renovation | new_build | change_of_use | demolition_rebuild | other",
  "estimated_cost": null or number in GBP,
  "bedrooms_before": null or number,
  "bedrooms_after": null or number,
  "floor_area_added_m2": null or number,
  "total_floor_area_m2": null or number,
  "num_storeys": null or number of storeys (existing),
  "storeys_proposed": null or number of storeys (proposed/after),
  "materials": ["list", "of", "materials", "mentioned"],
  "planning_reference": "reference number if visible",
  "applicant_name": "name if shown",
  "architect_name": "architect or agent name if shown",
  "contractor_name": "builder/contractor if mentioned",
  "site_area_m2": null or number,
  "conservation_area": true/false/null,
  "listed_building": true/false/null,
  "tree_preservation": true/false/null,
  "parking_spaces": null or number,
  "proposed_use": "residential | commercial | mixed | other",
  "roof_type": "pitched | flat | mansard | hip | gable | null",
  "construction_method": "traditional brick | timber frame | steel frame | ICF | SIPs | null",
  "heating_system": "gas boiler | heat pump | electric | other | null",
  "renewable_energy": "solar panels | heat pump | other | null",
  "document_type": "application form | design and access statement | floor plans | elevations | site plan | structural report | other"
}

IMPORTANT:
- Read EVERY page of the document carefully
- Extract measurements, dimensions, and areas wherever mentioned
- Identify the document type (form, D&A statement, drawings, etc.)
- For work_description, be as detailed as possible — mention dimensions, materials, layout changes
- Return ONLY valid JSON, no markdown formatting, no commentary"""


class GeminiService:
    """Wrapper for Gemini API calls using the new google.genai SDK.

    Uses the Files API for native PDF reading — Google processes the entire
    document including layout, tables, diagrams, and handwriting.
    """

    def __init__(self):
        self.client = _get_client()
        self.extraction_model = client_config.gemini_config.get(
            "model_extraction", "gemini-2.0-flash"
        )
        self.generation_model = client_config.gemini_config.get(
            "model_generation", "gemini-2.0-flash"
        )
        self.total_cost_gbp = 0.0

    async def extract_from_pdf(self, pdf_bytes: bytes) -> tuple[dict, float]:
        """Extract structured data from a planning application PDF.

        Uses the Gemini Files API for native PDF understanding.
        Google reads the full document — text, tables, images, layout.

        Returns: (extracted_data, confidence_score 0.0–1.0)
        """
        try:
            # Upload PDF to Gemini Files API for native processing
            uploaded_file = self.client.files.upload(
                file=io.BytesIO(pdf_bytes),
                config=types.UploadFileConfig(
                    mime_type="application/pdf",
                    display_name="planning_application.pdf",
                ),
            )

            logger.info(
                f"PDF uploaded to Gemini: {uploaded_file.name} "
                f"({len(pdf_bytes):,} bytes)"
            )

            # Generate with the uploaded file — Gemini reads it natively
            response = self.client.models.generate_content(
                model=self.extraction_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_uri(
                                file_uri=uploaded_file.uri,
                                mime_type="application/pdf",
                            ),
                            types.Part.from_text(text=EXTRACTION_PROMPT),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )

            text = response.text.strip()

            # Strip markdown code fences if present (shouldn't be with response_mime_type)
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0].strip()

            data = json.loads(text)

            # Gemini sometimes wraps response in a JSON array
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            # Calculate confidence based on fields extracted
            # Weight important fields higher
            important_fields = [
                "property_type", "work_description", "work_category",
                "materials", "planning_reference", "floor_area_added_m2",
            ]
            secondary_fields = [
                "estimated_cost", "bedrooms_before", "bedrooms_after",
                "applicant_name", "num_storeys", "conservation_area",
                "listed_building", "architect_name", "document_type",
                "construction_method", "roof_type",
            ]

            important_filled = sum(
                1 for f in important_fields
                if data.get(f) is not None and data.get(f) != [] and data.get(f) != ""
            )
            secondary_filled = sum(
                1 for f in secondary_fields
                if data.get(f) is not None and data.get(f) != [] and data.get(f) != ""
            )

            # Weighted: important fields worth 2x
            max_score = len(important_fields) * 2 + len(secondary_fields)
            actual_score = important_filled * 2 + secondary_filled
            confidence = round(min(actual_score / max_score, 1.0), 2)

            # Track cost
            cost = self._estimate_cost(self.extraction_model, response)
            self.total_cost_gbp += cost

            # Clean up uploaded file
            try:
                self.client.files.delete(name=uploaded_file.name)
            except Exception:
                pass  # Non-critical

            total_filled = sum(
                1 for v in data.values()
                if v is not None and v != [] and v != ""
            )
            logger.info(
                f"Extraction complete: {total_filled} fields filled, "
                f"confidence={confidence:.0%}, cost=£{cost:.4f}"
            )

            return data, confidence

        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {e}")
            return {}, 0.0
        except Exception as e:
            logger.error(f"Gemini PDF extraction failed: {e}")
            return {}, 0.0

    async def extract_from_pdf_inline(self, pdf_bytes: bytes) -> tuple[dict, float]:
        """Fallback: extract using inline base64 PDF (no Files API upload).

        Use this if the Files API upload fails or for smaller PDFs.
        """
        try:
            response = self.client.models.generate_content(
                model=self.extraction_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(
                                data=pdf_bytes,
                                mime_type="application/pdf",
                            ),
                            types.Part.from_text(text=EXTRACTION_PROMPT),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                    response_mime_type="application/json",
                ),
            )

            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0].strip()

            data = json.loads(text)

            # Gemini sometimes wraps response in a JSON array
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            total_fields = 25
            filled = sum(
                1 for v in data.values()
                if v is not None and v != [] and v != ""
            )
            confidence = round(filled / total_fields, 2)

            cost = self._estimate_cost(self.extraction_model, response)
            self.total_cost_gbp += cost

            return data, confidence

        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON (inline): {e}")
            return {}, 0.0
        except Exception as e:
            logger.error(f"Gemini inline extraction failed: {e}")
            return {}, 0.0

    async def generate_letter(
        self,
        address: str,
        planning_reference: str,
        work_description: str,
        property_type: str,
        planning_status: str,
        postcode_area: str,
        case_studies: list[dict],
        property_facts: Optional[dict] = None,
    ) -> Optional[str]:
        """Generate a personalized sales letter grounded in real data.

        Args:
            property_facts: Real data from EPC + planning extraction
                           (floor area, EPC rating, age, materials, etc.)
        """
        prompt_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "config"
            / "prompts"
            / "letter_generation.txt"
        )
        template = prompt_path.read_text()

        cs_text = ""
        for cs in case_studies:
            cs_text += (
                f"- {cs['title']} ({cs['location']}, {cs['year_completed']}): "
                f"{cs['work_type']}. Value: £{cs['project_value']}. "
                f"Client said: \"{cs['testimonial']}\"\n"
            )

        # Build property facts string from real EPC + extraction data
        facts_text = self._build_property_facts(property_facts or {})

        prompt = template.format(
            owner_name=client_config.owner_name,
            company_name=client_config.company_name,
            company_background=client_config.get_company_background(),
            address=address,
            planning_reference=planning_reference,
            work_description=work_description,
            property_type=property_type or "residential property",
            planning_status=planning_status or "submitted",
            postcode_area=postcode_area,
            trading_since=client_config.trading_since,
            case_studies=cs_text or "No similar projects available.",
            property_facts=facts_text,
        )

        try:
            response = self.client.models.generate_content(
                model=self.generation_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )
            letter_text = response.text.strip()

            cost = self._estimate_cost(self.generation_model, response)
            self.total_cost_gbp += cost

            return letter_text

        except Exception as e:
            logger.error(f"Gemini letter generation failed: {e}")
            return None

    @staticmethod
    def _build_property_facts(facts: dict) -> str:
        """Build a human-readable property facts section from real data.

        Only includes facts that actually exist — no fabrication.
        Data comes from EPC API + PDF extraction (via unified_data).
        """
        lines = []

        if facts.get("epc_rating"):
            line = f"- EPC Energy Rating: {facts['epc_rating']}"
            if facts.get("epc_potential_rating"):
                line += f" (potential: {facts['epc_potential_rating']})"
            lines.append(line)

        if facts.get("total_floor_area_m2"):
            lines.append(f"- Floor Area: {facts['total_floor_area_m2']}m²")

        if facts.get("floor_area_added_m2"):
            lines.append(f"- Proposed Additional Floor Area: {facts['floor_area_added_m2']}m²")

        if facts.get("construction_age"):
            lines.append(f"- Property Age: {facts['construction_age']}")

        if facts.get("bedrooms_before"):
            bed_text = f"- Bedrooms: {facts['bedrooms_before']}"
            if facts.get("bedrooms_after"):
                bed_text += f" → {facts['bedrooms_after']} (after work)"
            lines.append(bed_text)

        if facts.get("materials"):
            materials = facts["materials"]
            if isinstance(materials, list) and materials:
                lines.append(f"- Proposed Materials: {', '.join(materials)}")

        if facts.get("estimated_cost"):
            lines.append(f"- Estimated Project Cost: £{facts['estimated_cost']:,.0f}")

        if facts.get("walls"):
            lines.append(f"- Existing Walls: {facts['walls']}")

        if facts.get("roof"):
            lines.append(f"- Existing Roof: {facts['roof']}")

        if facts.get("heating"):
            lines.append(f"- Heating: {facts['heating']}")

        if facts.get("conservation_area"):
            lines.append("- Property is in a Conservation Area")

        if facts.get("listed_building"):
            lines.append("- Listed Building")

        if not lines:
            return "No additional property data available."

        return "\n".join(lines)

    def _estimate_cost(self, model_name: str, response) -> float:
        """Estimate API call cost in GBP."""
        try:
            usage = response.usage_metadata
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0

            input_cost = (input_tokens / 1000) * COST_PER_1K_INPUT.get(
                model_name, 0.0001
            )
            output_cost = (output_tokens / 1000) * COST_PER_1K_OUTPUT.get(
                model_name, 0.0004
            )

            return round(input_cost + output_cost, 6)
        except Exception:
            return 0.001  # Default estimate


async def download_pdf(url: str, session_url: str = "") -> Optional[bytes]:
    """Download a PDF from a URL.

    Council planning portals (Idox) require an active JSESSIONID cookie.
    If session_url is provided (the portal detail/documents page), we
    visit it first to establish a session, then download the PDF.

    Args:
        url: Direct PDF URL.
        session_url: Optional URL to visit first for session cookie
                     (e.g. the documents tab page).
    """
    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/pdf,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        ) as client:
            # Establish session if needed (Lambeth Idox requires JSESSIONID)
            if session_url:
                logger.debug(f"Establishing session via {session_url[:80]}")
                await client.get(session_url)

            resp = await client.get(url, headers={"Referer": session_url or url})
            resp.raise_for_status()
            if len(resp.content) < 100:
                logger.warning(f"PDF too small ({len(resp.content)} bytes): {url}")
                return None
            return resp.content
    except Exception as e:
        logger.error(f"Failed to download PDF from {url}: {e}")
        return None
