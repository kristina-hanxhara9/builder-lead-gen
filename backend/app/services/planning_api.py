"""London council planning application scraper.

Fetches recent applications from Wandsworth, Lambeth, and Richmond
via their Idox PublicAccess portals, with BeautifulSoup fallback.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import client_config

logger = logging.getLogger(__name__)

# Council portal base URLs (Idox PublicAccess)
COUNCIL_PORTALS = {
    "wandsworth": {
        "base_url": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer",
        "search_url": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/Generic/StdResults.aspx",
        "detail_base": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/Generic/StdDetails.aspx",
        "api_base": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/api",
    },
    "lambeth": {
        "base_url": "https://planning.lambeth.gov.uk/online-applications",
        "search_url": "https://planning.lambeth.gov.uk/online-applications/search.do",
        "detail_base": "https://planning.lambeth.gov.uk/online-applications/applicationDetails.do",
    },
    "richmond": {
        "base_url": "https://www2.richmond.gov.uk/PlanData2/Planning.aspx",
        "search_url": "https://www2.richmond.gov.uk/PlanData2/Planning.aspx",
        "detail_base": "https://www2.richmond.gov.uk/PlanData2/Planning.aspx",
    },
}

# Keywords that indicate work types we're interested in
INCLUDE_KEYWORDS = [
    "extension", "loft conversion", "loft", "dormer", "rear extension",
    "side extension", "side return", "single storey", "two storey",
    "hip-to-gable", "hip to gable", "mansard", "kitchen extension",
    "garage conversion", "wrap-around", "wraparound",
]

# Keywords that indicate work types we should exclude
EXCLUDE_KEYWORDS = [
    "change of use", "advertisement", "advert", "tree", "trees",
    "demolition only", "telecom", "antenna", "signage", "hoarding",
    "listed building consent only",
]


class LondonPlanningAPI:
    """Scraper for London borough planning applications."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "SmithAndSons-LeadGen/1.0 (Planning Research)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            },
        )
        self.target_postcodes = client_config.target_postcodes

    async def close(self):
        await self.client.aclose()

    async def fetch_recent_applications(
        self, days_back: int = 1
    ) -> list[dict]:
        """Fetch new planning applications from all councils."""
        all_applications = []

        for council in client_config.borough_councils:
            try:
                apps = await self._fetch_council_applications(council, days_back)
                all_applications.extend(apps)
                logger.info(f"Fetched {len(apps)} applications from {council}")
            except Exception as e:
                logger.error(f"Failed to fetch from {council}: {e}")
                continue

        # Filter for target postcodes and work types
        filtered = self._filter_applications(all_applications)
        logger.info(
            f"Total: {len(all_applications)} raw, {len(filtered)} after filtering"
        )
        return filtered

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    async def _fetch_council_applications(
        self, council: str, days_back: int
    ) -> list[dict]:
        """Fetch applications from a single council portal."""
        portal = COUNCIL_PORTALS.get(council)
        if not portal:
            logger.warning(f"No portal configured for {council}")
            return []

        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%d/%m/%Y")
        date_to = datetime.now().strftime("%d/%m/%Y")

        # Try Idox API first
        try:
            return await self._fetch_idox(portal, council, date_from, date_to)
        except Exception as e:
            logger.warning(f"Idox API failed for {council}, trying scrape: {e}")

        # Fallback to web scraping
        try:
            return await self._scrape_portal(portal, council, date_from, date_to)
        except Exception as e:
            logger.error(f"Scrape also failed for {council}: {e}")
            return []

    async def _fetch_idox(
        self, portal: dict, council: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Fetch from Idox PublicAccess search results."""
        params = {
            "searchType": "Application",
            "caseStatus": "all",
            "dateType": "DC_Validated",
            "dateStart": date_from,
            "dateEnd": date_to,
        }

        resp = await self.client.get(portal["search_url"], params=params)
        resp.raise_for_status()

        return self._parse_search_results(resp.text, council, portal)

    async def _scrape_portal(
        self, portal: dict, council: str, date_from: str, date_to: str
    ) -> list[dict]:
        """Fallback scraper using BeautifulSoup."""
        resp = await self.client.get(portal["search_url"], params={
            "dateStart": date_from,
            "dateEnd": date_to,
        })
        resp.raise_for_status()

        return self._parse_search_results(resp.text, council, portal)

    def _parse_search_results(
        self, html: str, council: str, portal: dict
    ) -> list[dict]:
        """Parse search results HTML into structured application data."""
        soup = BeautifulSoup(html, "lxml")
        applications = []

        # Idox PublicAccess typically uses table rows with class "searchresult"
        rows = soup.select("table#searchresults tr, li.searchresult, div.searchresult")

        for row in rows:
            try:
                app = self._parse_result_row(row, council, portal)
                if app:
                    applications.append(app)
            except Exception as e:
                logger.debug(f"Failed to parse row in {council}: {e}")
                continue

        return applications

    def _parse_result_row(
        self, row, council: str, portal: dict
    ) -> Optional[dict]:
        """Parse a single search result into application dict."""
        # Extract reference number
        ref_link = row.select_one("a[href*='applicationDetails'], a[href*='StdDetails']")
        if not ref_link:
            return None

        reference = ref_link.get_text(strip=True)
        if not reference:
            return None

        # Extract address
        address_elem = row.select_one(".address, td:nth-of-type(2)")
        address = address_elem.get_text(strip=True) if address_elem else ""

        # Extract description
        desc_elem = row.select_one(".description, td:nth-of-type(3)")
        description = desc_elem.get_text(strip=True) if desc_elem else ""

        # Extract postcode from address
        postcode = self._extract_postcode(address)

        # Build detail URL for later PDF extraction
        detail_url = ref_link.get("href", "")
        if not detail_url.startswith("http"):
            detail_url = portal["base_url"].rstrip("/") + "/" + detail_url.lstrip("/")

        return {
            "reference": reference,
            "address": address,
            "postcode": postcode or "",
            "description": description,
            "application_type": "Householder",  # Default, refined later
            "submitted_date": datetime.now().isoformat(),
            "decision": "Pending",
            "decision_date": None,
            "pdf_urls": [],  # Populated by get_pdf_urls()
            "local_authority": council.title(),
            "applicant_name": None,
            "status": "Submitted",
            "detail_url": detail_url,
        }

    async def get_pdf_urls(self, detail_url: str) -> list[str]:
        """Fetch PDF document URLs from an application detail page."""
        try:
            resp = await self.client.get(detail_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            pdf_links = []
            for link in soup.select("a[href$='.pdf'], a[href*='ViewDocument']"):
                href = link.get("href", "")
                if href and ("pdf" in href.lower() or "document" in href.lower()):
                    if not href.startswith("http"):
                        # Make absolute URL
                        from urllib.parse import urljoin
                        href = urljoin(detail_url, href)
                    pdf_links.append(href)

            return pdf_links
        except Exception as e:
            logger.error(f"Failed to get PDFs from {detail_url}: {e}")
            return []

    async def get_application_details(self, detail_url: str) -> dict:
        """Fetch full details for a single planning application."""
        try:
            resp = await self.client.get(detail_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            details = {}
            # Parse key-value pairs from detail tables
            for row in soup.select("tr, div.detail"):
                label = row.select_one("th, .label, dt")
                value = row.select_one("td, .value, dd")
                if label and value:
                    key = label.get_text(strip=True).lower().replace(" ", "_")
                    details[key] = value.get_text(strip=True)

            return details
        except Exception as e:
            logger.error(f"Failed to get details from {detail_url}: {e}")
            return {}

    def _filter_applications(self, applications: list[dict]) -> list[dict]:
        """Filter applications by postcode and work type."""
        filtered = []

        for app in applications:
            # Check postcode
            postcode = app.get("postcode", "")
            district = self._extract_district(postcode)
            if district and district not in self.target_postcodes:
                # Also check adjacent areas
                if not client_config.is_adjacent_area(postcode):
                    continue

            # Check description for relevant work types
            desc = (app.get("description") or "").lower()

            # Exclude unwanted types
            if any(kw in desc for kw in EXCLUDE_KEYWORDS):
                continue

            # Include only relevant work types
            if any(kw in desc for kw in INCLUDE_KEYWORDS):
                filtered.append(app)

        return filtered

    @staticmethod
    def _extract_postcode(address: str) -> Optional[str]:
        """Extract UK postcode from an address string."""
        pattern = r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}"
        match = re.search(pattern, address.upper())
        return match.group(0) if match else None

    @staticmethod
    def _extract_district(postcode: str) -> Optional[str]:
        """Extract district from postcode (e.g. 'SW18 2PT' -> 'SW18')."""
        if not postcode:
            return None
        clean = postcode.strip().upper().replace(" ", "")
        if len(clean) >= 5:
            return clean[:-3].strip()
        return clean
