"""UK Government EPC (Energy Performance Certificate) API integration.

Docs: https://epc.opendatacommunities.org/docs/api
Requires registered account — auth is Basic base64(email:apikey).
"""

import base64
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Optional

import httpx

from app.core.config import settings
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

EPC_BASE_URL = "https://epc.opendatacommunities.org/api/v1"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
MIN_ADDRESS_MATCH_CONFIDENCE = 0.7


class EPCAPIService:
    """Service for fetching and caching EPC data."""

    def __init__(self):
        headers = {"Accept": "application/json"}
        if settings.epc_api_key and settings.epc_api_email:
            # EPC API requires Basic auth: base64(email:apikey)
            credentials = f"{settings.epc_api_email}:{settings.epc_api_key}"
            b64_credentials = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {b64_credentials}"
            logger.info(f"EPC API auth configured for {settings.epc_api_email}")
        elif settings.epc_api_key:
            # Fallback: try just the key (won't work but log it)
            headers["Authorization"] = f"Basic {settings.epc_api_key}"
            logger.warning("EPC_API_EMAIL not set — auth will likely fail")

        self.client = httpx.AsyncClient(
            base_url=EPC_BASE_URL,
            timeout=10.0,
            headers=headers,
        )

    async def close(self):
        await self.client.aclose()

    async def get_epc_by_postcode(
        self, postcode: str, address_hint: Optional[str] = None
    ) -> Optional[dict]:
        """Fetch EPC data by postcode, optionally matching address.

        Returns the best matching EPC certificate or None.
        """
        normalized_postcode = self._normalize_postcode(postcode)
        cache_key = f"epc:{normalized_postcode}:{self._normalize_address(address_hint or '')}"

        # Check cache first
        cached = redis_client.get(cache_key)
        if cached:
            logger.debug(f"EPC cache hit: {cache_key}")
            return json.loads(cached)

        # Fetch from API
        try:
            certificates = await self._fetch_certificates(normalized_postcode)
        except Exception as e:
            logger.error(f"EPC API error for {postcode}: {e}")
            return None

        if not certificates:
            logger.info(f"No EPC found for {postcode}")
            return None

        # Match address if hint provided
        if address_hint:
            result = self._best_address_match(certificates, address_hint)
        else:
            # Return most recent certificate
            result = self._most_recent(certificates)

        if result:
            # Cache the result
            redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))

        return result

    async def _fetch_certificates(self, postcode: str) -> list[dict]:
        """Fetch all EPC certificates for a postcode."""
        try:
            resp = await self.client.get(
                "/domestic/search",
                params={"postcode": postcode, "size": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("rows", [])
            return [self._parse_certificate(row) for row in rows]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise

    def _parse_certificate(self, raw: dict) -> dict:
        """Parse raw EPC API response into clean structure."""
        return {
            "address": raw.get("address", ""),
            "postcode": raw.get("postcode", ""),
            "current_rating": raw.get("current-energy-rating", ""),
            "potential_rating": raw.get("potential-energy-rating", ""),
            "current_energy_efficiency": _safe_int(raw.get("current-energy-efficiency")),
            "potential_energy_efficiency": _safe_int(raw.get("potential-energy-efficiency")),
            "property_type": raw.get("property-type", ""),
            "construction_age_band": raw.get("construction-age-band", ""),
            "total_floor_area": _safe_float(raw.get("total-floor-area")),
            "walls_description": raw.get("walls-description", ""),
            "roof_description": raw.get("roof-description", ""),
            "windows_description": raw.get("windows-description", ""),
            "main_heating_description": raw.get("mainheat-description", ""),
            "floor_description": raw.get("floor-description", ""),
            "inspection_date": raw.get("inspection-date"),
            "lodgement_date": raw.get("lodgement-date"),
        }

    def _best_address_match(
        self, certificates: list[dict], address_hint: str
    ) -> Optional[dict]:
        """Find the best address match using fuzzy matching."""
        normalized_hint = self._normalize_address(address_hint)
        best_match = None
        best_score = 0.0

        for cert in certificates:
            cert_addr = self._normalize_address(cert.get("address", ""))
            score = SequenceMatcher(None, normalized_hint, cert_addr).ratio()

            if score > best_score:
                best_score = score
                best_match = cert

        if best_score >= MIN_ADDRESS_MATCH_CONFIDENCE:
            logger.info(f"EPC address match: {best_score:.2f} confidence")
            best_match["_match_confidence"] = round(best_score, 3)
            return best_match

        logger.info(
            f"No confident EPC match (best: {best_score:.2f} < {MIN_ADDRESS_MATCH_CONFIDENCE})"
        )
        # Fall back to most recent if no good match
        return self._most_recent(certificates)

    @staticmethod
    def _most_recent(certificates: list[dict]) -> Optional[dict]:
        """Return the most recently lodged certificate."""
        if not certificates:
            return None

        def sort_key(c):
            date_str = c.get("lodgement_date") or c.get("inspection_date") or ""
            return date_str

        sorted_certs = sorted(certificates, key=sort_key, reverse=True)
        return sorted_certs[0]

    @staticmethod
    def _normalize_postcode(postcode: str) -> str:
        """Normalize postcode: uppercase, remove spaces."""
        return postcode.strip().upper().replace(" ", "")

    @staticmethod
    def _normalize_address(address: str) -> str:
        """Normalize address for comparison."""
        addr = address.lower().strip()
        addr = re.sub(r"[,.\-']", " ", addr)
        addr = re.sub(r"\s+", " ", addr)
        # Remove common abbreviations
        replacements = {
            " street": " st",
            " road": " rd",
            " avenue": " ave",
            " drive": " dr",
            " lane": " ln",
            " close": " cl",
            " crescent": " cres",
            " london": "",
        }
        for old, new in replacements.items():
            addr = addr.replace(old, new)
        return addr.strip()


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
