"""Agent workflow state definition — comprehensive TypedDict for the full pipeline.

Uses Annotated types with operator.add for append-only lists so every
agent can push errors / log entries without overwriting previous ones.
"""

import operator
from typing import Annotated, Any, Optional, TypedDict


class PlanningAppInput(TypedDict, total=False):
    """Raw planning application data fed into the pipeline."""

    id: str
    reference: str
    address: str
    postcode: str
    description: str
    application_type: str
    decision: str
    decision_date: Optional[str]
    submitted_date: Optional[str]
    local_authority: str
    applicant_name: Optional[str]
    agent_name: Optional[str]
    pdf_urls: list[str]
    detail_url: Optional[str]
    ward: Optional[str]


class ExtractionResult(TypedDict, total=False):
    """Structured data pulled from planning PDFs by Gemini."""

    property_type: Optional[str]
    work_description: Optional[str]
    work_category: Optional[str]
    estimated_cost: Optional[float]
    bedrooms_before: Optional[int]
    bedrooms_after: Optional[int]
    floor_area_added_m2: Optional[float]
    materials: list[str]
    planning_reference: Optional[str]
    applicant_name: Optional[str]
    architect_name: Optional[str]
    contractor_name: Optional[str]
    num_storeys: Optional[int]
    conservation_area: Optional[bool]
    listed_building: Optional[bool]
    tree_preservation: Optional[bool]


class EPCResult(TypedDict, total=False):
    """Energy Performance Certificate data from the EPC API."""

    address: str
    postcode: str
    current_rating: str
    potential_rating: str
    current_energy_efficiency: Optional[int]
    potential_energy_efficiency: Optional[int]
    property_type: str
    construction_age_band: str
    total_floor_area: Optional[float]
    walls_description: str
    roof_description: str
    windows_description: str
    main_heating_description: str
    floor_description: str
    inspection_date: Optional[str]
    lodgement_date: Optional[str]
    match_confidence: Optional[float]


class UnifiedData(TypedDict, total=False):
    """Merged data from all sources with derived fields."""

    # Address
    address: str
    postcode: str
    district: str
    local_authority: str

    # Planning
    planning_reference: str
    planning_status: str
    submitted_date: Optional[str]
    decision_date: Optional[str]
    application_type: str
    applicant_name: Optional[str]

    # Property details
    property_type: str
    construction_age: Optional[str]
    total_floor_area_m2: Optional[float]
    epc_rating: Optional[str]
    epc_potential_rating: Optional[str]
    epc_efficiency: Optional[int]

    # Work details
    work_description: str
    work_category: Optional[str]
    work_type_standardized: Optional[str]
    estimated_cost: Optional[float]
    floor_area_added_m2: Optional[float]
    materials: list[str]
    bedrooms_before: Optional[int]
    bedrooms_after: Optional[int]
    num_storeys: Optional[int]

    # Building fabric (from EPC)
    walls: Optional[str]
    roof: Optional[str]
    windows: Optional[str]
    heating: Optional[str]

    # Constraints
    conservation_area: Optional[bool]
    listed_building: Optional[bool]

    # Derived
    property_value_estimate: float
    distance_from_office_km: float
    in_target_area: bool
    in_adjacent_area: bool

    # Data quality
    data_sources: list[str]
    conflict_resolutions: list[str]


class ScoreBreakdown(TypedDict, total=False):
    """Detailed breakdown of lead score factors."""

    geography: dict[str, Any]
    property_value: dict[str, Any]
    work_type: dict[str, Any]
    timing: dict[str, Any]
    total: float
    reasoning: str
    adjustments: list[str]


class LetterOutput(TypedDict, total=False):
    """Generated letter content and PDF."""

    content: str
    pdf_bytes: bytes
    qr_url: str
    case_studies_used: list[str]
    word_count: int
    tone: str
    personalisation_score: float


class AgentState(TypedDict, total=False):
    """Full pipeline state — every agent reads/writes to this.

    Annotated lists use operator.add so multiple agents can append
    to errors / agent_logs / processing_steps without clobbering.
    """

    # ── Inputs ──────────────────────────────────────────────────
    planning_app_id: str
    planning_app_data: PlanningAppInput

    # ── Agent 1: PDF Extraction ─────────────────────────────────
    extracted_data: Optional[ExtractionResult]
    extraction_confidence: float
    pdfs_attempted: int
    pdfs_succeeded: int
    extraction_model_used: str

    # ── Agent 2: EPC Enrichment ─────────────────────────────────
    epc_data: Optional[EPCResult]
    epc_match_confidence: float
    epc_source: str  # "api", "cache", "none"

    # ── Agent 3: Data Combination ───────────────────────────────
    unified_data: UnifiedData

    # ── Agent 4: Lead Scoring ───────────────────────────────────
    lead_score: float
    score_breakdown: ScoreBreakdown
    should_generate_letter: bool
    auto_approve_letter: bool
    scoring_reasoning: str

    # ── Agent 5: Letter Generation ──────────────────────────────
    letter_output: Optional[LetterOutput]
    letter_content: Optional[str]
    letter_pdf_bytes: Optional[bytes]
    qr_url: Optional[str]

    # ── Metadata ────────────────────────────────────────────────
    errors: Annotated[list[str], operator.add]
    agent_logs: Annotated[list[str], operator.add]
    processing_steps: Annotated[list[dict[str, Any]], operator.add]
    total_cost_gbp: float
    pipeline_started_at: Optional[str]
    pipeline_completed_at: Optional[str]
    current_agent: str
