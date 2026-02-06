"""SQLAlchemy ORM models for all 8 tables."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


def _uuid():
    return uuid.uuid4()


# --- Enums ---


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUOTED = "quoted"
    WON = "won"
    LOST = "lost"


class LetterStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    QUEUED = "queued"
    PRINTED = "printed"
    POSTED = "posted"
    DELIVERED = "delivered"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


# --- Models ---


class PlanningApplication(Base):
    __tablename__ = "planning_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    reference = Column(String(50), unique=True, nullable=False)
    address = Column(String(500), nullable=False)
    postcode = Column(String(10), nullable=False)
    description = Column(Text)
    application_type = Column(String(100))
    status = Column(String(50))
    submitted_date = Column(DateTime)
    decision = Column(String(50))
    decision_date = Column(DateTime)
    pdf_urls = Column(JSONB, default=list)
    detail_url = Column(String(1000))  # URL to planning portal detail page
    local_authority = Column(String(100))
    applicant_name = Column(String(200))
    raw_data = Column(JSONB, default=dict)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    extracted = relationship("PlanningExtracted", back_populates="planning_app", uselist=False)
    lead = relationship("Lead", back_populates="planning_app", uselist=False)

    __table_args__ = (
        Index("ix_planning_postcode", "postcode"),
        Index("ix_planning_submitted", "submitted_date"),
        Index("ix_planning_reference", "reference"),
    )


class PlanningExtracted(Base):
    __tablename__ = "planning_extracted"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    planning_app_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    property_type = Column(String(50))
    work_description = Column(Text)
    work_category = Column(String(50))
    estimated_cost = Column(Float)
    bedrooms_before = Column(Integer)
    bedrooms_after = Column(Integer)
    floor_area_added_m2 = Column(Float)
    materials = Column(JSONB, default=list)
    property_details = Column(JSONB, default=dict)
    confidence_score = Column(Float, default=0.0)

    created_at = Column(DateTime, server_default=func.now())

    planning_app = relationship("PlanningApplication", back_populates="extracted")


class EPCData(Base):
    __tablename__ = "epc_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    address = Column(String(500), nullable=False)
    postcode = Column(String(10), nullable=False)
    current_rating = Column(String(1))
    potential_rating = Column(String(1))
    current_energy_efficiency = Column(Integer)
    potential_energy_efficiency = Column(Integer)
    property_type = Column(String(100))
    construction_age_band = Column(String(50))
    total_floor_area = Column(Float)
    walls_description = Column(Text)
    roof_description = Column(Text)
    windows_description = Column(Text)
    main_heating_description = Column(Text)
    floor_description = Column(Text)
    inspection_date = Column(DateTime)
    lodgement_date = Column(DateTime)
    raw_data = Column(JSONB, default=dict)

    created_at = Column(DateTime, server_default=func.now())

    leads = relationship("Lead", back_populates="epc")

    __table_args__ = (Index("ix_epc_postcode", "postcode"),)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    planning_app_id = Column(
        UUID(as_uuid=True),
        ForeignKey("planning_applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    epc_id = Column(
        UUID(as_uuid=True),
        ForeignKey("epc_data.id", ondelete="SET NULL"),
        nullable=True,
    )
    address = Column(String(500), nullable=False)
    postcode = Column(String(10), nullable=False)
    work_type = Column(String(50))
    work_description = Column(Text)
    lead_score = Column(Float, default=0.0)
    score_breakdown = Column(JSONB, default=dict)
    status = Column(
        Enum(LeadStatus, values_callable=lambda x: [e.value for e in x]),
        default=LeadStatus.NEW,
    )
    property_value_estimate = Column(Float)
    distance_km = Column(Float)
    unified_data = Column(JSONB, default=dict)
    notes = Column(JSONB, default=list)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    contacted_at = Column(DateTime)
    quoted_at = Column(DateTime)
    won_at = Column(DateTime)

    # Relationships
    planning_app = relationship("PlanningApplication", back_populates="lead")
    epc = relationship("EPCData", back_populates="leads")
    letters = relationship("Letter", back_populates="lead")


class Letter(Base):
    __tablename__ = "letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lead_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(Text)
    pdf_url = Column(String(500))
    pdf_storage_path = Column(String(500))
    status = Column(
        Enum(LetterStatus, values_callable=lambda x: [e.value for e in x]),
        default=LetterStatus.DRAFT,
    )
    stannp_job_id = Column(String(100))

    # Tracking
    qr_code_url = Column(String(500))
    qr_scan_count = Column(Integer, default=0)
    first_scan_at = Column(DateTime)
    phone_call_received = Column(Boolean, default=False)
    quote_requested = Column(Boolean, default=False)

    # Costs
    generation_cost_gbp = Column(Float, default=0.0)
    print_cost_gbp = Column(Float, default=0.0)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    approved_at = Column(DateTime)
    sent_at = Column(DateTime)

    # Relationships
    lead = relationship("Lead", back_populates="letters")
    qr_scans = relationship("QRScan", back_populates="letter")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(
        Enum(UserRole, values_callable=lambda x: [e.value for e in x]),
        default=UserRole.MEMBER,
    )
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    audit_entries = relationship("AuditLog", back_populates="user")


class QRScan(Base):
    __tablename__ = "qr_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    letter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("letters.id", ondelete="CASCADE"),
        nullable=False,
    )
    scanned_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String(45))
    user_agent = Column(Text)
    redirect_url = Column(String(500))

    letter = relationship("Letter", back_populates="qr_scans")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    changes = Column(JSONB, default=dict)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="audit_entries")
