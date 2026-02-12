"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# --- Planning Applications ---


class PlanningAppBase(BaseModel):
    reference: str
    address: str
    postcode: str
    description: Optional[str] = None
    application_type: Optional[str] = None
    status: Optional[str] = None
    submitted_date: Optional[datetime] = None
    decision: Optional[str] = None
    decision_date: Optional[datetime] = None
    pdf_urls: list[str] = Field(default_factory=list)
    detail_url: Optional[str] = None
    local_authority: Optional[str] = None
    applicant_name: Optional[str] = None


class PlanningAppCreate(PlanningAppBase):
    pass


class PlanningAppResponse(PlanningAppBase):
    id: UUID
    processing_status: Optional[str] = "new"
    created_at: datetime

    class Config:
        from_attributes = True


# --- Leads ---


class LeadBase(BaseModel):
    address: str
    postcode: str
    work_type: Optional[str] = None
    work_description: Optional[str] = None
    lead_score: float = 0.0
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    status: str = "new"
    property_value_estimate: Optional[float] = None
    distance_km: Optional[float] = None


class LeadResponse(LeadBase):
    id: UUID
    planning_app_id: UUID
    epc_id: Optional[UUID] = None
    unified_data: dict[str, Any] = Field(default_factory=dict)
    notes: list[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    contacted_at: Optional[datetime] = None
    quoted_at: Optional[datetime] = None
    won_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = None


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    total: int
    page: int
    per_page: int


# --- Letters ---


class LetterBase(BaseModel):
    content: Optional[str] = None
    status: str = "draft"


class LetterResponse(LetterBase):
    id: UUID
    lead_id: UUID
    pdf_url: Optional[str] = None
    stannp_job_id: Optional[str] = None
    qr_code_url: Optional[str] = None
    qr_scan_count: int = 0
    first_scan_at: Optional[datetime] = None
    phone_call_received: bool = False
    quote_requested: bool = False
    generation_cost_gbp: float = 0.0
    print_cost_gbp: float = 0.0
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LetterListResponse(BaseModel):
    letters: list[LetterResponse]
    total: int


# --- Dashboard ---


class DashboardStats(BaseModel):
    new_leads_today: int = 0
    total_leads: int = 0
    letters_pending: int = 0
    letters_sent: int = 0
    qr_scans_total: int = 0
    conversion_rate: float = 0.0
    pipeline_value: float = 0.0
    avg_lead_score: float = 0.0


class PipelineStage(BaseModel):
    stage: str
    count: int
    value: float = 0.0


class PipelineResponse(BaseModel):
    stages: list[PipelineStage]


# --- Auth ---


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- QR Scans ---


class QRScanResponse(BaseModel):
    id: UUID
    letter_id: UUID
    scanned_at: datetime
    redirect_url: Optional[str] = None

    class Config:
        from_attributes = True
