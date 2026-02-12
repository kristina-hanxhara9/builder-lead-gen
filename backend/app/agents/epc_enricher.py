"""Agent 2: EPC Data Enrichment — LangChain Agent with Tools.

Fetches Energy Performance Certificate data for the property.
Reasons about cache vs API, address matching confidence, and
interprets the EPC data for downstream use.
"""

import json
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.state import AgentState
from app.agents.tools.epc_tools import EPC_TOOLS, cleanup_epc_service
from app.core.config import settings

logger = logging.getLogger(__name__)

EPC_SYSTEM_PROMPT = """You are Agent 2 — the EPC Enrichment specialist for Smith & Sons Builders'
lead generation pipeline.

Your job is to fetch Energy Performance Certificate data for properties
and interpret what it means for our sales approach.

## Your tools:
1. **check_epc_cache** — Check if we have cached EPC data (saves API calls)
2. **lookup_epc_by_postcode** — Query the UK Government EPC API
3. **interpret_epc_rating** — Understand what the rating means for our letter

## Your workflow:
1. First, check the cache for existing EPC data
2. If not cached, call the EPC API with postcode and address
3. If data found, interpret the EPC rating for personalisation
4. Report the data source (cache/api) and match confidence

## Important context:
- Not all properties have EPCs — this is NOT an error
- New builds and properties that haven't been sold/rented may lack EPCs
- EPCs are most useful for understanding:
  * Property type (detached, semi, terraced, flat)
  * Construction age
  * Floor area
  * Building fabric (walls, roof, windows, heating)
  * Energy efficiency (affects letter personalisation)
- A low EPC rating is an OPPORTUNITY for our letter — we can mention
  that new building work can improve energy efficiency."""


async def enrich_with_epc(state: AgentState) -> dict:
    """LangChain agent that reasons about EPC data enrichment.

    Uses tools to check cache, query API, and interpret ratings.
    """
    postcode = state["planning_app_data"].get("postcode", "")
    address = state["planning_app_data"].get("address", "")
    description = state["planning_app_data"].get("description", "")
    borough = state["planning_app_data"].get("local_authority", "")

    # If no postcode, try to derive it from address, description, or geocoding
    if not postcode:
        logger.info("No postcode — attempting to derive from address/description/geocoding")
        from app.services.postcode_service import PostcodeService
        pc_service = PostcodeService()
        try:
            # Try address first, then description (councils often put addresses there)
            for text_source in [address, description]:
                if not text_source:
                    continue
                result = await pc_service.derive_postcode(text_source, borough)
                if result["postcode"]:
                    postcode = result["postcode"]
                    logger.info(
                        f"Derived postcode {postcode} via {result['method']} "
                        f"(confidence={result['confidence']:.0%})"
                    )
                    # Update state so downstream agents have it too
                    state["planning_app_data"]["postcode"] = postcode
                    break
        finally:
            await pc_service.close()

    if not postcode:
        logger.warning("No postcode and couldn't derive one — skipping EPC")
        return {
            "epc_data": None,
            "epc_match_confidence": 0.0,
            "epc_source": "none",
            "errors": [],
            "agent_logs": [
                f"[Agent 2 @ {datetime.utcnow().isoformat()}] "
                f"No postcode (tried address, description, geocoding) — skipping EPC"
            ],
            "processing_steps": [{"agent": "epc_enricher", "status": "skipped", "reason": "no_postcode"}],
            "current_agent": "epc_enricher",
        }

    # Build the LangChain agent
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.1,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", EPC_SYSTEM_PROMPT),
        ("human",
         "Please look up EPC data for:\n"
         "  Postcode: {postcode}\n"
         "  Address: {address}\n\n"
         "Check the cache first, then query the API if needed. "
         "Interpret the rating if found."),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm_with_tools = llm.bind_tools(EPC_TOOLS)
    messages = prompt.format_messages(
        postcode=postcode,
        address=address or "(no address provided)",
        agent_scratchpad=[],
    )

    epc_data = None
    epc_source = "none"
    match_confidence = 0.0
    agent_logs = []

    from langchain_core.messages import ToolMessage

    for iteration in range(8):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            tool_fn = next((t for t in EPC_TOOLS if t.name == tool_name), None)
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

            # Track EPC data from lookup results
            if tool_name == "lookup_epc_by_postcode":
                try:
                    lookup_result = json.loads(result) if isinstance(result, str) else result
                    if lookup_result.get("found"):
                        epc_data = lookup_result.get("data")
                        epc_source = lookup_result.get("source", "api")
                        match_confidence = lookup_result.get("match_confidence", 0.0)
                        agent_logs.append(
                            f"[Agent 2] EPC found via {epc_source}: "
                            f"rating={epc_data.get('current_rating', '?')}, "
                            f"type={epc_data.get('property_type', '?')}"
                        )
                    else:
                        agent_logs.append(f"[Agent 2] No EPC data found for {postcode}")
                except (json.JSONDecodeError, TypeError):
                    pass

            if tool_name == "check_epc_cache":
                try:
                    cache_result = json.loads(result) if isinstance(result, str) else result
                    if cache_result.get("cached"):
                        agent_logs.append(f"[Agent 2] Cache hit for {postcode}")
                except (json.JSONDecodeError, TypeError):
                    pass

    # Cleanup the httpx client
    await cleanup_epc_service()

    logger.info(
        f"Agent 2 complete: EPC {'found' if epc_data else 'not found'}, "
        f"source={epc_source}, confidence={match_confidence:.2f}"
    )

    return {
        "epc_data": epc_data,
        "epc_match_confidence": match_confidence,
        "epc_source": epc_source,
        "errors": [],
        "agent_logs": [
            f"[Agent 2 @ {datetime.utcnow().isoformat()}] "
            f"EPC lookup: {'found' if epc_data else 'no data'} "
            f"(source={epc_source}, confidence={match_confidence:.2f})"
        ] + agent_logs,
        "processing_steps": [{
            "agent": "epc_enricher",
            "status": "complete",
            "epc_found": epc_data is not None,
            "source": epc_source,
            "match_confidence": match_confidence,
        }],
        "current_agent": "epc_enricher",
    }
