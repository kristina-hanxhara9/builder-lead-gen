"""LangGraph workflow with SQLiteSaver checkpointing.

Pipeline: extract_pdf → enrich_epc → combine_data → score_lead → (conditional) generate_letter

Each node is a LangChain agent with tools (except data_combiner which is
deterministic). The workflow uses checkpointing so it can resume from any
point if interrupted.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from app.agents.data_combiner import combine_data
from app.agents.epc_enricher import enrich_with_epc
from app.agents.letter_generator import generate_letter
from app.agents.pdf_extractor import extract_planning_pdf
from app.agents.scorer import score_lead
from app.agents.state import AgentState

logger = logging.getLogger(__name__)

# Checkpoint database path
CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CHECKPOINT_DB = CHECKPOINT_DIR / "pipeline_checkpoints.db"


def _ensure_checkpoint_dir():
    """Ensure the checkpoint directory exists."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def _should_generate_letter(state: AgentState) -> str:
    """Conditional edge: generate letter only if score meets threshold."""
    if state.get("should_generate_letter", False):
        logger.info("Score meets threshold — routing to letter generation")
        return "generate_letter"
    logger.info("Score below threshold — skipping letter generation")
    return "end"


def build_agent_graph(checkpointer=None) -> StateGraph:
    """Build and compile the LangGraph agent workflow.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
                      If None, runs without checkpointing.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    workflow = StateGraph(AgentState)

    # Add nodes — each is a LangChain agent with tools
    workflow.add_node("extract_pdf", extract_planning_pdf)
    workflow.add_node("enrich_epc", enrich_with_epc)
    workflow.add_node("combine_data", combine_data)
    workflow.add_node("score_lead", score_lead)
    workflow.add_node("generate_letter", generate_letter)

    # Wire edges (sequential pipeline)
    workflow.set_entry_point("extract_pdf")
    workflow.add_edge("extract_pdf", "enrich_epc")
    workflow.add_edge("enrich_epc", "combine_data")
    workflow.add_edge("combine_data", "score_lead")

    # Conditional: generate letter only if score is high enough
    workflow.add_conditional_edges(
        "score_lead",
        _should_generate_letter,
        {
            "generate_letter": "generate_letter",
            "end": END,
        },
    )
    workflow.add_edge("generate_letter", END)

    # Compile with optional checkpointer
    compile_kwargs = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return workflow.compile(**compile_kwargs)


def get_checkpointer() -> Optional[InMemorySaver]:
    """Create an in-memory checkpointer for pipeline persistence.

    Uses InMemorySaver for compatibility. For production, swap to
    PostgresSaver or AsyncPostgresSaver for durable persistence.

    Returns None if creation fails.
    """
    try:
        return InMemorySaver()
    except Exception as e:
        logger.warning(f"Could not create checkpointer: {e}. Running without checkpoints.")
        return None


# Build the graph with checkpointing
_checkpointer = get_checkpointer()
agent_pipeline = build_agent_graph(checkpointer=_checkpointer)

# Also build a non-checkpointed version for simple runs
agent_pipeline_simple = build_agent_graph(checkpointer=None)


async def run_pipeline(
    planning_app_id: str,
    planning_app_data: dict,
    use_checkpointing: bool = True,
    thread_id: Optional[str] = None,
) -> AgentState:
    """Execute the full agent pipeline for a planning application.

    Args:
        planning_app_id: UUID of the planning application record.
        planning_app_data: Dict of raw planning app data.
        use_checkpointing: Whether to use SQLite checkpointing.
        thread_id: Optional thread ID for checkpointing (auto-generated if None).

    Returns:
        Final AgentState with all outputs.
    """
    initial_state: AgentState = {
        "planning_app_id": planning_app_id,
        "planning_app_data": planning_app_data,
        "extracted_data": None,
        "extraction_confidence": 0.0,
        "pdfs_attempted": 0,
        "pdfs_succeeded": 0,
        "extraction_model_used": "",
        "epc_data": None,
        "epc_match_confidence": 0.0,
        "epc_source": "",
        "unified_data": {},
        "lead_score": 0.0,
        "score_breakdown": {},
        "should_generate_letter": False,
        "auto_approve_letter": False,
        "scoring_reasoning": "",
        "letter_output": None,
        "letter_content": None,
        "letter_pdf_bytes": None,
        "qr_url": None,
        "errors": [],
        "agent_logs": [],
        "processing_steps": [],
        "total_cost_gbp": 0.0,
        "pipeline_started_at": datetime.utcnow().isoformat(),
        "pipeline_completed_at": None,
        "current_agent": "starting",
    }

    # Choose pipeline variant
    pipeline = agent_pipeline if (use_checkpointing and _checkpointer) else agent_pipeline_simple

    # Config for checkpointing
    config = {}
    if use_checkpointing and _checkpointer:
        tid = thread_id or f"pipeline-{planning_app_id}-{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": tid}}

    logger.info(
        f"Starting pipeline for {planning_app_id} "
        f"(checkpointing={'on' if config else 'off'})"
    )

    try:
        result = await pipeline.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"Pipeline failed for {planning_app_id}: {e}")
        initial_state["errors"] = [f"Pipeline failed: {str(e)}"]
        initial_state["pipeline_completed_at"] = datetime.utcnow().isoformat()
        return initial_state

    # Stamp completion time
    result["pipeline_completed_at"] = datetime.utcnow().isoformat()

    logger.info(
        f"Pipeline complete for {planning_app_id}: "
        f"score={result.get('lead_score', 0)}, "
        f"letter={'yes' if result.get('letter_content') else 'no'}, "
        f"errors={len(result.get('errors', []))}, "
        f"cost=£{result.get('total_cost_gbp', 0):.4f}, "
        f"steps={len(result.get('processing_steps', []))}"
    )

    return result


async def resume_pipeline(
    thread_id: str,
    from_state: Optional[AgentState] = None,
) -> Optional[AgentState]:
    """Resume a checkpointed pipeline from where it left off.

    Args:
        thread_id: The thread ID used in the original run.
        from_state: Optional updated state to resume from.

    Returns:
        Final AgentState, or None if no checkpoint found.
    """
    if not _checkpointer:
        logger.warning("No checkpointer available — cannot resume")
        return None

    config = {"configurable": {"thread_id": thread_id}}

    try:
        if from_state:
            result = await agent_pipeline.ainvoke(from_state, config=config)
        else:
            result = await agent_pipeline.ainvoke(None, config=config)

        result["pipeline_completed_at"] = datetime.utcnow().isoformat()
        return result
    except Exception as e:
        logger.error(f"Pipeline resume failed for thread {thread_id}: {e}")
        return None
