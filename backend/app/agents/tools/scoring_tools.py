"""LangChain tools for lead scoring.

These tools are used by Agent 4 (Scorer) to evaluate leads
across multiple dimensions and make go/no-go decisions.
Includes geocoding for precise distance measurement.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.tools import tool

from app.core.config import client_config

logger = logging.getLogger(__name__)


@tool
async def geocode_property(address: str, postcode: str = "") -> str:
    """Geocode a property address to get precise lat/lon coordinates.

    Uses Google Maps Geocoding API for accurate distance calculation
    instead of postcode-centre approximations.

    Args:
        address: Full property address.
        postcode: UK postcode for disambiguation.

    Returns:
        JSON with lat, lon, formatted_address, distance_from_office_km.
    """
    try:
        from app.services.google_maps_service import GoogleMapsService

        maps = GoogleMapsService()
        geo = await maps.geocode_address(address, postcode)
        if not geo:
            return json.dumps({
                "geocoded": False,
                "message": "Could not geocode address. Using postcode-centre fallback.",
            })

        # Calculate precise distance from office (SW18)
        distance = maps.haversine_distance(
            geo["lat"], geo["lon"], 51.4550, -0.1910
        )
        await maps.close()

        return json.dumps({
            "geocoded": True,
            "lat": geo["lat"],
            "lon": geo["lon"],
            "formatted_address": geo["formatted_address"],
            "distance_from_office_km": distance,
            "message": (
                f"Geocoded to {geo['lat']:.6f}, {geo['lon']:.6f}. "
                f"Precise distance from office: {distance:.2f} km."
            ),
        })

    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        return json.dumps({
            "geocoded": False,
            "message": f"Geocoding error: {str(e)}. Using postcode-centre fallback.",
        })


@tool
def score_geography(postcode: str, district: str = "", distance_km: float = 0.0) -> str:
    """Score a lead based on geographical proximity to our service area.

    Evaluates whether the property is in our target postcodes, an adjacent
    area, or outside our service range.

    Args:
        postcode: Full UK postcode of the property.
        district: Postcode district (e.g. "SW11"). Optional — derived from postcode.
        distance_km: Distance from our office in km. Optional — calculated if 0.

    Returns:
        JSON with score (0-30), max_points, in_target, in_adjacent, reasoning.
    """
    max_points = client_config.scoring_weights.get("geography", 30)

    in_target = client_config.matches_service_area(postcode)
    in_adjacent = client_config.is_adjacent_area(postcode)

    if distance_km == 0.0:
        distance_km = client_config.calculate_distance(postcode)

    if in_target:
        score = max_points
        reasoning = (
            f"Property in {postcode} is in our primary service area. "
            f"Distance: {distance_km:.1f} km from office. Full points awarded."
        )
    elif in_adjacent:
        score = max_points * 0.5
        reasoning = (
            f"Property in {postcode} is in adjacent area ({distance_km:.1f} km). "
            f"Serviceable but not primary zone. Half points."
        )
    else:
        score = 0.0
        reasoning = (
            f"Property in {postcode} is {distance_km:.1f} km away — "
            f"outside our service area. No points."
        )

    return json.dumps({
        "score": round(score, 1),
        "max_points": max_points,
        "in_target_area": in_target,
        "in_adjacent_area": in_adjacent,
        "distance_km": round(distance_km, 1),
        "reasoning": reasoning,
    })


@tool
def score_property_value(
    estimated_value: float,
    property_type: str = "",
    district: str = "",
) -> str:
    """Score a lead based on estimated property value.

    Higher value properties are better leads because they typically
    have larger budgets for building work.

    Args:
        estimated_value: Estimated property value in GBP.
        property_type: E.g. "detached", "semi-detached", "terraced", "flat".
        district: Postcode district for context.

    Returns:
        JSON with score (0-25), max_points, tier, reasoning.
    """
    max_points = client_config.scoring_weights.get("property_value", 25)

    if estimated_value >= 1_000_000:
        score = max_points
        tier = "premium"
        reasoning = f"£{estimated_value:,.0f} — premium property, excellent budget potential."
    elif estimated_value >= 500_000:
        score = max_points
        tier = "high"
        reasoning = f"£{estimated_value:,.0f} — high-value property, strong budget expectation."
    elif estimated_value >= 250_000:
        score = max_points * 0.8
        tier = "mid-high"
        reasoning = f"£{estimated_value:,.0f} — mid-high value, good budget likely."
    elif estimated_value >= 150_000:
        score = max_points * 0.6
        tier = "mid"
        reasoning = f"£{estimated_value:,.0f} — mid-range property, moderate budget."
    else:
        score = max_points * 0.4
        tier = "entry"
        reasoning = f"£{estimated_value:,.0f} — lower value, may have limited budget."

    # Bonus for detached properties (tend to have more work scope)
    adjustment = None
    if property_type and "detached" in property_type.lower() and "semi" not in property_type.lower():
        bonus = max_points * 0.1
        score = min(score + bonus, max_points)
        adjustment = f"+{bonus:.1f} bonus for detached property (larger scope potential)"

    return json.dumps({
        "score": round(score, 1),
        "max_points": max_points,
        "tier": tier,
        "estimated_value": estimated_value,
        "property_type": property_type,
        "reasoning": reasoning,
        "adjustment": adjustment,
    })


@tool
def score_work_type(work_description: str, work_category: str = "") -> str:
    """Score a lead based on the type of building work planned.

    Matches the work description to our primary and secondary services
    to determine relevance.

    Args:
        work_description: Description of the planned building work.
        work_category: Standardised category (e.g. "extension", "loft_conversion").

    Returns:
        JSON with score (0-30), max_points, matched_service, service_tier, reasoning.
    """
    max_points = client_config.scoring_weights.get("work_type", 30)

    # Try to match work type
    matched = client_config.matches_work_type(work_description)

    if matched and matched in client_config.primary_services:
        score = max_points
        tier = "primary"
        reasoning = (
            f"Work type '{matched}' is a PRIMARY service — this is our bread and butter. "
            f"Full points. Description: {work_description[:100]}..."
        )
    elif matched and matched in client_config.secondary_services:
        score = max_points * 0.67
        tier = "secondary"
        reasoning = (
            f"Work type '{matched}' is a SECONDARY service — we can do this but it's "
            f"not our core offering. Two-thirds points."
        )
    elif work_category:
        # Try the explicit category
        category_mapping = {
            "extension": "EXTENSION",
            "loft_conversion": "CONVERSION_LOFT",
            "garage_conversion": "CONVERSION_GARAGE",
            "kitchen_extension": "KITCHEN",
            "basement": "BASEMENT",
            "renovation": "RENOVATION",
        }
        mapped = category_mapping.get(work_category)
        if mapped and mapped in client_config.primary_services:
            score = max_points * 0.9
            tier = "primary_inferred"
            reasoning = (
                f"Category '{work_category}' maps to primary service '{mapped}'. "
                f"Slightly lower confidence as matched by category, not description."
            )
        elif mapped and mapped in client_config.secondary_services:
            score = max_points * 0.6
            tier = "secondary_inferred"
            reasoning = f"Category '{work_category}' maps to secondary service '{mapped}'."
        else:
            score = 0.0
            tier = "not_offered"
            reasoning = f"Work category '{work_category}' doesn't match any of our services."
    else:
        score = 0.0
        tier = "not_matched"
        reasoning = (
            f"Could not match work description to any service: "
            f"'{work_description[:100]}...'. No points."
        )

    return json.dumps({
        "score": round(score, 1),
        "max_points": max_points,
        "matched_service": matched,
        "service_tier": tier,
        "reasoning": reasoning,
    })


@tool
def score_timing(
    planning_status: str,
    submitted_date: str = "",
    decision_date: str = "",
) -> str:
    """Score a lead based on planning application timing.

    Recently approved applications are best (homeowner is ready to build).
    Pending applications are also good (early contact opportunity).

    Args:
        planning_status: E.g. "Approved", "Pending", "Submitted", "Refused".
        submitted_date: ISO date string of application submission.
        decision_date: ISO date string of decision (if any).

    Returns:
        JSON with score (0-15), max_points, status_type, days_old, reasoning.
    """
    max_points = client_config.scoring_weights.get("timing", 15)
    status = planning_status.lower() if planning_status else ""

    # Calculate days since submission
    days_old = 999
    if submitted_date:
        try:
            dt = datetime.fromisoformat(submitted_date.replace("Z", "+00:00"))
            days_old = (datetime.now() - dt.replace(tzinfo=None)).days
        except (ValueError, TypeError):
            pass

    if "approved" in status or "granted" in status:
        if days_old <= 30:
            score = max_points
            status_type = "approved_recent"
            reasoning = (
                f"Approved {days_old} days ago — perfect timing! "
                f"Homeowner is actively looking for a builder."
            )
        elif days_old <= 90:
            score = max_points * 0.53
            status_type = "approved_moderate"
            reasoning = (
                f"Approved {days_old} days ago — may already have quotes "
                f"but worth reaching out."
            )
        else:
            score = max_points * 0.33
            status_type = "approved_old"
            reasoning = (
                f"Approved {days_old} days ago — might have already started or "
                f"chosen a builder. Lower priority."
            )
    elif "pending" in status or "submitted" in status:
        score = max_points * 0.8
        status_type = "pending"
        reasoning = (
            f"Application pending/submitted — early contact opportunity. "
            f"Homeowner is in planning phase and receptive to builder suggestions."
        )
    elif "refused" in status or "rejected" in status:
        score = max_points * 0.1
        status_type = "refused"
        reasoning = (
            f"Application refused — low priority. They may reapply or change plans, "
            f"but not an active lead."
        )
    else:
        score = max_points * 0.33
        status_type = "unknown"
        reasoning = f"Status '{planning_status}' not recognised — default low score."

    return json.dumps({
        "score": round(score, 1),
        "max_points": max_points,
        "status_type": status_type,
        "days_old": days_old if days_old < 999 else None,
        "reasoning": reasoning,
    })


@tool
def make_lead_decision(
    total_score: float,
    breakdown: dict,
) -> str:
    """Make the final go/no-go decision on whether to create a lead and generate a letter.

    Uses the scoring thresholds from client config:
    - >= minimum_score (65): Create lead, manual letter approval
    - >= auto_send_threshold (85): Create lead, auto-approve letter
    - < minimum_score: Discard

    Args:
        total_score: Total lead score (0-100).
        breakdown: Dict of factor scores.

    Returns:
        JSON with decision, should_create_lead, should_generate_letter,
        auto_approve, reasoning.
    """
    min_score = client_config.minimum_score
    auto_threshold = client_config.auto_send_threshold

    if total_score >= auto_threshold:
        decision = "auto_approve"
        create_lead = True
        generate_letter = True
        auto_approve = True
        reasoning = (
            f"Score {total_score}/100 exceeds auto-send threshold ({auto_threshold}). "
            f"High-quality lead — creating lead and auto-approving letter."
        )
    elif total_score >= min_score:
        decision = "manual_review"
        create_lead = True
        generate_letter = True
        auto_approve = False
        reasoning = (
            f"Score {total_score}/100 meets minimum ({min_score}) but below "
            f"auto-send ({auto_threshold}). Creating lead and generating letter "
            f"for manual review."
        )
    else:
        decision = "discard"
        create_lead = False
        generate_letter = False
        auto_approve = False
        reasoning = (
            f"Score {total_score}/100 below minimum threshold ({min_score}). "
            f"Lead discarded — not worth pursuing."
        )

    return json.dumps({
        "decision": decision,
        "should_create_lead": create_lead,
        "should_generate_letter": generate_letter,
        "auto_approve": auto_approve,
        "total_score": total_score,
        "minimum_score": min_score,
        "auto_send_threshold": auto_threshold,
        "reasoning": reasoning,
    })


# Convenience list for agent construction
SCORING_TOOLS = [
    geocode_property,
    score_geography,
    score_property_value,
    score_work_type,
    score_timing,
    make_lead_decision,
]
