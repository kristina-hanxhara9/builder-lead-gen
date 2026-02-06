"""LangChain agent pipeline for lead generation.

Architecture:
- 5 agents wired as a LangGraph StateGraph
- Each agent (except data_combiner) uses LangChain tool-calling with Gemini
- Tools are defined in the tools/ subdirectory
- SQLite checkpointing enables fault-tolerant pipeline execution

Pipeline: extract_pdf → enrich_epc → combine_data → score_lead → generate_letter
"""

from app.agents.agent_graph import run_pipeline, resume_pipeline

__all__ = ["run_pipeline", "resume_pipeline"]
