"""Settings API routes — read and update client_config.yaml from the UI."""

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import app.core.config as cfg

logger = logging.getLogger(__name__)


def _get_config():
    """Always return the current client_config (respects reloads)."""
    return cfg.client_config
router = APIRouter(prefix="/settings", tags=["settings"])

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "client_config.yaml"


# ── Schemas ──────────────────────────────────────────────────────────

class CompanyUpdate(BaseModel):
    name: str | None = None
    owner_name: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    office_address: str | None = None
    company_registration: str | None = None
    vat_number: str | None = None


class ServicesUpdate(BaseModel):
    primary: list[str] | None = None
    secondary: list[str] | None = None
    exclude: list[str] | None = None


class GeographicUpdate(BaseModel):
    districts: list[str] | None = None
    max_distance_km: int | None = None
    borough_councils: list[str] | None = None


class ScoringUpdate(BaseModel):
    weights: dict[str, int] | None = None
    minimum_score: int | None = None
    auto_send_threshold: int | None = None


class SettingsUpdateRequest(BaseModel):
    company: CompanyUpdate | None = None
    services: ServicesUpdate | None = None
    geographic_area: GeographicUpdate | None = None
    lead_scoring: ScoringUpdate | None = None


# ── Helpers ──────────────────────────────────────────────────────────

def _read_yaml() -> dict:
    """Read the raw YAML config (without env-var substitution)."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _write_yaml(data: dict) -> None:
    """Write updated config back to YAML."""
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _reload_client_config() -> None:
    """Reload the global client_config in-place after YAML changes."""
    import app.core.config as cfg

    # Clear the lru_cache so next call re-reads from disk
    cfg.get_client_config.cache_clear()
    new_config = cfg.get_client_config()

    # Update the module-level convenience reference
    cfg.client_config = new_config

    # Also re-import into local reference for any already-imported modules
    logger.info("Client config reloaded from disk")


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
def get_settings():
    """Return the full client configuration for the settings page."""
    cc = _get_config()
    return {
        "company": {
            "name": cc.company_name,
            "owner_name": cc.owner_name,
            "trading_since": cc.trading_since,
            "phone": cc.phone,
            "email": cc.email,
            "website": cc.website,
            "office_address": cc.office_address,
            "company_registration": cc.legal.get("company_registration", ""),
            "vat_number": cc.legal.get("vat_number", ""),
            "credentials": cc.credentials,
        },
        "services": {
            "primary": cc.primary_services,
            "secondary": cc.secondary_services,
            "exclude": cc.excluded_services,
        },
        "geographic_area": {
            "districts": cc.target_postcodes,
            "max_distance_km": cc.max_distance_km,
            "borough_councils": cc.borough_councils,
        },
        "lead_scoring": {
            "weights": cc.scoring_weights,
            "minimum_score": cc.minimum_score,
            "auto_send_threshold": cc.auto_send_threshold,
        },
        "letter_settings": {
            "auto_approve": cc.letter_auto_approve,
            "include_case_studies": cc.include_case_studies_count,
        },
    }


@router.put("")
def update_settings(body: SettingsUpdateRequest):
    """Update client configuration and reload.

    Accepts partial updates — only provided fields are changed.
    """
    data = _read_yaml()

    # ── Company ──
    if body.company:
        c = body.company
        if c.name is not None:
            data["company"]["name"] = c.name
        if c.owner_name is not None:
            data["company"]["owner_name"] = c.owner_name
        if c.phone is not None:
            data["company"]["contact"]["phone"] = c.phone
        if c.email is not None:
            data["company"]["contact"]["email"] = c.email
        if c.website is not None:
            data["company"]["contact"]["website"] = c.website
        if c.office_address is not None:
            data["company"]["contact"]["office_address"] = c.office_address
        if c.company_registration is not None:
            data["company"]["legal"]["company_registration"] = c.company_registration
        if c.vat_number is not None:
            data["company"]["legal"]["vat_number"] = c.vat_number

    # ── Services ──
    if body.services:
        s = body.services
        if s.primary is not None:
            data["services"]["primary"] = s.primary
        if s.secondary is not None:
            data["services"]["secondary"] = s.secondary
        if s.exclude is not None:
            data["services"]["exclude"] = s.exclude

    # ── Geographic Area ──
    if body.geographic_area:
        g = body.geographic_area
        if g.districts is not None:
            data["geographic_area"]["districts"] = g.districts
        if g.max_distance_km is not None:
            data["geographic_area"]["max_distance_km"] = g.max_distance_km
        if g.borough_councils is not None:
            data["geographic_area"]["borough_councils"] = g.borough_councils

    # ── Lead Scoring ──
    if body.lead_scoring:
        ls = body.lead_scoring
        if ls.weights is not None:
            total = sum(ls.weights.values())
            if total != 100:
                raise HTTPException(
                    status_code=422,
                    detail=f"Scoring weights must sum to 100, got {total}",
                )
            data["lead_scoring"]["weights"] = ls.weights
        if ls.minimum_score is not None:
            data["lead_scoring"]["minimum_score"] = ls.minimum_score
        if ls.auto_send_threshold is not None:
            data["lead_scoring"]["auto_send_threshold"] = ls.auto_send_threshold

    # Write and reload
    _write_yaml(data)
    _reload_client_config()

    return {"status": "updated", "message": "Settings saved and reloaded"}


@router.get("/councils")
def get_available_councils():
    """Return the list of configured borough councils (for dropdowns)."""
    return {
        "councils": [c.title() for c in _get_config().borough_councils],  # noqa: fresh read
    }


@router.get("/service-types")
def get_service_types():
    """Return all known service type codes."""
    return {
        "all_types": [
            "EXTENSION",
            "CONVERSION_LOFT",
            "KITCHEN",
            "CONVERSION_GARAGE",
            "BATHROOM",
            "CONVERSION_BASEMENT",
            "NEW_BUILD",
            "RENOVATION",
            "SOLAR_PV",
            "HEAT_PUMP",
            "GENERAL_RENOVATION",
        ],
        "primary": _get_config().primary_services,
        "secondary": _get_config().secondary_services,
        "exclude": _get_config().excluded_services,
    }
