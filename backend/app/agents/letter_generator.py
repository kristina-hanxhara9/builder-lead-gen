"""Agent 5: Letter Generation — LangChain Agent with Tools.

Generates personalised letter content via Gemini and creates a branded PDF.
Only runs if lead score >= minimum threshold. The agent reasons about
which case studies to use, generates the letter, and creates the PDF.
"""

import json
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.state import AgentState
from app.agents.tools.letter_tools import LETTER_TOOLS, create_branded_pdf, fetch_property_images, reset_gemini
from app.core.config import settings

logger = logging.getLogger(__name__)

LETTER_SYSTEM_PROMPT = """You are Agent 5 — the Letter Generation specialist for Smith & Sons Builders'
lead generation pipeline.

Your job is to create a personalised, professional sales letter and branded PDF
for a qualified lead — complete with property imagery.

## Your tools:
1. **get_company_context** — Get company background for personalisation
2. **select_case_studies** — Choose relevant case studies for the letter
3. **generate_letter_content** — Generate the letter text via Gemini AI
4. **fetch_property_images** — Get Street View photo and map of the property
5. **generate_qr_tracking_url** — Create a unique tracking URL for the letter
6. **create_branded_pdf** — Create the final branded PDF with letterhead + images

## Your workflow:
1. Get company context for the letter
2. Select relevant case studies based on work type and location
3. Fetch property images (Street View + map) — this makes the PDF much more personal
4. Generate the letter content — pass ALL available property data via property_facts_json
5. Generate a QR tracking URL
6. Create the branded PDF (images are automatically included if fetched)

## CRITICAL — Property data grounding:
When calling generate_letter_content, you MUST pass the property_facts_json parameter
with ALL the real property data available. This includes EPC data (energy rating,
floor area, building age, walls, roof, heating) and planning extraction data
(materials, bedrooms, estimated cost, conservation area status).

The letter MUST only reference facts that come from real data. Never fabricate
project details, addresses, or statistics.

## Letter quality guidelines:
- Professional but warm — we're a family business
- Reference the specific planning application
- Use real property facts (EPC rating, floor area, etc.) for personalisation
- Mention nearby projects ONLY from case studies (never invent them)
- Keep it to 250-300 words
- Don't be pushy — be helpful and knowledgeable"""


async def generate_letter(state: AgentState) -> dict:
    """LangChain agent that generates a personalised letter and PDF.

    Uses tools to select case studies, generate content, and create PDF.
    """
    unified = state.get("unified_data", {})
    app_id = state.get("planning_app_id", "unknown")
    total_cost = state.get("total_cost_gbp", 0.0)

    # Reset Gemini for fresh cost tracking
    reset_gemini()

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.3,  # Slightly higher for creative letter writing
    )

    # Build property facts JSON for the letter tool
    import json as _json
    property_facts = {
        "epc_rating": unified.get("epc_rating"),
        "epc_potential_rating": unified.get("epc_potential_rating"),
        "total_floor_area_m2": unified.get("total_floor_area_m2"),
        "floor_area_added_m2": unified.get("floor_area_added_m2"),
        "construction_age": unified.get("construction_age"),
        "bedrooms_before": unified.get("bedrooms_before"),
        "bedrooms_after": unified.get("bedrooms_after"),
        "materials": unified.get("materials"),
        "estimated_cost": unified.get("estimated_cost"),
        "walls": unified.get("walls"),
        "roof": unified.get("roof"),
        "heating": unified.get("heating"),
        "conservation_area": unified.get("conservation_area"),
        "listed_building": unified.get("listed_building"),
    }
    # Remove None values to keep it clean
    property_facts = {k: v for k, v in property_facts.items() if v is not None}
    property_facts_str = _json.dumps(property_facts)

    prompt = ChatPromptTemplate.from_messages([
        ("system", LETTER_SYSTEM_PROMPT),
        ("human",
         "Generate a personalised letter for this lead:\n\n"
         "**Address**: {address}\n"
         "**Planning Reference**: {planning_reference}\n"
         "**Work Description**: {work_description}\n"
         "**Property Type**: {property_type}\n"
         "**Planning Status**: {planning_status}\n"
         "**District**: {district}\n"
         "**Lead Score**: {lead_score}/100\n"
         "**EPC Rating**: {epc_rating}\n\n"
         "**Property Facts (pass this as property_facts_json to generate_letter_content)**:\n"
         "{property_facts}\n\n"
         "IMPORTANT: When calling generate_letter_content, pass the property_facts_json "
         "parameter with the property facts JSON above. This ensures the letter is "
         "grounded in real data.\n\n"
         "Create the letter, select case studies, generate the PDF, "
         "and create a QR tracking URL. Letter ID for tracking: {app_id}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm_with_tools = llm.bind_tools(LETTER_TOOLS)
    messages = prompt.format_messages(
        address=unified.get("address", ""),
        planning_reference=unified.get("planning_reference", ""),
        work_description=unified.get("work_description", "")[:300],
        property_type=unified.get("property_type", "residential property"),
        planning_status=unified.get("planning_status", "submitted"),
        district=unified.get("district", "SW London"),
        lead_score=state.get("lead_score", 0),
        epc_rating=unified.get("epc_rating", "N/A"),
        property_facts=property_facts_str,
        app_id=app_id,
        agent_scratchpad=[],
    )

    letter_content = None
    letter_pdf_bytes = None
    qr_url = None
    case_studies_used = []
    word_count = 0
    agent_logs = []

    from langchain_core.messages import ToolMessage

    for iteration in range(15):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            tool_fn = next((t for t in LETTER_TOOLS if t.name == tool_name), None)
            if tool_fn is None:
                result = json.dumps({"error": f"Unknown tool: {tool_name}"})
            else:
                try:
                    logger.info(f"[Agent 5] Calling {tool_name}")
                    logger.debug(f"[Agent 5] Args types: {[(k, type(v).__name__) for k, v in tool_args.items()]}")
                    if hasattr(tool_fn, "coroutine") or "async" in str(type(tool_fn)):
                        result = await tool_fn.ainvoke(tool_args)
                    else:
                        result = tool_fn.invoke(tool_args)
                except Exception as e:
                    logger.error(f"[Agent 5] Tool {tool_name} failed: {e}", exc_info=True)
                    result = json.dumps({"error": str(e)})

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

            # Track outputs
            try:
                tool_result = json.loads(result) if isinstance(result, str) else result
            except (json.JSONDecodeError, TypeError):
                continue

            if tool_name == "select_case_studies":
                studies = tool_result.get("case_studies", [])
                case_studies_used = [cs.get("title", "") for cs in studies]
                agent_logs.append(
                    f"[Agent 5] Selected {len(studies)} case studies"
                )

            elif tool_name == "generate_letter_content":
                if tool_result.get("success"):
                    letter_content = tool_result.get("letter_content")
                    word_count = tool_result.get("word_count", 0)
                    total_cost += tool_result.get("cost_gbp", 0.0)
                    agent_logs.append(
                        f"[Agent 5] Generated {word_count}-word letter "
                        f"(cost: £{tool_result.get('cost_gbp', 0):.4f})"
                    )
                else:
                    agent_logs.append("[Agent 5] Letter generation failed")

            elif tool_name == "generate_qr_tracking_url":
                qr_url = tool_result.get("qr_url")
                agent_logs.append("[Agent 5] QR URL generated")

            elif tool_name == "create_branded_pdf":
                if tool_result.get("success"):
                    letter_pdf_bytes = getattr(create_branded_pdf, "_last_pdf", None)
                    agent_logs.append(
                        f"[Agent 5] PDF created ({tool_result.get('pdf_size_kb', 0)} KB)"
                    )
                else:
                    agent_logs.append("[Agent 5] PDF creation failed")

    errors = []
    if not letter_content:
        errors.append("[Agent 5] Failed to generate letter content")
    if not letter_pdf_bytes:
        errors.append("[Agent 5] Failed to create PDF")

    logger.info(
        f"Agent 5 complete: letter={'yes' if letter_content else 'no'}, "
        f"PDF={'yes' if letter_pdf_bytes else 'no'}, "
        f"cost=£{total_cost:.4f}"
    )

    return {
        "letter_content": letter_content,
        "letter_pdf_bytes": letter_pdf_bytes,
        "qr_url": qr_url,
        "letter_output": {
            "content": letter_content or "",
            "pdf_bytes": letter_pdf_bytes,
            "qr_url": qr_url or "",
            "case_studies_used": case_studies_used,
            "word_count": word_count,
            "tone": "professional_warm",
            "personalisation_score": 0.0,
        } if letter_content else None,
        "total_cost_gbp": total_cost,
        "errors": errors,
        "agent_logs": [
            f"[Agent 5 @ {datetime.utcnow().isoformat()}] "
            f"Letter: {word_count} words, "
            f"PDF: {'created' if letter_pdf_bytes else 'failed'}, "
            f"cost: £{total_cost:.4f}"
        ] + agent_logs,
        "processing_steps": [{
            "agent": "letter_generator",
            "status": "complete" if letter_content else "failed",
            "word_count": word_count,
            "pdf_created": letter_pdf_bytes is not None,
            "case_studies": len(case_studies_used),
            "qr_url_created": qr_url is not None,
        }],
        "current_agent": "letter_generator",
    }
