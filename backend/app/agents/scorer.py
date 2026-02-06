"""Agent 4: Lead Scoring — LangChain Agent with Tools.

Scores leads 0-100 using 4 weighted factors. Reasons about each
factor using dedicated tools, then makes the final go/no-go decision.
"""

import json
import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.state import AgentState
from app.agents.tools.scoring_tools import SCORING_TOOLS
from app.core.config import client_config, settings

logger = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """You are Agent 4 — the Lead Scoring specialist for Smith & Sons Builders'
lead generation pipeline.

Your job is to evaluate leads using scoring tools and then make a go/no-go
decision on whether to create a lead and generate a sales letter.

## Your tools:
1. **geocode_property** — Geocode address for precise distance (optional but recommended)
2. **score_geography** — Score based on proximity to our service area (max 30 pts)
3. **score_property_value** — Score based on estimated property value (max 25 pts)
4. **score_work_type** — Score based on relevance to our services (max 30 pts)
5. **score_timing** — Score based on planning application status & age (max 15 pts)
6. **make_lead_decision** — Final go/no-go decision based on total score

## Your workflow:
1. Optionally geocode the property for precise distance measurement
2. Score ALL four factors using the scoring tools
3. Add up the total score
4. Call make_lead_decision with the total and breakdown
5. Explain your reasoning for the final decision

## Scoring thresholds:
- Total >= {auto_threshold}: Auto-approve letter (best leads)
- Total >= {min_score}: Create lead + generate letter for manual review
- Total < {min_score}: Discard — not worth pursuing

Be thorough and call all 4 scoring tools before making a decision."""


async def score_lead(state: AgentState) -> dict:
    """LangChain agent that reasons about lead scoring.

    Uses tools to evaluate 4 factors and make the final decision.
    """
    unified = state.get("unified_data", {})

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.1,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", SCORING_SYSTEM_PROMPT.format(
            min_score=client_config.minimum_score,
            auto_threshold=client_config.auto_send_threshold,
        )),
        ("human",
         "Please score this lead:\n\n"
         "**Property**: {address} ({postcode})\n"
         "**District**: {district}\n"
         "**Property Type**: {property_type}\n"
         "**Estimated Value**: £{property_value:,}\n"
         "**Distance from Office**: {distance_km:.1f} km\n"
         "**Work Description**: {work_description}\n"
         "**Work Category**: {work_category}\n"
         "**Planning Status**: {planning_status}\n"
         "**Submitted Date**: {submitted_date}\n\n"
         "Score all 4 factors and make a decision."),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm_with_tools = llm.bind_tools(SCORING_TOOLS)
    messages = prompt.format_messages(
        address=unified.get("address", "Unknown"),
        postcode=unified.get("postcode", ""),
        district=unified.get("district", ""),
        property_type=unified.get("property_type", "Unknown"),
        property_value=unified.get("property_value_estimate", 0),
        distance_km=unified.get("distance_from_office_km", 0.0),
        work_description=unified.get("work_description", "No description")[:200],
        work_category=unified.get("work_category", "unknown"),
        planning_status=unified.get("planning_status", "Unknown"),
        submitted_date=unified.get("submitted_date", "Unknown"),
        agent_scratchpad=[],
    )

    breakdown = {}
    total_score = 0.0
    should_generate = False
    auto_approve = False
    scoring_reasoning = ""
    agent_logs = []

    from langchain_core.messages import ToolMessage

    for iteration in range(12):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # Agent done — extract final reasoning from response
            if response.content:
                scoring_reasoning = str(response.content)
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            tool_fn = next((t for t in SCORING_TOOLS if t.name == tool_name), None)
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

            # Extract scoring data
            try:
                score_result = json.loads(result) if isinstance(result, str) else result
            except (json.JSONDecodeError, TypeError):
                continue

            if tool_name == "geocode_property":
                if score_result.get("geocoded"):
                    agent_logs.append(
                        f"[Agent 4] Geocoded: {score_result.get('distance_from_office_km', '?')} km from office"
                    )

            elif tool_name == "score_geography":
                breakdown["geography"] = score_result
                total_score += score_result.get("score", 0)
                agent_logs.append(
                    f"[Agent 4] Geography: {score_result.get('score', 0)}/{score_result.get('max_points', 30)}"
                )

            elif tool_name == "score_property_value":
                breakdown["property_value"] = score_result
                total_score += score_result.get("score", 0)
                agent_logs.append(
                    f"[Agent 4] Value: {score_result.get('score', 0)}/{score_result.get('max_points', 25)}"
                )

            elif tool_name == "score_work_type":
                breakdown["work_type"] = score_result
                total_score += score_result.get("score", 0)
                agent_logs.append(
                    f"[Agent 4] Work: {score_result.get('score', 0)}/{score_result.get('max_points', 30)}"
                )

            elif tool_name == "score_timing":
                breakdown["timing"] = score_result
                total_score += score_result.get("score", 0)
                agent_logs.append(
                    f"[Agent 4] Timing: {score_result.get('score', 0)}/{score_result.get('max_points', 15)}"
                )

            elif tool_name == "make_lead_decision":
                should_generate = score_result.get("should_generate_letter", False)
                auto_approve = score_result.get("auto_approve", False)
                scoring_reasoning = score_result.get("reasoning", "")
                agent_logs.append(
                    f"[Agent 4] Decision: {score_result.get('decision', 'unknown')}"
                )

    total_score = round(total_score, 1)
    breakdown["total"] = total_score
    breakdown["reasoning"] = scoring_reasoning

    # Fallback: if the agent didn't call make_lead_decision (or it failed),
    # apply thresholds directly from config
    if not should_generate and total_score >= client_config.minimum_score:
        should_generate = True
        auto_approve = total_score >= client_config.auto_send_threshold
        logger.info(f"Applied fallback threshold: score {total_score} >= {client_config.minimum_score}")

    logger.info(
        f"Agent 4 complete: score={total_score}/100, "
        f"generate={'yes' if should_generate else 'no'}, "
        f"auto_approve={'yes' if auto_approve else 'no'}"
    )

    return {
        "lead_score": total_score,
        "score_breakdown": breakdown,
        "should_generate_letter": should_generate,
        "auto_approve_letter": auto_approve,
        "scoring_reasoning": scoring_reasoning,
        "errors": [],
        "agent_logs": [
            f"[Agent 4 @ {datetime.utcnow().isoformat()}] "
            f"Score: {total_score}/100 → {'GENERATE' if should_generate else 'DISCARD'}"
        ] + agent_logs,
        "processing_steps": [{
            "agent": "scorer",
            "status": "complete",
            "total_score": total_score,
            "should_generate_letter": should_generate,
            "auto_approve": auto_approve,
            "breakdown": {k: v.get("score", 0) if isinstance(v, dict) else v for k, v in breakdown.items()},
        }],
        "current_agent": "scorer",
    }
