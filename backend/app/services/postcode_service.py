"""Postcode derivation and validation service using postcodes.io (free, no auth).

Used throughout the pipeline when planning applications don't have a clean
postcode — which is common. Council portals often list addresses like:
  "42 Lavender Hill London" (no postcode)
  "Flat 3, 18 High Street, Wandsworth" (no postcode)

This service derives postcodes via:
1. Regex extraction from address text
2. Geocoding via postcodes.io reverse lookup
3. Borough-to-outcode mapping (coarse fallback)
"""

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

POSTCODES_IO_BASE = "https://api.postcodes.io"

# Borough name → likely outcode districts (for coarse fallback)
BOROUGH_OUTCODE_MAP = {
    "wandsworth": ["SW11", "SW12", "SW15", "SW17", "SW18"],
    "lambeth": ["SE1", "SE5", "SE11", "SE24", "SE27", "SW2", "SW4", "SW8", "SW9", "SW16"],
    "richmond": ["TW1", "TW2", "TW9", "TW10", "SW13", "SW14"],
    "merton": ["SW19", "SW20"],
    "southwark": ["SE1", "SE5", "SE15", "SE16", "SE17", "SE21", "SE22"],
    "croydon": ["CR0", "CR2", "CR5", "CR7", "CR8"],
    "kingston": ["KT1", "KT2", "KT3", "KT5", "KT6"],
    "camden": ["NW1", "NW3", "NW5", "WC1", "WC2"],
}

# Coordinates for borough centres (for reverse geocoding)
BOROUGH_CENTRES = {
    "wandsworth": (51.455, -0.191),
    "lambeth": (51.457, -0.117),
    "richmond": (51.461, -0.303),
}

# UK postcode regex — matches full postcodes like SW11 5RN, EC1A 1BB
_FULL_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)

# Partial postcode (outcode only) — matches SW11, EC1A, etc.
_OUTCODE_RE = re.compile(
    r"\b((?:SW|SE|NW|NE|W|E|N|S|EC|WC|TW|KT|CR|SM|BR|DA|EN|HA|IG|RM|UB)\d{1,2}[A-Z]?)\b",
    re.IGNORECASE,
)


class PostcodeService:
    """Derive and validate UK postcodes from addresses."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=POSTCODES_IO_BASE,
            timeout=8.0,
        )

    async def close(self):
        await self.client.aclose()

    async def derive_postcode(
        self,
        address: str,
        borough: str = "",
    ) -> dict:
        """Try every method to get a postcode from an address.

        Returns:
            {
                "postcode": "SW11 5RN" or "",
                "district": "SW11" or "",
                "method": "regex" | "geocode" | "borough_fallback" | "none",
                "confidence": 0.0-1.0,
            }
        """
        # 1. Try regex extraction from address text
        full_match = _FULL_POSTCODE_RE.search(address)
        if full_match:
            pc = self._format_postcode(full_match.group(1))
            valid = await self._validate_postcode(pc)
            if valid:
                return {
                    "postcode": pc,
                    "district": self._extract_district(pc),
                    "method": "regex",
                    "confidence": 1.0,
                }

        # 2. Try partial postcode extraction (just the outcode)
        outcode_match = _OUTCODE_RE.search(address)
        outcode = outcode_match.group(1).upper() if outcode_match else ""

        # 3. Try geocoding the full address via postcodes.io
        geocoded = await self._geocode_address(address)
        if geocoded:
            return {
                "postcode": geocoded["postcode"],
                "district": self._extract_district(geocoded["postcode"]),
                "method": "geocode",
                "confidence": 0.75,
            }

        # 4. If we got an outcode from the address, use it
        if outcode:
            return {
                "postcode": "",  # Don't have full postcode
                "district": outcode,
                "method": "outcode_regex",
                "confidence": 0.6,
            }

        # 5. Borough-based fallback (very coarse — just gives the area)
        borough_lower = borough.lower().strip()
        if borough_lower in BOROUGH_OUTCODE_MAP:
            districts = BOROUGH_OUTCODE_MAP[borough_lower]
            return {
                "postcode": "",
                "district": districts[0],  # Primary district
                "method": "borough_fallback",
                "confidence": 0.3,
            }

        return {
            "postcode": "",
            "district": "",
            "method": "none",
            "confidence": 0.0,
        }

    async def _geocode_address(self, address: str) -> Optional[dict]:
        """Geocode a UK address to get its postcode.

        Strategy:
        1. Try Google Maps geocoding (most accurate, uses API key if available)
        2. Try extracting a street address from description text and geocoding it
        3. Fall back to postcodes.io reverse geocode from borough centre
        """
        from app.core.config import settings

        # Strategy 1: Google Maps geocoding (if API key available)
        if settings.google_maps_api_key:
            result = await self._google_geocode(address, settings.google_maps_api_key)
            if result:
                return result

        # Strategy 2: Extract street-like address from text and try Google
        street_address = self._extract_address_from_text(address)
        if street_address and street_address != address and settings.google_maps_api_key:
            result = await self._google_geocode(
                street_address + ", London", settings.google_maps_api_key
            )
            if result:
                return result

        # Strategy 3: postcodes.io reverse geocode from borough centre
        address_lower = address.lower()
        for borough, (lat, lon) in BOROUGH_CENTRES.items():
            if borough in address_lower or "london" in address_lower:
                result = await self._reverse_geocode(lat, lon)
                if result:
                    return result
                break

        return None

    async def _google_geocode(self, address: str, api_key: str) -> Optional[dict]:
        """Geocode via Google Maps API, then reverse lookup for postcode."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={
                        "address": address,
                        "components": "country:GB",
                        "key": api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") == "OK" and data.get("results"):
                    result = data["results"][0]

                    # Extract postcode from address components
                    for comp in result.get("address_components", []):
                        if "postal_code" in comp.get("types", []):
                            pc = comp["long_name"]
                            return {
                                "postcode": pc,
                                "district": self._extract_district(pc),
                                "admin_district": "",
                            }

                    # If no postcode in components, use lat/lon to reverse geocode
                    location = result.get("geometry", {}).get("location", {})
                    if location:
                        return await self._reverse_geocode(
                            location["lat"], location["lng"]
                        )
        except Exception as e:
            logger.debug(f"Google geocode failed: {e}")
        return None

    @staticmethod
    def _extract_address_from_text(text: str) -> Optional[str]:
        """Try to extract a street address from free-form planning text.

        Planning descriptions often contain addresses like:
        - "Erection of extension at 42 Lavender Hill London"
        - "Works to rear of 18 High Street Wandsworth"
        """
        # Look for patterns like "NN Street Name" or "NN-NN Road Name"
        address_pattern = re.compile(
            r"(?:at|to|of|,)\s+"
            r"(\d+(?:-\d+)?[A-Za-z]?\s+"
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*"
            r"(?:\s+(?:Road|Street|Lane|Hill|Avenue|Drive|Close|Way|"
            r"Crescent|Place|Gardens|Terrace|Grove|Walk|Rise|"
            r"Park|Court|Square|Mews|Row))"
            r"(?:[,\s]+[A-Za-z\s]+)?)",
            re.IGNORECASE,
        )
        match = address_pattern.search(text)
        if match:
            return match.group(1).strip().rstrip(",. ")
        return None

    async def _reverse_geocode(self, lat: float, lon: float) -> Optional[dict]:
        """Reverse geocode lat/lon to nearest postcode."""
        try:
            resp = await self.client.get(
                "/postcodes",
                params={"lon": lon, "lat": lat, "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", [])
            if results:
                return {
                    "postcode": results[0]["postcode"],
                    "district": self._extract_district(results[0]["postcode"]),
                    "admin_district": results[0].get("admin_district", ""),
                }
        except Exception as e:
            logger.debug(f"Reverse geocode failed: {e}")
        return None

    async def _validate_postcode(self, postcode: str) -> bool:
        """Check if a postcode is valid via postcodes.io."""
        try:
            clean = postcode.replace(" ", "")
            resp = await self.client.get(f"/postcodes/{clean}/validate")
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", False)
        except Exception:
            # If API fails, assume valid if it looks right
            return bool(_FULL_POSTCODE_RE.match(postcode))

    async def lookup_postcode(self, postcode: str) -> Optional[dict]:
        """Get full details for a postcode."""
        try:
            clean = postcode.replace(" ", "")
            resp = await self.client.get(f"/postcodes/{clean}")
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result")
            if result:
                return {
                    "postcode": result["postcode"],
                    "district": self._extract_district(result["postcode"]),
                    "admin_district": result.get("admin_district", ""),
                    "latitude": result.get("latitude"),
                    "longitude": result.get("longitude"),
                }
        except Exception as e:
            logger.debug(f"Postcode lookup failed: {e}")
        return None

    async def bulk_derive(
        self,
        applications: list[dict],
        borough: str = "",
    ) -> list[dict]:
        """Derive postcodes for a batch of planning applications.

        Modifies applications in-place, adding postcode and district
        where missing.
        """
        derived_count = 0
        for app in applications:
            postcode = app.get("postcode", "")
            if postcode and _FULL_POSTCODE_RE.match(postcode):
                continue  # Already has a valid postcode

            address = app.get("address", "")
            local_authority = app.get("local_authority", borough)

            result = await self.derive_postcode(address, local_authority)
            if result["postcode"]:
                app["postcode"] = result["postcode"]
                app["_postcode_method"] = result["method"]
                app["_postcode_confidence"] = result["confidence"]
                derived_count += 1
            elif result["district"]:
                # At least we have a district for area-based filtering
                app["_derived_district"] = result["district"]
                app["_postcode_method"] = result["method"]
                app["_postcode_confidence"] = result["confidence"]
                derived_count += 1

        logger.info(f"Postcode derivation: {derived_count}/{len(applications)} enhanced")
        return applications

    @staticmethod
    def _format_postcode(raw: str) -> str:
        """Format a postcode into standard form (e.g. 'sw115rn' → 'SW11 5RN')."""
        clean = raw.upper().replace(" ", "")
        if len(clean) >= 5:
            return clean[:-3] + " " + clean[-3:]
        return clean

    @staticmethod
    def _extract_district(postcode: str) -> str:
        """Extract outcode district from postcode (e.g. 'SW11 5RN' → 'SW11')."""
        clean = postcode.strip().upper().replace(" ", "")
        if len(clean) >= 5:
            return clean[:-3].strip()
        return clean
