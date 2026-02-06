"""Google Maps API service — geocoding, Street View, and static maps.

Provides precise geocoding for addresses (replacing postcode-centre lookup),
Street View imagery for property photos in PDFs, and static maps showing
property location relative to the builder's office.

All API calls use httpx async client with Redis caching (7-day TTL).
"""

import hashlib
import json
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis cache TTL (7 days)
CACHE_TTL = 60 * 60 * 24 * 7


class GoogleMapsService:
    """Google Maps Platform API client for geocoding and imagery."""

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    STREETVIEW_META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
    STREETVIEW_URL = "https://maps.googleapis.com/maps/api/streetview"
    STATICMAP_URL = "https://maps.googleapis.com/maps/api/staticmap"

    def __init__(self):
        self.api_key = settings.google_maps_api_key
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_API_KEY not set — Maps features disabled")
        self._client: Optional[httpx.AsyncClient] = None
        self._redis = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def _get_redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.redis_url, decode_responses=True
                )
            except Exception as e:
                logger.warning(f"Redis not available for Maps caching: {e}")
        return self._redis

    async def _cache_get(self, key: str) -> Optional[str]:
        r = await self._get_redis()
        if r:
            try:
                return await r.get(key)
            except Exception:
                pass
        return None

    async def _cache_set(self, key: str, value: str, ttl: int = CACHE_TTL):
        r = await self._get_redis()
        if r:
            try:
                await r.set(key, value, ex=ttl)
            except Exception:
                pass

    # ── Geocoding ──────────────────────────────────────────────────

    async def geocode_address(
        self, address: str, postcode: str = ""
    ) -> Optional[dict]:
        """Geocode a UK address to lat/lon coordinates.

        Args:
            address: Street address (e.g. "76 Upper Tulse Hill, London").
            postcode: UK postcode for disambiguation.

        Returns:
            Dict with keys: lat, lon, formatted_address, place_id.
            None if geocoding fails.
        """
        if not self.api_key:
            return None

        query = f"{address}, {postcode}".strip(", ")
        cache_key = f"gmaps:geocode:{hashlib.md5(query.encode()).hexdigest()}"

        # Check cache
        cached = await self._cache_get(cache_key)
        if cached:
            logger.debug(f"Geocode cache hit for {query[:50]}")
            return json.loads(cached)

        client = await self._get_client()
        try:
            resp = await client.get(self.GEOCODE_URL, params={
                "address": query,
                "components": "country:GB",
                "key": self.api_key,
            })
            resp.raise_for_status()
            data = resp.json()

            if data["status"] != "OK" or not data.get("results"):
                logger.warning(f"Geocode failed for '{query}': {data['status']}")
                return None

            result = data["results"][0]
            loc = result["geometry"]["location"]
            geo = {
                "lat": loc["lat"],
                "lon": loc["lng"],
                "formatted_address": result.get("formatted_address", ""),
                "place_id": result.get("place_id", ""),
            }

            await self._cache_set(cache_key, json.dumps(geo))
            logger.info(f"Geocoded: {query[:50]} → {geo['lat']:.6f}, {geo['lon']:.6f}")
            return geo

        except Exception as e:
            logger.error(f"Geocoding error for '{query}': {e}")
            return None

    # ── Street View ────────────────────────────────────────────────

    async def get_street_view_image(
        self,
        lat: float,
        lon: float,
        width: int = 400,
        height: int = 250,
        heading: int = 0,
        fov: int = 90,
    ) -> Optional[bytes]:
        """Fetch a Street View image of a property.

        First checks metadata to see if Street View is available at the
        location, then fetches the actual image.

        Args:
            lat: Latitude.
            lon: Longitude.
            width: Image width in pixels.
            height: Image height in pixels.
            heading: Camera heading (0=north, 90=east, etc.). 0 = auto.
            fov: Field of view (10-120 degrees).

        Returns:
            JPEG image bytes, or None if no Street View available.
        """
        if not self.api_key:
            return None

        location = f"{lat},{lon}"

        # Check metadata first (free API call, avoids wasting quota)
        client = await self._get_client()
        try:
            meta_resp = await client.get(self.STREETVIEW_META_URL, params={
                "location": location,
                "key": self.api_key,
            })
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            if meta.get("status") != "OK":
                logger.info(f"No Street View available at {location}")
                return None

        except Exception as e:
            logger.warning(f"Street View metadata check failed: {e}")
            return None

        # Fetch the actual image
        try:
            params = {
                "location": location,
                "size": f"{width}x{height}",
                "fov": fov,
                "key": self.api_key,
                "source": "outdoor",
            }
            if heading:
                params["heading"] = heading

            img_resp = await client.get(self.STREETVIEW_URL, params=params)
            img_resp.raise_for_status()

            if img_resp.headers.get("content-type", "").startswith("image/"):
                logger.info(f"Street View image: {len(img_resp.content):,} bytes")
                return img_resp.content

            return None

        except Exception as e:
            logger.error(f"Street View image fetch failed: {e}")
            return None

    # ── Static Map ─────────────────────────────────────────────────

    async def get_static_map_image(
        self,
        lat: float,
        lon: float,
        width: int = 400,
        height: int = 250,
        zoom: int = 14,
        office_lat: float = 51.4550,
        office_lon: float = -0.1910,
    ) -> Optional[bytes]:
        """Generate a static map with the property marker and office marker.

        Shows the property location (red marker) relative to the builder's
        office (blue marker), giving a sense of proximity.

        Args:
            lat: Property latitude.
            lon: Property longitude.
            width: Image width in pixels.
            height: Image height in pixels.
            zoom: Map zoom level (1-20).
            office_lat: Office latitude (default: SW18 centre).
            office_lon: Office longitude (default: SW18 centre).

        Returns:
            PNG image bytes, or None on failure.
        """
        if not self.api_key:
            return None

        client = await self._get_client()
        try:
            # Red marker for property, blue marker for office
            markers = [
                f"color:red|label:P|{lat},{lon}",
                f"color:blue|label:O|{office_lat},{office_lon}",
            ]

            resp = await client.get(self.STATICMAP_URL, params={
                "center": f"{lat},{lon}",
                "zoom": zoom,
                "size": f"{width}x{height}",
                "maptype": "roadmap",
                "markers": markers,
                "key": self.api_key,
            })
            resp.raise_for_status()

            if resp.headers.get("content-type", "").startswith("image/"):
                logger.info(f"Static map image: {len(resp.content):,} bytes")
                return resp.content

            return None

        except Exception as e:
            logger.error(f"Static map fetch failed: {e}")
            return None

    # ── Distance ───────────────────────────────────────────────────

    @staticmethod
    def haversine_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Calculate distance in km between two points using Haversine formula."""
        import math

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        return round(c * 6371, 2)  # Earth radius in km

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._redis:
            await self._redis.close()
