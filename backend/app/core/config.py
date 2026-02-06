"""
Client configuration loader.

Loads config/client_config.yaml, substitutes environment variables,
validates required fields, and provides typed access throughout the app.

Usage:
    from app.core.config import client_config, settings

    company_name = client_config.company_name
    primary_color = client_config.brand_colors["primary"]
    case_studies = client_config.get_case_studies_for_work_type("EXTENSION")
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Infrastructure settings from environment variables."""

    database_url: str = "postgresql://builder:builder@localhost:5432/builder_leads"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    app_env: str = "development"
    debug: bool = True
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    gemini_api_key: str = ""
    stannp_api_key: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    epc_api_key: str = ""
    epc_api_email: str = ""
    google_maps_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars (POSTGRES_*, OPENAI_*, etc.)


# Postcode district centre coordinates (lat, lon) for distance calculation
_POSTCODE_CENTRES: dict[str, tuple[float, float]] = {
    "SW11": (51.4620, -0.1680),
    "SW12": (51.4435, -0.1520),
    "SW15": (51.4610, -0.2160),
    "SW17": (51.4280, -0.1680),
    "SW18": (51.4550, -0.1910),
    # Adjacent areas
    "SW1": (51.4975, -0.1357),
    "SW2": (51.4570, -0.1210),
    "SW3": (51.4887, -0.1698),
    "SW4": (51.4620, -0.1380),
    "SW5": (51.4920, -0.1880),
    "SW6": (51.4750, -0.1970),
    "SW7": (51.4940, -0.1760),
    "SW8": (51.4740, -0.1420),
    "SW9": (51.4680, -0.1150),
    "SW10": (51.4830, -0.1840),
    "SW13": (51.4720, -0.2370),
    "SW14": (51.4640, -0.2580),
    "SW16": (51.4170, -0.1360),
    "SW19": (51.4220, -0.2000),
    "SW20": (51.4090, -0.2250),
}

# Office postcode for distance calculations
_OFFICE_POSTCODE = "SW18"


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} placeholders in config values."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{(\w+)\}")
        matches = pattern.findall(value)
        for var_name in matches:
            env_val = os.getenv(var_name, "")
            value = value.replace(f"${{{var_name}}}", env_val)
        return value
    if isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


class ClientConfig:
    """Typed access to client_config.yaml with helper methods."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            # Look relative to project root
            root = Path(__file__).resolve().parent.parent.parent.parent
            config_path = str(root / "config" / "client_config.yaml")

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        self._data = _substitute_env_vars(raw)
        self._validate()

    def _validate(self) -> None:
        required = ["company", "services", "geographic_area", "lead_scoring"]
        for key in required:
            if key not in self._data:
                raise ValueError(f"Missing required config section: {key}")

        if not self._data["geographic_area"].get("districts"):
            raise ValueError("geographic_area.districts must not be empty")

        weights = self._data["lead_scoring"]["weights"]
        total = sum(weights.values())
        if total != 100:
            raise ValueError(f"lead_scoring weights must sum to 100, got {total}")

    # --- Company ---

    @property
    def company_name(self) -> str:
        return self._data["company"]["name"]

    @property
    def owner_name(self) -> str:
        return self._data["company"]["owner_name"]

    @property
    def trading_since(self) -> int:
        return self._data["company"]["trading_since"]

    @property
    def contact(self) -> dict:
        return self._data["company"]["contact"]

    @property
    def phone(self) -> str:
        return self._data["company"]["contact"]["phone"]

    @property
    def email(self) -> str:
        return self._data["company"]["contact"]["email"]

    @property
    def website(self) -> str:
        return self._data["company"]["contact"]["website"]

    @property
    def office_address(self) -> str:
        return self._data["company"]["contact"]["office_address"]

    @property
    def brand_colors(self) -> dict[str, str]:
        b = self._data["company"]["branding"]
        return {
            "primary": b["primary_color"],
            "secondary": b["secondary_color"],
            "accent": b["accent_color"],
        }

    @property
    def logo_path(self) -> str:
        return self._data["company"]["branding"]["logo_path"]

    @property
    def font_family(self) -> str:
        return self._data["company"]["branding"]["font_family"]

    @property
    def signature_path(self) -> str:
        return self._data["company"]["owner_signature_path"]

    @property
    def credentials(self) -> list[str]:
        return self._data["company"]["credentials"]

    @property
    def legal(self) -> dict:
        return self._data["company"]["legal"]

    # --- Services ---

    @property
    def primary_services(self) -> list[str]:
        return self._data["services"]["primary"]

    @property
    def secondary_services(self) -> list[str]:
        return self._data["services"]["secondary"]

    @property
    def excluded_services(self) -> list[str]:
        return self._data["services"]["exclude"]

    @property
    def all_offered_services(self) -> list[str]:
        return self.primary_services + self.secondary_services

    # --- Geographic ---

    @property
    def target_postcodes(self) -> list[str]:
        return self._data["geographic_area"]["districts"]

    @property
    def max_distance_km(self) -> int:
        return self._data["geographic_area"]["max_distance_km"]

    @property
    def borough_councils(self) -> list[str]:
        return self._data["geographic_area"]["borough_councils"]

    # --- Scoring ---

    @property
    def scoring_weights(self) -> dict[str, int]:
        return self._data["lead_scoring"]["weights"]

    @property
    def minimum_score(self) -> int:
        return self._data["lead_scoring"]["minimum_score"]

    @property
    def auto_send_threshold(self) -> int:
        return self._data["lead_scoring"]["auto_send_threshold"]

    # --- Letters ---

    @property
    def letter_auto_approve(self) -> bool:
        return self._data["letter_settings"]["auto_approve"]

    @property
    def case_studies(self) -> list[dict]:
        return self._data["letter_settings"].get("case_studies", [])

    @property
    def include_case_studies_count(self) -> int:
        return self._data["letter_settings"]["include_case_studies"]

    # --- Reporting ---

    @property
    def reporting(self) -> dict:
        return self._data["reporting"]

    # --- Integrations ---

    @property
    def gemini_config(self) -> dict:
        return self._data["integrations"]["gemini"]

    @property
    def stannp_config(self) -> dict:
        return self._data["integrations"]["stannp"]

    @property
    def smtp_config(self) -> dict:
        return self._data["integrations"]["smtp"]

    # --- Helper Methods ---

    def matches_service_area(self, postcode: str) -> bool:
        """Check if a postcode falls within the target service area."""
        district = self._extract_district(postcode)
        return district in self.target_postcodes

    def is_adjacent_area(self, postcode: str) -> bool:
        """Check if postcode is adjacent to (but not in) the target area."""
        district = self._extract_district(postcode)
        if district in self.target_postcodes:
            return False
        distance = self.calculate_distance(postcode)
        return distance <= self.max_distance_km

    def calculate_distance(self, postcode: str) -> float:
        """Calculate approximate distance in km from office to postcode district."""
        district = self._extract_district(postcode)
        if district not in _POSTCODE_CENTRES:
            return 99.0  # Unknown postcode, treat as far away

        office = _POSTCODE_CENTRES[_OFFICE_POSTCODE]
        target = _POSTCODE_CENTRES[district]

        # Haversine approximation for short distances
        import math

        lat1, lon1 = math.radians(office[0]), math.radians(office[1])
        lat2, lon2 = math.radians(target[0]), math.radians(target[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        return round(c * 6371, 1)  # Earth radius in km

    def get_case_studies_for_work_type(self, work_type: str) -> list[dict]:
        """Return case studies matching a work type keyword."""
        work_type_lower = work_type.lower()
        matches = []
        for cs in self.case_studies:
            cs_type = cs.get("work_type", "").lower()
            cs_id = cs.get("id", "").lower()
            if work_type_lower in cs_type or work_type_lower in cs_id:
                matches.append(cs)

        # If no direct match, return all (better than nothing)
        if not matches:
            return self.case_studies[: self.include_case_studies_count]

        return matches[: self.include_case_studies_count]

    def get_case_study_by_id(self, case_study_id: str) -> Optional[dict]:
        """Return a specific case study by its ID."""
        for cs in self.case_studies:
            if cs["id"] == case_study_id:
                return cs
        return None

    def matches_work_type(self, description: str) -> Optional[str]:
        """Check if a planning description matches our services. Returns the
        matched service type or None."""
        desc_lower = description.lower()

        # Keywords for each service type
        keywords = {
            "EXTENSION": [
                "extension", "extend", "single storey", "two storey",
                "rear extension", "side extension", "side return",
                "wrap-around", "wraparound",
            ],
            "CONVERSION_LOFT": [
                "loft conversion", "loft", "attic", "hip-to-gable",
                "hip to gable", "dormer", "mansard",
            ],
            "KITCHEN": [
                "kitchen extension", "kitchen",
            ],
            "CONVERSION_GARAGE": [
                "garage conversion", "convert garage",
            ],
        }

        for service_type, kws in keywords.items():
            if service_type in self.excluded_services:
                continue
            for kw in kws:
                if kw in desc_lower:
                    return service_type

        return None

    def get_company_background(self) -> str:
        """Generate company background text for letter prompts."""
        creds = ", ".join(self.credentials)
        return (
            f"{self.company_name} has been building in South West London since "
            f"{self.trading_since}. We are {creds}. "
            f"Contact: {self.phone}, {self.website}"
        )

    @staticmethod
    def _extract_district(postcode: str) -> str:
        """Extract district from full postcode (e.g. 'SW18 2PT' -> 'SW18')."""
        clean = postcode.strip().upper().replace(" ", "")
        # UK postcode: area + district + sector + unit
        # District is everything before the last 3 characters
        if len(clean) >= 5:
            return clean[:-3].strip()
        return clean


@lru_cache()
def get_settings() -> Settings:
    return Settings()


@lru_cache()
def get_client_config() -> ClientConfig:
    return ClientConfig()


# Convenience shortcuts
settings = get_settings()
client_config = get_client_config()
