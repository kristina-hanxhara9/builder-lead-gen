"""LangChain tools for discovering, downloading, and extracting planning PDFs.

Uses the Google Gemini Files API for native PDF reading — Google processes
the entire document with full document understanding (layout, tables, images).

These tools are used by Agent 1 (PDF Extractor) to:
1. Discover documents on the planning portal (scrape the detail page)
2. Analyse filenames to prioritise downloads
3. Download and extract data from the best PDFs
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from app.services.gemini_service import GeminiService, download_pdf

logger = logging.getLogger(__name__)

# Module-level service instance (reused for cost tracking within a run)
_gemini: Optional[GeminiService] = None


def _get_gemini() -> GeminiService:
    global _gemini
    if _gemini is None:
        _gemini = GeminiService()
    return _gemini


def reset_gemini():
    """Reset the module-level Gemini service (call at pipeline start)."""
    global _gemini
    _gemini = None


def _classify_document(filename: str) -> str:
    """Classify a planning document by its filename into a type category."""
    name = filename.lower()
    if "design" in name and "access" in name:
        return "design_and_access_statement"
    if "application" in name and "form" in name:
        return "application_form"
    if ("application" in name and "without" in name and "personal" in name):
        return "application_form"
    if "floor" in name and "plan" in name:
        return "floor_plan"
    if "elevation" in name:
        return "elevation_drawing"
    if "site" in name and "plan" in name:
        return "site_plan"
    if "structural" in name:
        return "structural_report"
    if "heritage" in name or "conservation" in name:
        return "heritage_statement"
    if "planning" in name and "statement" in name:
        return "planning_statement"
    if "officer" in name and "report" in name:
        return "officer_report"
    if "decision" in name and "notice" in name:
        return "decision_notice"
    if "notice" in name:
        return "site_notice"
    if "certificate" in name or "ownership" in name:
        return "certificate"
    if "cil" in name or "infrastructure" in name:
        return "cil_form"
    if "plan" in name or "drawing" in name:
        return "drawing"
    if "statement" in name:
        return "statement"
    if "pre-existing" in name or "existing" in name:
        return "existing_plans"
    if "proposed" in name:
        return "proposed_plans"
    if "location" in name:
        return "location_plan"
    return "other"


@tool
async def discover_planning_documents(detail_url: str) -> str:
    """Discover all available PDF documents from a planning application's
    detail page on a council planning portal.

    Takes the application detail URL, fetches the page, navigates to the
    documents tab/section, and extracts all available document URLs with
    their filenames and document types.

    This tool should be called FIRST before attempting to download PDFs,
    especially when no pdf_urls are pre-loaded. It scrapes the council
    planning portal to find real document links.

    Supports both Idox PublicAccess portals (Lambeth, Richmond) and
    Northgate PlanningExplorer portals (Wandsworth).

    Args:
        detail_url: Full URL to the planning application detail page
                    (e.g. from Wandsworth, Lambeth, or Richmond portal).

    Returns:
        JSON with keys: found (bool), documents (list of {url, filename,
        document_type}), total_count (int), message (str).
    """
    if not detail_url:
        return json.dumps({
            "found": False,
            "documents": [],
            "total_count": 0,
            "message": "No detail URL provided.",
        })

    documents = []

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            # Step 1: Build the documents tab URL
            # Idox pattern: replace activeTab=... with activeTab=documents
            if "activeTab=" in detail_url:
                docs_url = re.sub(r"activeTab=\w+", "activeTab=documents", detail_url)
            elif "?" in detail_url:
                docs_url = detail_url + "&activeTab=documents"
            else:
                docs_url = detail_url + "?activeTab=documents"

            # Step 2: Fetch the documents page directly
            logger.info(f"Discovering documents from: {docs_url}")
            resp = await client.get(docs_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # If we got a page without documents, try finding a documents link
            seen_urls = set()

            # Step 3: Extract PDF links — multiple selector patterns for different portals
            all_pdf_selectors = (
                "a[href*='/files/'][href$='.pdf'], "
                "a[href$='.pdf'], "
                "a[href*='ViewDocument'], "
                "a[href*='viewDocument'], "
                "a[href*='ShowDocument'], "
                "a[href*='showDocument'], "
                "a[href*='document.ashx'], "
                "a[href*='getDocument']"
            )

            for link in soup.select(all_pdf_selectors):
                href = link.get("href", "").strip()
                if not href:
                    continue
                abs_url = urljoin(docs_url, href)
                if abs_url in seen_urls:
                    continue
                seen_urls.add(abs_url)

                # Extract best filename: prefer URL filename over link text
                # because Idox often shows "View Document" as link text
                url_filename = href.split("/")[-1].split("?")[0]
                link_text = link.get_text(strip=True)
                link_title = link.get("title", "")

                # Use URL filename if it's informative (contains .pdf or recognisable text)
                if url_filename and len(url_filename) > 5 and url_filename != "pdf":
                    filename = url_filename.replace("%20", " ").replace("_", " ").replace("-", " ")
                elif link_title and link_title.lower() != "view document":
                    filename = link_title
                elif link_text and link_text.lower() != "view document" and len(link_text) > 3:
                    filename = link_text
                else:
                    filename = url_filename or "unknown"

                # Also classify based on the full URL path (more info in URL than link text)
                classify_input = href.replace("%20", " ").replace("_", " ").replace("-", " ").lower()
                doc_type = _classify_document(classify_input)

                documents.append({
                    "url": abs_url,
                    "filename": filename[:200],
                    "document_type": doc_type,
                })

            # If no documents found on the docs tab, try the original detail page
            if not documents and docs_url != detail_url:
                logger.info(f"No docs on documents tab, trying detail page: {detail_url}")
                resp2 = await client.get(detail_url)
                resp2.raise_for_status()
                soup2 = BeautifulSoup(resp2.text, "lxml")

                # Look for a documents tab link we may have missed
                for nav_link in soup2.select("a[href]"):
                    link_text = nav_link.get_text(strip=True).lower()
                    href = nav_link.get("href", "")
                    if "document" in link_text and href:
                        alt_docs_url = urljoin(detail_url, href)
                        if alt_docs_url != docs_url and alt_docs_url != detail_url:
                            logger.info(f"Found alternate documents link: {alt_docs_url}")
                            resp3 = await client.get(alt_docs_url)
                            resp3.raise_for_status()
                            soup3 = BeautifulSoup(resp3.text, "lxml")
                            for pdf_link in soup3.select(
                                "a[href$='.pdf'], "
                                "a[href*='/files/'], "
                                "a[href*='ViewDocument']"
                            ):
                                h = pdf_link.get("href", "").strip()
                                if h:
                                    au = urljoin(alt_docs_url, h)
                                    if au not in seen_urls:
                                        seen_urls.add(au)
                                        fn = pdf_link.get("title", "") or pdf_link.get_text(strip=True) or h.split("/")[-1]
                                        documents.append({
                                            "url": au,
                                            "filename": fn,
                                            "document_type": _classify_document(fn),
                                        })
                            break

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error discovering documents at {detail_url}: {e.response.status_code}")
        return json.dumps({
            "found": False,
            "documents": [],
            "total_count": 0,
            "message": f"HTTP {e.response.status_code} when accessing planning portal. The portal may be down.",
        })
    except Exception as e:
        logger.error(f"Document discovery failed for {detail_url}: {e}")
        return json.dumps({
            "found": False,
            "documents": [],
            "total_count": 0,
            "message": f"Failed to discover documents: {str(e)}",
        })

    # Sort by document type priority (D&A statements first)
    type_priority = {
        "design_and_access_statement": 0,
        "application_form": 1,
        "planning_statement": 2,
        "proposed_plans": 3,
        "floor_plan": 4,
        "elevation_drawing": 5,
        "existing_plans": 6,
        "drawing": 7,
        "statement": 8,
        "structural_report": 9,
        "heritage_statement": 10,
        "officer_report": 11,
        "decision_notice": 12,
        "location_plan": 13,
        "site_notice": 14,
        "certificate": 15,
        "cil_form": 16,
        "other": 17,
    }
    documents.sort(key=lambda d: type_priority.get(d["document_type"], 99))

    # Store the documents tab URL so download_planning_pdf can establish
    # a session with the same portal (Idox requires JSESSIONID)
    discover_planning_documents._session_url = docs_url

    logger.info(f"Discovered {len(documents)} documents from {detail_url}")

    return json.dumps({
        "found": len(documents) > 0,
        "documents": documents,
        "total_count": len(documents),
        "message": (
            f"Found {len(documents)} documents on the planning portal. "
            f"Types: {', '.join(set(d['document_type'] for d in documents))}"
            if documents
            else "No documents found on the planning portal page."
        ),
    })


@tool
async def download_planning_pdf(url: str) -> str:
    """Download a planning application PDF from a URL.

    Automatically establishes a browser session with the planning portal
    first (required for Idox portals like Lambeth which need a JSESSIONID
    cookie before serving PDF files).

    Args:
        url: Full URL to the PDF document on the council planning portal.

    Returns:
        JSON with keys: success (bool), size_bytes (int), message (str).
        The PDF bytes are stored internally for extraction.
    """
    try:
        # Use session URL from discover_planning_documents if available
        # (Lambeth Idox requires JSESSIONID from the documents page)
        session_url = getattr(discover_planning_documents, "_session_url", "")
        if not session_url:
            # Derive a session URL from the PDF URL as fallback
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if "online-applications" in url:
                session_url = f"{parsed.scheme}://{parsed.netloc}/online-applications/"
            elif "PlanningExplorer" in url:
                session_url = f"{parsed.scheme}://{parsed.netloc}/Northgate/PlanningExplorer/"

        pdf_bytes = await download_pdf(url, session_url=session_url)
        if pdf_bytes is None:
            return json.dumps({
                "success": False,
                "size_bytes": 0,
                "message": f"Failed to download PDF from {url} — file too small or unreachable.",
            })

        # Store in tool's internal state for the extraction step
        download_planning_pdf._last_pdf = pdf_bytes
        return json.dumps({
            "success": True,
            "size_bytes": len(pdf_bytes),
            "message": f"Successfully downloaded PDF ({len(pdf_bytes):,} bytes). Ready for extraction.",
        })
    except Exception as e:
        logger.error(f"PDF download failed: {e}")
        return json.dumps({
            "success": False,
            "size_bytes": 0,
            "message": f"Download error: {str(e)}",
        })


# Initialise internal storage
download_planning_pdf._last_pdf = None
discover_planning_documents._session_url = ""


@tool
async def extract_data_from_pdf(use_last_download: bool = True) -> str:
    """Extract structured property and work data from a planning PDF using
    Google Gemini's native PDF reading via the Files API.

    Google reads the FULL document natively — text, tables, floor plans,
    diagrams, even handwritten annotations. This is much better than
    text-only extraction.

    Extracts 25+ fields including property type, work description, materials,
    costs, dimensions, conservation status, building fabric, and more.

    The extraction uses the Gemini Files API which uploads the PDF to Google
    for native document understanding, then falls back to inline base64 if
    the upload fails.

    Args:
        use_last_download: If True (default), uses the PDF from the most recent
            download_planning_pdf call.

    Returns:
        JSON with keys: extracted_data (dict with 25+ fields), confidence (0-1),
        fields_found (int), cost_gbp (float), extraction_method (str).
    """
    pdf_bytes = getattr(download_planning_pdf, "_last_pdf", None)
    if pdf_bytes is None:
        return json.dumps({
            "extracted_data": {},
            "confidence": 0.0,
            "fields_found": 0,
            "cost_gbp": 0.0,
            "extraction_method": "none",
            "message": "No PDF available. Call download_planning_pdf first.",
        })

    gemini = _get_gemini()

    # Try Files API first (native PDF reading — best quality)
    try:
        data, confidence = await gemini.extract_from_pdf(pdf_bytes)
        extraction_method = "gemini_files_api"
    except Exception as e:
        logger.warning(f"Files API failed, falling back to inline: {e}")
        # Fallback to inline base64
        data, confidence = await gemini.extract_from_pdf_inline(pdf_bytes)
        extraction_method = "gemini_inline_base64"

    fields_found = sum(
        1 for v in data.values()
        if v is not None and v != [] and v != ""
    )

    # Build a readable summary of what was found
    key_findings = []
    if data.get("property_type"):
        key_findings.append(f"property: {data['property_type']}")
    if data.get("work_category"):
        key_findings.append(f"work: {data['work_category']}")
    if data.get("floor_area_added_m2"):
        key_findings.append(f"area: {data['floor_area_added_m2']}m²")
    if data.get("estimated_cost"):
        key_findings.append(f"cost: £{data['estimated_cost']:,.0f}")
    if data.get("materials"):
        key_findings.append(f"materials: {', '.join(data['materials'][:3])}")
    if data.get("document_type"):
        key_findings.append(f"doc type: {data['document_type']}")

    return json.dumps({
        "extracted_data": data,
        "confidence": confidence,
        "fields_found": fields_found,
        "cost_gbp": gemini.total_cost_gbp,
        "extraction_method": extraction_method,
        "message": (
            f"Extracted {fields_found} fields with {confidence:.0%} confidence "
            f"via {extraction_method}. "
            f"Key findings: {'; '.join(key_findings) if key_findings else 'minimal data'}"
        ),
    })


@tool
def analyse_pdf_filenames(pdf_urls: list[str]) -> str:
    """Analyse PDF filenames to determine which ones are most likely to contain
    useful planning data (application forms, design statements, etc.) vs
    less useful ones (site notices, neighbour letters, etc.).

    Prioritises:
    - Design & Access Statements (richest data — descriptions, materials, dimensions)
    - Application forms (structured data — property type, bedrooms, costs)
    - Proposed floor plans / drawings (dimensions, layout)
    - Supporting statements

    Deprioritises:
    - Site notices, neighbour consultation letters
    - Ownership certificates, fee receipts
    - Location plans (minimal data)

    Args:
        pdf_urls: List of PDF URLs from the planning application.

    Returns:
        JSON with prioritised list of URLs and reasoning for each.
    """
    # High-value document types for data extraction
    priority_keywords = {
        "design": 4, "access": 3, "statement": 3,
        "application": 3, "form": 2,
        "proposed": 2, "plans": 2, "drawings": 2,
        "planning": 2, "supporting": 1,
        "floor": 2, "elevation": 1, "section": 1,
        "structural": 1, "heritage": 1, "energy": 1,
    }
    skip_keywords = {
        "notice": -4, "neighbour": -3, "consultation": -3,
        "letter": -2, "certificate": -3, "ownership": -3,
        "receipt": -4, "fee": -3, "cil": -2,
        "location": -1, "site_notice": -4,
    }

    results = []
    for url in pdf_urls:
        filename = url.split("/")[-1].lower().replace("%20", " ").replace("_", " ")
        score = 0
        reasons = []

        for kw, weight in priority_keywords.items():
            if kw in filename:
                score += weight
                reasons.append(f"Contains '{kw}' (+{weight})")

        for kw, weight in skip_keywords.items():
            if kw in filename:
                score += weight  # weight is negative
                reasons.append(f"Contains '{kw}' ({weight})")

        if not reasons:
            score = 1
            reasons.append("No recognised keywords — worth trying")

        # Boost D&A statements specifically (most data-rich)
        if "design" in filename and "access" in filename:
            score += 3
            reasons.append("Design & Access Statement — highest value document (+3)")

        results.append({
            "url": url,
            "filename": url.split("/")[-1],
            "priority_score": score,
            "reasoning": "; ".join(reasons),
        })

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return json.dumps({
        "prioritised_pdfs": results,
        "recommendation": (
            f"Try the top {min(3, len(results))} PDFs in order. "
            f"Best candidate: {results[0]['filename'] if results else 'none'}"
        ),
    })


# Convenience list for agent construction
PDF_TOOLS = [discover_planning_documents, analyse_pdf_filenames, download_planning_pdf, extract_data_from_pdf]
