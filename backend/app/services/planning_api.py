"""London council planning application scraper.

Fetches recent applications from Wandsworth, Lambeth, and Richmond
via their public portals. Handles:
- Idox PublicAccess (Lambeth) — requires session/cookie handling
- Northgate PlanningExplorer (Wandsworth) — ASP.NET with ViewState
- Citizen Portal / Angular SPAs (Richmond) — follows redirects
- Missing postcodes — derives them from addresses via postcodes.io

All council data is publicly available via their planning portals.
Postcodes aren't always present in the search results, so the pipeline
uses multiple strategies to extract or derive them.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import client_config
from app.services.postcode_service import PostcodeService

logger = logging.getLogger(__name__)

# Council portal URLs — updated Feb 2025
COUNCIL_PORTALS = {
    "wandsworth": {
        "type": "northgate",
        "base_url": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer",
        "search_url": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/Generic/StdResults.aspx",
        "detail_base": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/Generic/StdDetails.aspx",
        # Wandsworth also has a weekly list page
        "weekly_list_url": "https://planning.wandsworth.gov.uk/Northgate/PlanningExplorer/Generic/StdWeeklyList.aspx",
    },
    "lambeth": {
        "type": "idox",
        "base_url": "https://planning.lambeth.gov.uk/online-applications",
        "search_url": "https://planning.lambeth.gov.uk/online-applications/search.do",
        "results_url": "https://planning.lambeth.gov.uk/online-applications/advancedSearchResults.do",
        "weekly_url": "https://planning.lambeth.gov.uk/online-applications/search.do?action=weeklyList&searchType=Application",
        "detail_base": "https://planning.lambeth.gov.uk/online-applications/applicationDetails.do",
    },
    "richmond": {
        "type": "citizen_portal",
        "base_url": "https://planning.richmond.gov.uk/richmond",
        "search_url": "https://planning.richmond.gov.uk/richmond/search-applications/",
        "detail_base": "https://planning.richmond.gov.uk/richmond/application-details/",
        # Richmond's old URL redirects to this new Angular SPA
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
    """Scraper for London borough planning applications.

    Handles the reality that:
    - Each council uses a different portal system
    - Postcodes are often missing from search results
    - Sessions/cookies are needed for Idox portals
    - Some portals are temporarily down (Wandsworth 500s are common)
    """

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
        self.postcode_service = PostcodeService()
        self.target_postcodes = client_config.target_postcodes

    async def close(self):
        await self.client.aclose()
        await self.postcode_service.close()

    async def fetch_recent_applications(
        self, days_back: int = 1
    ) -> list[dict]:
        """Fetch new planning applications from all configured councils.

        Tries multiple strategies per council and derives postcodes
        for any applications that don't have them.
        """
        all_applications = []

        for council in client_config.borough_councils:
            try:
                apps = await self._fetch_council_applications(council, days_back)
                all_applications.extend(apps)
                logger.info(f"Fetched {len(apps)} applications from {council}")
            except Exception as e:
                logger.error(f"Failed to fetch from {council}: {e}")
                continue

        # Derive postcodes for applications that don't have them
        if all_applications:
            all_applications = await self.postcode_service.bulk_derive(all_applications)
            logger.info(
                f"Postcode derivation complete for {len(all_applications)} applications"
            )

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
        """Fetch applications from a single council portal.

        Tries portal-specific strategies in order of reliability.
        """
        portal = COUNCIL_PORTALS.get(council)
        if not portal:
            logger.warning(f"No portal configured for {council}")
            return []

        portal_type = portal.get("type", "unknown")

        if portal_type == "idox":
            return await self._fetch_idox_with_session(portal, council, days_back)
        elif portal_type == "northgate":
            return await self._fetch_northgate(portal, council, days_back)
        elif portal_type == "citizen_portal":
            return await self._fetch_citizen_portal(portal, council, days_back)
        else:
            logger.warning(f"Unknown portal type '{portal_type}' for {council}")
            return []

    # ── Idox (Lambeth) ────────────────────────────────────────

    async def _fetch_idox_with_session(
        self, portal: dict, council: str, days_back: int
    ) -> list[dict]:
        """Fetch from Idox PublicAccess with proper session handling.

        Idox portals require:
        1. Load the search form to get a session cookie
        2. POST the search form with date parameters
        3. Parse the results page
        """
        # Strategy 1: Try the weekly list (most reliable, no search needed)
        weekly_url = portal.get("weekly_url")
        if weekly_url:
            try:
                apps = await self._fetch_idox_weekly_list(portal, council)
                if apps:
                    return apps
            except Exception as e:
                logger.warning(f"Idox weekly list failed for {council}: {e}")

        # Strategy 2: Search with proper session
        try:
            return await self._fetch_idox_search(portal, council, days_back)
        except Exception as e:
            logger.warning(f"Idox search failed for {council}: {e}")

        return []

    async def _fetch_idox_weekly_list(
        self, portal: dict, council: str
    ) -> list[dict]:
        """Fetch the weekly planning list by submitting the form.

        The weekly list page has a form with ward and week selectors.
        We submit it to get the actual application list.
        """
        weekly_url = portal["weekly_url"]

        # Step 1: Load the weekly list page to get session cookies + form options
        resp = await self.client.get(weekly_url)
        resp.raise_for_status()

        # Step 2: Submit the form to get results (all wards, current week)
        results_url = portal["base_url"] + "/weeklyListResults.do"
        form_data = {
            "action": "firstPage",
            "searchCriteria.ward": "",  # Empty = all wards
            "week": "0",  # 0 = current week
            "searchType": "Application",
        }
        results_resp = await self.client.post(
            results_url,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": weekly_url,
            },
        )
        results_resp.raise_for_status()

        # Step 3: Parse results
        return self._parse_idox_results(results_resp.text, council, portal)

    async def _fetch_idox_search(
        self, portal: dict, council: str, days_back: int
    ) -> list[dict]:
        """Search Idox with session cookies and proper form submission."""
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%d/%m/%Y")
        date_to = datetime.now().strftime("%d/%m/%Y")

        # Step 1: Load the search page to get session cookies
        search_url = portal["search_url"]
        search_resp = await self.client.get(
            search_url,
            params={"action": "advanced", "searchType": "Application"},
        )
        search_resp.raise_for_status()

        # Step 2: POST the search form
        results_url = portal.get("results_url", search_url)
        search_data = {
            "searchType": "Application",
            "action": "firstPage",
            "caseStatus": "all",
            "dateType": "DC_Validated",
            "dateStart": date_from,
            "dateEnd": date_to,
        }

        results_resp = await self.client.post(
            results_url,
            data=search_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": search_url,
            },
        )
        results_resp.raise_for_status()

        return self._parse_idox_results(results_resp.text, council, portal)

    def _parse_idox_results(
        self, html: str, council: str, portal: dict
    ) -> list[dict]:
        """Parse Idox PublicAccess search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        applications = []

        # Idox result rows can be in multiple formats
        rows = soup.select(
            "li.searchresult, "
            "div.searchresult, "
            "table#searchresults tr, "
            "ul#searchresults li"
        )

        if not rows:
            # Try another common Idox pattern
            rows = soup.select("div#searchResultsContainer li, div.result")

        for row in rows:
            try:
                app = self._parse_idox_row(row, council, portal)
                if app:
                    applications.append(app)
            except Exception as e:
                logger.debug(f"Failed to parse Idox row in {council}: {e}")
                continue

        logger.info(f"Parsed {len(applications)} Idox results from {council}")
        return applications

    def _parse_idox_row(
        self, row, council: str, portal: dict
    ) -> Optional[dict]:
        """Parse a single Idox search result."""
        # Reference — usually the first link
        ref_link = row.select_one(
            "a[href*='applicationDetails'], "
            "a[href*='caseNo'], "
            "a.caseNumber"
        )
        if not ref_link:
            # Try any link in the row
            ref_link = row.select_one("a")
        if not ref_link:
            return None

        reference = ref_link.get_text(strip=True)
        if not reference or len(reference) < 5:
            return None

        # Address — multiple possible class names
        address = ""
        for selector in [".address", ".addressWrapper", "p.address", "td:nth-of-type(2)"]:
            addr_elem = row.select_one(selector)
            if addr_elem:
                address = addr_elem.get_text(strip=True)
                break
        if not address:
            # Fallback: get all text and split by reference
            full_text = row.get_text(" ", strip=True)
            parts = full_text.split(reference, 1)
            if len(parts) > 1:
                address = parts[1].strip()[:300]

        # Description
        description = ""
        for selector in [".description", ".descriptionWrapper", "p.description", "td:nth-of-type(3)"]:
            desc_elem = row.select_one(selector)
            if desc_elem:
                description = desc_elem.get_text(strip=True)
                break

        # Extract postcode from address
        postcode = self._extract_postcode(address)

        # Build detail URL
        detail_url = ref_link.get("href", "")
        if detail_url and not detail_url.startswith("http"):
            detail_url = urljoin(portal["base_url"] + "/", detail_url)

        # Extract submitted date if available
        date_elem = row.select_one(".date, .dateReceived")
        submitted_date = None
        if date_elem:
            submitted_date = self._parse_date(date_elem.get_text(strip=True))

        return {
            "reference": reference,
            "address": address,
            "postcode": postcode or "",
            "description": description,
            "application_type": "Householder",
            "submitted_date": (submitted_date or datetime.now()).isoformat(),
            "decision": "Pending",
            "decision_date": None,
            "pdf_urls": [],
            "local_authority": council.title(),
            "applicant_name": None,
            "status": "Submitted",
            "detail_url": detail_url,
        }

    # ── Northgate / PlanningExplorer (Wandsworth) ──────────────

    async def _fetch_northgate(
        self, portal: dict, council: str, days_back: int
    ) -> list[dict]:
        """Fetch from Northgate PlanningExplorer.

        These ASP.NET portals are often unreliable (500 errors).
        Try the weekly list first, then fall back to search.
        """
        # Strategy 1: Weekly list
        weekly_url = portal.get("weekly_list_url")
        if weekly_url:
            try:
                resp = await self.client.get(weekly_url)
                if resp.status_code == 200:
                    apps = self._parse_northgate_results(resp.text, council, portal)
                    if apps:
                        return apps
            except Exception as e:
                logger.warning(f"Northgate weekly list failed: {e}")

        # Strategy 2: Standard search
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%d/%m/%Y")
        date_to = datetime.now().strftime("%d/%m/%Y")

        try:
            resp = await self.client.get(
                portal["search_url"],
                params={
                    "searchType": "Application",
                    "caseStatus": "all",
                    "dateType": "DC_Validated",
                    "dateStart": date_from,
                    "dateEnd": date_to,
                },
            )
            if resp.status_code == 200:
                return self._parse_northgate_results(resp.text, council, portal)
            else:
                logger.warning(
                    f"Northgate returned {resp.status_code} for {council} "
                    f"(this is common — portal may be down)"
                )
        except Exception as e:
            logger.warning(f"Northgate search failed: {e}")

        return []

    def _parse_northgate_results(
        self, html: str, council: str, portal: dict
    ) -> list[dict]:
        """Parse Northgate PlanningExplorer HTML results."""
        soup = BeautifulSoup(html, "lxml")
        applications = []

        # Northgate uses table-based layout
        rows = soup.select(
            "table#searchresults tr, "
            "table.display_results tr, "
            "div.resultsContainer tr"
        )

        for row in rows:
            ref_link = row.select_one("a[href*='StdDetails'], a[href*='caseno']")
            if not ref_link:
                continue

            reference = ref_link.get_text(strip=True)
            if not reference:
                continue

            # Address and description in table cells
            cells = row.select("td")
            address = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            description = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            postcode = self._extract_postcode(address)

            detail_url = ref_link.get("href", "")
            if detail_url and not detail_url.startswith("http"):
                detail_url = urljoin(portal["base_url"] + "/", detail_url)

            applications.append({
                "reference": reference,
                "address": address,
                "postcode": postcode or "",
                "description": description,
                "application_type": "Householder",
                "submitted_date": datetime.now().isoformat(),
                "decision": "Pending",
                "decision_date": None,
                "pdf_urls": [],
                "local_authority": council.title(),
                "applicant_name": None,
                "status": "Submitted",
                "detail_url": detail_url,
            })

        logger.info(f"Parsed {len(applications)} Northgate results from {council}")
        return applications

    # ── Citizen Portal / Angular SPA (Richmond) ────────────────

    async def _fetch_citizen_portal(
        self, portal: dict, council: str, days_back: int
    ) -> list[dict]:
        """Fetch from modern Angular-based Citizen Portal.

        These SPAs load data via internal APIs. We try to discover
        the API endpoint from the page source.
        """
        try:
            resp = await self.client.get(portal["search_url"])
            resp.raise_for_status()

            # Look for API base URL in the Angular app's config
            api_url = self._discover_spa_api(resp.text, portal)
            if api_url:
                return await self._fetch_spa_api(api_url, council, days_back)

            logger.warning(
                f"Citizen Portal for {council} is an Angular SPA — "
                f"cannot scrape without headless browser. "
                f"Consider using Playwright for this portal."
            )
        except Exception as e:
            logger.warning(f"Citizen Portal failed for {council}: {e}")

        return []

    def _discover_spa_api(self, html: str, portal: dict) -> Optional[str]:
        """Try to find the API URL from an Angular SPA's source."""
        # Common patterns in Angular apps
        patterns = [
            r'"apiUrl"\s*:\s*"([^"]+)"',
            r'"baseUrl"\s*:\s*"([^"]+)"',
            r'"API_URL"\s*:\s*"([^"]+)"',
            r'/api/applications',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                url = match.group(1) if match.lastindex else match.group(0)
                if not url.startswith("http"):
                    url = urljoin(portal["base_url"], url)
                return url
        return None

    async def _fetch_spa_api(
        self, api_url: str, council: str, days_back: int
    ) -> list[dict]:
        """Fetch from the discovered SPA API."""
        try:
            date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            resp = await self.client.get(
                api_url,
                params={"from": date_from, "type": "householder"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            applications = []
            items = data if isinstance(data, list) else data.get("results", data.get("applications", []))

            for item in items:
                postcode = self._extract_postcode(item.get("address", ""))
                applications.append({
                    "reference": item.get("reference", item.get("caseReference", "")),
                    "address": item.get("address", ""),
                    "postcode": postcode or "",
                    "description": item.get("description", item.get("proposal", "")),
                    "application_type": item.get("type", "Householder"),
                    "submitted_date": item.get("receivedDate", datetime.now().isoformat()),
                    "decision": item.get("decision", "Pending"),
                    "decision_date": item.get("decisionDate"),
                    "pdf_urls": [],
                    "local_authority": council.title(),
                    "applicant_name": item.get("applicantName"),
                    "status": item.get("status", "Submitted"),
                    "detail_url": item.get("url", ""),
                })

            return applications
        except Exception as e:
            logger.error(f"SPA API failed for {council}: {e}")
            return []

    # ── Detail page parsing ────────────────────────────────────

    async def get_pdf_urls(self, detail_url: str) -> list[str]:
        """Fetch PDF document URLs from an application detail page."""
        try:
            resp = await self.client.get(detail_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            pdf_links = []
            for link in soup.select("a[href$='.pdf'], a[href*='ViewDocument'], a[href*='document']"):
                href = link.get("href", "")
                if href and ("pdf" in href.lower() or "document" in href.lower()):
                    if not href.startswith("http"):
                        href = urljoin(detail_url, href)
                    pdf_links.append(href)

            return pdf_links
        except Exception as e:
            logger.error(f"Failed to get PDFs from {detail_url}: {e}")
            return []

    async def get_application_details(self, detail_url: str) -> dict:
        """Fetch full details for a single planning application.

        Also extracts postcode from the detail page if not in search results.
        """
        try:
            resp = await self.client.get(detail_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            details = {}
            # Parse key-value pairs from detail tables
            for row in soup.select("tr, div.detail, dl dt, dl dd"):
                label = row.select_one("th, .label, dt")
                value = row.select_one("td, .value, dd")
                if label and value:
                    key = label.get_text(strip=True).lower().replace(" ", "_")
                    details[key] = value.get_text(strip=True)

            # Also try to extract postcode from the full page text
            full_text = soup.get_text()
            postcode = self._extract_postcode(full_text)
            if postcode:
                details["_derived_postcode"] = postcode

            return details
        except Exception as e:
            logger.error(f"Failed to get details from {detail_url}: {e}")
            return {}

    # ── Filtering ──────────────────────────────────────────────

    def _filter_applications(self, applications: list[dict]) -> list[dict]:
        """Filter applications by postcode/district and work type.

        Key change: DON'T drop applications with missing postcodes —
        include them if they match by work type (the agents will
        derive postcodes later in the pipeline).
        """
        filtered = []

        for app in applications:
            postcode = app.get("postcode", "")
            district = self._extract_district(postcode)

            # Also check derived district from postcode service
            derived_district = app.get("_derived_district", "")

            effective_district = district or derived_district

            if effective_district:
                if effective_district not in self.target_postcodes:
                    # Check adjacent areas
                    if postcode and not client_config.is_adjacent_area(postcode):
                        continue
                    elif not postcode:
                        # No full postcode but district doesn't match — skip
                        continue

            # Check description for relevant work types
            desc = (app.get("description") or "").lower()

            # Exclude unwanted types
            if any(kw in desc for kw in EXCLUDE_KEYWORDS):
                continue

            # Include relevant work types
            # If no postcode AND no district, still include if work type matches
            # (the agents will figure out the postcode later)
            if any(kw in desc for kw in INCLUDE_KEYWORDS):
                if not effective_district:
                    # No postcode at all — include but flag it
                    app["_needs_postcode"] = True
                    logger.info(
                        f"Including {app.get('reference')} without postcode "
                        f"(work type matches, agents will derive)"
                    )
                filtered.append(app)

        return filtered

    # ── Utilities ──────────────────────────────────────────────

    @staticmethod
    def _extract_postcode(text: str) -> Optional[str]:
        """Extract UK postcode from any text string."""
        if not text:
            return None
        pattern = r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}"
        match = re.search(pattern, text.upper())
        if match:
            raw = match.group(0).replace(" ", "")
            # Format nicely: "SW115RN" → "SW11 5RN"
            if len(raw) >= 5:
                return raw[:-3] + " " + raw[-3:]
            return raw
        return None

    @staticmethod
    def _extract_district(postcode: str) -> Optional[str]:
        """Extract district from postcode (e.g. 'SW18 2PT' -> 'SW18')."""
        if not postcode:
            return None
        clean = postcode.strip().upper().replace(" ", "")
        if len(clean) >= 5:
            return clean[:-3].strip()
        return clean

    @staticmethod
    def _parse_date(date_text: str) -> Optional[datetime]:
        """Parse a date string in common UK formats."""
        for fmt in ["%d/%m/%Y", "%d %b %Y", "%d-%m-%Y", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_text.strip(), fmt)
            except ValueError:
                continue
        return None
