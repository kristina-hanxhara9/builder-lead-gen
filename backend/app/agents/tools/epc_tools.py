"""LangChain tools for EPC (Energy Performance Certificate) lookups.

These tools are used by Agent 2 (EPC Enricher) to fetch, cache, and
interpret EPC data for properties.
"""

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from app.core.redis import redis_client
from app.services.epc_api import EPCAPIService

logger = logging.getLogger(__name__)

# Module-level service instance
_epc_service: Optional[EPCAPIService] = None


def _get_epc_service() -> EPCAPIService:
    global _epc_service
    if _epc_service is None:
        _epc_service = EPCAPIService()
    return _epc_service


async def cleanup_epc_service():
    """Close the httpx client when done."""
    global _epc_service
    if _epc_service is not None:
        await _epc_service.close()
        _epc_service = None


@tool
async def lookup_epc_by_postcode(postcode: str, address_hint: str = "") -> str:
    """Look up Energy Performance Certificate data for a property by postcode.

    Uses the UK Government EPC API with optional fuzzy address matching.
    Results are cached in Redis for 7 days.

    Args:
        postcode: UK postcode (e.g. "SW11 5TF").
        address_hint: Optional full or partial address for better matching.

    Returns:
        JSON with EPC data including energy rating, property type,
        construction age, floor area, building fabric details. Returns
        empty result if no EPC found (common for newer properties).
    """
    service = _get_epc_service()
    try:
        epc_data = await service.get_epc_by_postcode(postcode, address_hint or None)
        if epc_data:
            return json.dumps({
                "found": True,
                "source": "cache" if epc_data.get("_from_cache") else "api",
                "data": epc_data,
                "summary": (
                    f"EPC Rating {epc_data.get('current_rating', '?')} "
                    f"(potential {epc_data.get('potential_rating', '?')}), "
                    f"{epc_data.get('property_type', 'unknown')} property, "
                    f"built {epc_data.get('construction_age_band', 'unknown')}, "
                    f"{epc_data.get('total_floor_area', '?')} m² floor area"
                ),
                "match_confidence": epc_data.get("_match_confidence", 0.0),
            })
        else:
            return json.dumps({
                "found": False,
                "source": "api",
                "data": None,
                "summary": f"No EPC data found for {postcode}. "
                           "This is normal for new builds or properties that haven't been sold/rented.",
                "match_confidence": 0.0,
            })
    except Exception as e:
        logger.error(f"EPC lookup failed: {e}")
        return json.dumps({
            "found": False,
            "source": "error",
            "data": None,
            "summary": f"EPC lookup error: {str(e)}",
            "match_confidence": 0.0,
        })


@tool
def check_epc_cache(postcode: str) -> str:
    """Check if we already have cached EPC data for a postcode.

    Useful for avoiding unnecessary API calls. The EPC API has rate limits
    so checking cache first is recommended.

    Args:
        postcode: UK postcode to check.

    Returns:
        JSON with cached (bool) and key information.
    """
    normalized = postcode.strip().upper().replace(" ", "")
    pattern = f"epc:{normalized}:*"
    keys = redis_client.keys(pattern)
    if keys:
        ttl = redis_client.ttl(keys[0])
        return json.dumps({
            "cached": True,
            "keys_found": len(keys),
            "ttl_seconds": ttl,
            "message": f"Found {len(keys)} cached EPC record(s) for {postcode}. "
                       f"Cache expires in {ttl // 3600} hours.",
        })
    return json.dumps({
        "cached": False,
        "keys_found": 0,
        "ttl_seconds": 0,
        "message": f"No cached EPC data for {postcode}. Will need to call the API.",
    })


@tool
def interpret_epc_rating(rating: str, efficiency_score: int = 0) -> str:
    """Interpret an EPC energy rating for use in sales letter personalisation.

    Helps the agent understand what the EPC rating means for the homeowner
    and how it relates to their planned building work.

    Args:
        rating: EPC rating letter (A-G).
        efficiency_score: Numeric efficiency score (1-100).

    Returns:
        JSON with interpretation and suggestions for the sales letter.
    """
    interpretations = {
        "A": {"quality": "excellent", "opportunity": "low", "description": "Very energy efficient — top of the scale"},
        "B": {"quality": "good", "opportunity": "low", "description": "Energy efficient — above average"},
        "C": {"quality": "average", "opportunity": "medium", "description": "Average efficiency — room for improvement"},
        "D": {"quality": "below_average", "opportunity": "medium", "description": "Below average — many improvement opportunities"},
        "E": {"quality": "poor", "opportunity": "high", "description": "Poor efficiency — significant improvement needed"},
        "F": {"quality": "very_poor", "opportunity": "high", "description": "Very poor — major upgrade opportunities"},
        "G": {"quality": "worst", "opportunity": "very_high", "description": "Lowest rated — substantial upgrade needed"},
    }

    info = interpretations.get(rating.upper(), {
        "quality": "unknown",
        "opportunity": "unknown",
        "description": "Rating not recognised",
    })

    letter_angle = ""
    if info["opportunity"] in ("high", "very_high"):
        letter_angle = (
            "Mention that the extension/renovation is an opportunity to improve "
            "the property's energy efficiency at the same time."
        )
    elif info["opportunity"] == "medium":
        letter_angle = (
            "Could mention energy-efficient materials and insulation "
            "as part of the building work."
        )

    return json.dumps({
        "rating": rating.upper(),
        "efficiency_score": efficiency_score,
        **info,
        "letter_angle": letter_angle,
    })


# Convenience list for agent construction
EPC_TOOLS = [lookup_epc_by_postcode, check_epc_cache, interpret_epc_rating]
