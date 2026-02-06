"""Agent 1: PDF Extraction via Gemini — LangChain Agent with Tools.

DISCOVER → DOWNLOAD → EXTRACT pipeline:
1. If no PDF URLs are pre-loaded, discover documents from the planning portal
2. Analyse filenames to prioritise which PDFs contain the richest data
3. Download the highest-priority PDFs
4. Extract structured property/work data via Gemini 2.0 Flash
5. Reason about confidence and whether to try additional PDFs
"""

import json
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.state import AgentState
from app.agents.tools.pdf_tools import PDF_TOOLS, reset_gemini
from app.core.config import settings

logger = logging.getLogger(__name__)

# System prompt for the extraction agent
EXTRACTION_SYSTEM_PROMPT = """You are Agent 1 — the PDF Extraction specialist for Smith & Sons Builders'
lead generation pipeline.

Your job is to discover, download, and extract structured data from UK planning application PDFs.

## Your tools:
1. **discover_planning_documents** — Scrape the council planning portal to find all available PDFs
2. **analyse_pdf_filenames** — Prioritise which PDFs are most likely to contain useful data
3. **download_planning_pdf** — Download a specific PDF
4. **extract_data_from_pdf** — Send the downloaded PDF to Gemini for structured extraction

## Your workflow:

### If you have a detail_url but NO pdf_urls:
1. Call **discover_planning_documents** with the detail_url to find all documents
2. Review the discovered documents — the tool returns them sorted by priority
3. Download the highest-priority document (Design & Access Statements are best)
4. Extract data from it
5. If confidence < 0.5, try the next priority document
6. Stop after 3 PDFs or when confidence >= 0.5

### If you already have pdf_urls:
1. Call **analyse_pdf_filenames** to prioritise the URLs
2. Download the highest-priority PDF
3. Extract data from it
4. If confidence < 0.5, try the next one
5. Stop after 3 PDFs or when confidence >= 0.5

## Document priority (best to worst for data extraction):
- Design & Access Statements — richest source of data (descriptions, materials, dimensions)
- Application Forms — structured data (property type, bedrooms, costs)
- Planning Statements — supporting information
- Proposed Plans / Drawings — dimensions, layout
- Everything else — usually low value

## Important rules:
- ALWAYS try to discover documents if pdf_urls is empty — don't just give up
- Skip PDFs that are clearly admin documents (notices, receipts, certificates, CIL forms)
- The discover tool sorts documents by priority — take the top ones
- Track how many PDFs you attempted and succeeded with
- Report the extraction model used and cost

Return your final assessment as a clear summary of what was extracted."""


async def extract_planning_pdf(state: AgentState) -> dict:
    """LangChain agent that reasons about PDF extraction.

    Uses tools to discover documents on the portal, analyse filenames,
    download PDFs, and extract data. If no pdf_urls are available but
    a detail_url exists, the agent discovers documents first.
    """
    pdf_urls = state["planning_app_data"].get("pdf_urls", [])
    detail_url = state["planning_app_data"].get("detail_url", "")
    app_id = state["planning_app_id"]

    if not pdf_urls and not detail_url:
        logger.warning(f"No PDFs and no detail URL for planning app {app_id}")
        return {
            "extracted_data": {},
            "extraction_confidence": 0.0,
            "pdfs_attempted": 0,
            "pdfs_succeeded": 0,
            "extraction_model_used": "none",
            "errors": [f"[Agent 1] No PDF URLs or detail URL for {app_id}"],
            "agent_logs": [f"[Agent 1 @ {datetime.utcnow().isoformat()}] No PDFs or detail URL — skipping"],
            "processing_steps": [{"agent": "pdf_extractor", "status": "skipped", "reason": "no_pdfs_or_detail_url"}],
            "current_agent": "pdf_extractor",
        }

    # Reset Gemini service for fresh cost tracking
    reset_gemini()

    # Build the LangChain agent
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.1,
    )

    # Build context-aware prompt based on what we have
    if pdf_urls:
        pdf_list = "\n".join(f"  {i+1}. {url}" for i, url in enumerate(pdf_urls))
        human_msg = (
            "Planning application {app_id} has {num_pdfs} pre-loaded PDF URLs:\n"
            "{pdf_list}\n\n"
            "Please analyse, download, and extract data from the most relevant PDFs. "
            "Stop when you get confidence >= 0.5 or after 3 attempts."
        )
    else:
        pdf_list = "(none — you must discover them)"
        human_msg = (
            "Planning application {app_id} has NO pre-loaded PDF URLs, but I have a "
            "detail URL for the planning portal:\n"
            "  {detail_url}\n\n"
            "Please:\n"
            "1. Call discover_planning_documents with the detail URL to find available PDFs\n"
            "2. Download the most relevant document (prioritise Design & Access Statements)\n"
            "3. Extract data from it\n"
            "4. Try more PDFs if confidence is low (< 0.5)\n"
            "Stop after 3 PDF downloads or when confidence >= 0.5."
        )

    prompt = ChatPromptTemplate.from_messages([
        ("system", EXTRACTION_SYSTEM_PROMPT),
        ("human", human_msg),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    # Use the tool-calling agent pattern
    llm_with_tools = llm.bind_tools(PDF_TOOLS)

    messages = prompt.format_messages(
        app_id=app_id,
        num_pdfs=len(pdf_urls),
        pdf_list=pdf_list,
        detail_url=detail_url,
        agent_scratchpad=[],
    )

    best_data = {}
    best_confidence = 0.0
    pdfs_attempted = 0
    pdfs_succeeded = 0
    docs_discovered = 0
    total_cost = state.get("total_cost_gbp", 0.0)
    agent_logs = []

    # Run the agent loop (max 15 iterations — extra room for discover step)
    from langchain_core.messages import ToolMessage

    for iteration in range(15):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # Agent finished reasoning
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            # Find and execute the tool
            tool_fn = next((t for t in PDF_TOOLS if t.name == tool_name), None)
            if tool_fn is None:
                result = json.dumps({"error": f"Unknown tool: {tool_name}"})
            else:
                try:
                    if hasattr(tool_fn, "coroutine") or "async" in str(type(tool_fn)):
                        result = await tool_fn.ainvoke(tool_args)
                    else:
                        result = tool_fn.invoke(tool_args)
                except Exception as e:
                    result = json.dumps({"error": str(e)})

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            # Track discovery results
            if tool_name == "discover_planning_documents":
                try:
                    disc_result = json.loads(result) if isinstance(result, str) else result
                    docs_discovered = disc_result.get("total_count", 0)
                    agent_logs.append(
                        f"[Agent 1] Discovered {docs_discovered} documents on portal"
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

            # Track metrics from download results
            if tool_name == "download_planning_pdf":
                pdfs_attempted += 1
                try:
                    dl_result = json.loads(result) if isinstance(result, str) else result
                    if dl_result.get("success"):
                        pdfs_succeeded += 1
                except (json.JSONDecodeError, TypeError):
                    pass

            if tool_name == "extract_data_from_pdf":
                try:
                    ext_result = json.loads(result) if isinstance(result, str) else result
                    conf = ext_result.get("confidence", 0.0)
                    if conf > best_confidence:
                        best_data = ext_result.get("extracted_data", {})
                        best_confidence = conf
                    total_cost = ext_result.get("cost_gbp", total_cost)
                    agent_logs.append(
                        f"[Agent 1] Extraction: {ext_result.get('fields_found', 0)} fields, "
                        f"{conf:.0%} confidence"
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

    logger.info(
        f"Agent 1 complete: discovered={docs_discovered}, attempted={pdfs_attempted}, "
        f"succeeded={pdfs_succeeded}, confidence={best_confidence:.2f}"
    )

    return {
        "extracted_data": best_data,
        "extraction_confidence": best_confidence,
        "pdfs_attempted": pdfs_attempted,
        "pdfs_succeeded": pdfs_succeeded,
        "extraction_model_used": "gemini-2.0-flash",
        "total_cost_gbp": total_cost,
        "errors": [],
        "agent_logs": [
            f"[Agent 1 @ {datetime.utcnow().isoformat()}] "
            f"Discovered {docs_discovered} docs, processed {pdfs_attempted} PDFs → "
            f"confidence {best_confidence:.0%}"
        ] + agent_logs,
        "processing_steps": [{
            "agent": "pdf_extractor",
            "status": "complete",
            "docs_discovered": docs_discovered,
            "pdfs_attempted": pdfs_attempted,
            "pdfs_succeeded": pdfs_succeeded,
            "confidence": best_confidence,
            "fields_extracted": len([v for v in best_data.values() if v is not None]),
        }],
        "current_agent": "pdf_extractor",
    }
