"""Agent 3: Data Combination.

Merges planning app data, extracted PDF data, and EPC data into
a unified structure with derived fields. Uses deterministic logic
(no LLM needed) — this agent is a pure function, not a tool-calling agent.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from app.agents.state import AgentState
from app.core.config import client_config

logger = logging.getLogger(__name__)

# Average property values by postcode district (approximate, for scoring)
PROPERTY_VALUE_ESTIMATES: dict[str, int] = {
    "SW1":  2_000_000,
    "SW3":  1_800_000,
    "SW4":    750_000,
    "SW6":    900_000,
    "SW7":  1_500_000,
    "SW10": 1_200_000,
    "SW11":   850_000,   # Battersea
    "SW12":   750_000,   # Balham
    "SW13":   950_000,   # Barnes
    "SW14":   800_000,   # Mortlake
    "SW15":   900_000,   # Putney
    "SW16":   550_000,   # Streatham
    "SW17":   650_000,   # Tooting
    "SW18":   700_000,   # Wandsworth
    "SW19":   600_000,   # Wimbledon
    "SW20":   650_000,   # West Wimbledon
    "TW9":    800_000,   # Richmond
    "TW10":   950_000,   # Ham / Petersham
    "SE1":    650_000,
    "SE11":   600_000,
    "SE5":    550_000,
}

CATEGORY_TO_SERVICE = {
    "extension": "EXTENSION",
    "loft_conversion": "CONVERSION_LOFT",
    "loft conversion": "CONVERSION_LOFT",
    "garage_conversion": "CONVERSION_GARAGE",
    "garage conversion": "CONVERSION_GARAGE",
    "kitchen_extension": "KITCHEN",
    "kitchen extension": "KITCHEN",
    "basement": "BASEMENT",
    "renovation": "RENOVATION",
    "new_build": "NEW_BUILD",
    "other": None,
}


def combine_data(state: AgentState) -> dict:
    """Merge all data sources into a unified structure with conflict resolution.

    Conflict resolution priorities:
    - Property type: EPC > Extracted > "Unknown"
    - Bedroom count: EPC > Extracted
    - Address: Planning app data (canonical)
    - Work description: Extracted > Planning app

    Derived fields:
    - property_value_estimate (from district lookup table)
    - distance_from_office_km (Haversine calculation)
    - work_type_standardized (mapped to our service categories)
    - in_target_area / in_adjacent_area (geography flags)
    """
    planning = state["planning_app_data"]
    extracted = state.get("extracted_data") or {}
    epc = state.get("epc_data") or {}

    postcode = planning.get("postcode", "")
    district = _extract_district(postcode)
    conflict_resolutions = []
    data_sources = ["planning_application"]

    if extracted:
        data_sources.append("gemini_extraction")
    if epc:
        data_sources.append("epc_api")

    # ── Property type (EPC > Extracted > default) ────────────
    epc_type = epc.get("property_type")
    ext_type = extracted.get("property_type")
    if epc_type and ext_type and epc_type.lower() != ext_type.lower():
        conflict_resolutions.append(
            f"property_type: EPC='{epc_type}' vs Extracted='{ext_type}' → used EPC"
        )
    property_type = epc_type or ext_type or "Unknown"

    # ── Work description (Extracted > Planning) ───────────────
    work_description = extracted.get("work_description") or planning.get("description", "")
    work_category = extracted.get("work_category") or _infer_work_type(work_description)

    # Standardise to our service categories
    work_type_std = client_config.matches_work_type(work_description)
    if not work_type_std and work_category:
        work_type_std = CATEGORY_TO_SERVICE.get(work_category)

    # ── Property value estimate ───────────────────────────────
    property_value = PROPERTY_VALUE_ESTIMATES.get(district, 500_000)

    # Adjust based on EPC floor area (larger = higher value)
    floor_area = epc.get("total_floor_area")
    if floor_area and floor_area > 150:
        property_value = int(property_value * 1.2)
        conflict_resolutions.append(
            f"property_value: adjusted +20% for large floor area ({floor_area}m²)"
        )

    # ── Distance from office ──────────────────────────────────
    distance_km = client_config.calculate_distance(postcode)

    # ── Build unified data ────────────────────────────────────
    unified = {
        # Address
        "address": planning.get("address", ""),
        "postcode": postcode,
        "district": district,
        "local_authority": planning.get("local_authority", ""),

        # Planning
        "planning_reference": planning.get("reference", ""),
        "planning_status": planning.get("decision", "Pending"),
        "submitted_date": planning.get("submitted_date"),
        "decision_date": planning.get("decision_date"),
        "application_type": planning.get("application_type", ""),
        "applicant_name": (
            extracted.get("applicant_name")
            or planning.get("applicant_name")
        ),

        # Property
        "property_type": property_type,
        "construction_age": epc.get("construction_age_band"),
        "total_floor_area_m2": epc.get("total_floor_area"),
        "epc_rating": epc.get("current_rating"),
        "epc_potential_rating": epc.get("potential_rating"),
        "epc_efficiency": epc.get("current_energy_efficiency"),

        # Work
        "work_description": work_description,
        "work_category": work_category,
        "work_type_standardized": work_type_std,
        "estimated_cost": extracted.get("estimated_cost"),
        "floor_area_added_m2": extracted.get("floor_area_added_m2"),
        "materials": extracted.get("materials", []),
        "bedrooms_before": extracted.get("bedrooms_before"),
        "bedrooms_after": extracted.get("bedrooms_after"),
        "num_storeys": extracted.get("num_storeys"),

        # Building fabric (EPC)
        "walls": epc.get("walls_description"),
        "roof": epc.get("roof_description"),
        "windows": epc.get("windows_description"),
        "heating": epc.get("main_heating_description"),

        # Constraints
        "conservation_area": extracted.get("conservation_area"),
        "listed_building": extracted.get("listed_building"),

        # Derived
        "property_value_estimate": property_value,
        "distance_from_office_km": distance_km,
        "in_target_area": client_config.matches_service_area(postcode),
        "in_adjacent_area": client_config.is_adjacent_area(postcode),

        # Data quality
        "data_sources": data_sources,
        "conflict_resolutions": conflict_resolutions,
    }

    logger.info(
        f"Agent 3 combined: {property_type} in {district}, "
        f"work_type={work_type_std}, value=£{property_value:,}, "
        f"sources={data_sources}, conflicts={len(conflict_resolutions)}"
    )

    return {
        "unified_data": unified,
        "errors": [],
        "agent_logs": [
            f"[Agent 3 @ {datetime.utcnow().isoformat()}] "
            f"Combined {len(data_sources)} sources → {property_type} in {district}, "
            f"work={work_type_std}, value=£{property_value:,}, "
            f"{len(conflict_resolutions)} conflicts resolved"
        ],
        "processing_steps": [{
            "agent": "data_combiner",
            "status": "complete",
            "data_sources": data_sources,
            "conflicts_resolved": len(conflict_resolutions),
            "property_type": property_type,
            "work_type": work_type_std,
            "property_value": property_value,
        }],
        "current_agent": "data_combiner",
    }


def _extract_district(postcode: str) -> str:
    """Extract district from a UK postcode (e.g. 'SW11 5TF' → 'SW11')."""
    clean = postcode.strip().upper().replace(" ", "")
    if len(clean) >= 5:
        return clean[:-3].strip()
    return clean


def _infer_work_type(description: str) -> str:
    """Infer work category from description text."""
    desc = description.lower()
    if "loft" in desc or "dormer" in desc or "mansard" in desc:
        return "loft_conversion"
    if "basement" in desc:
        return "basement"
    if "garage" in desc and "conver" in desc:
        return "garage_conversion"
    if "kitchen" in desc and ("extension" in desc or "extend" in desc):
        return "kitchen_extension"
    if "extension" in desc or "extend" in desc:
        return "extension"
    if "renovation" in desc or "refurbish" in desc:
        return "renovation"
    return "other"
