"""Initial schema with all 8 tables.

Revision ID: 001
Create Date: 2026-02-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # planning_applications
    op.create_table(
        "planning_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(50), unique=True, nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("postcode", sa.String(10), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("application_type", sa.String(100)),
        sa.Column("status", sa.String(50)),
        sa.Column("submitted_date", sa.DateTime),
        sa.Column("decision", sa.String(50)),
        sa.Column("decision_date", sa.DateTime),
        sa.Column("pdf_urls", postgresql.JSONB, server_default="[]"),
        sa.Column("local_authority", sa.String(100)),
        sa.Column("applicant_name", sa.String(200)),
        sa.Column("raw_data", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_planning_postcode", "planning_applications", ["postcode"])
    op.create_index("ix_planning_submitted", "planning_applications", ["submitted_date"])
    op.create_index("ix_planning_reference", "planning_applications", ["reference"])

    # planning_extracted
    op.create_table(
        "planning_extracted",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "planning_app_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("planning_applications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("property_type", sa.String(50)),
        sa.Column("work_description", sa.Text),
        sa.Column("work_category", sa.String(50)),
        sa.Column("estimated_cost", sa.Float),
        sa.Column("bedrooms_before", sa.Integer),
        sa.Column("bedrooms_after", sa.Integer),
        sa.Column("floor_area_added_m2", sa.Float),
        sa.Column("materials", postgresql.JSONB, server_default="[]"),
        sa.Column("property_details", postgresql.JSONB, server_default="{}"),
        sa.Column("confidence_score", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # epc_data
    op.create_table(
        "epc_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("postcode", sa.String(10), nullable=False),
        sa.Column("current_rating", sa.String(1)),
        sa.Column("potential_rating", sa.String(1)),
        sa.Column("current_energy_efficiency", sa.Integer),
        sa.Column("potential_energy_efficiency", sa.Integer),
        sa.Column("property_type", sa.String(100)),
        sa.Column("construction_age_band", sa.String(50)),
        sa.Column("total_floor_area", sa.Float),
        sa.Column("walls_description", sa.Text),
        sa.Column("roof_description", sa.Text),
        sa.Column("windows_description", sa.Text),
        sa.Column("main_heating_description", sa.Text),
        sa.Column("floor_description", sa.Text),
        sa.Column("inspection_date", sa.DateTime),
        sa.Column("lodgement_date", sa.DateTime),
        sa.Column("raw_data", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_epc_postcode", "epc_data", ["postcode"])

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(200), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "member", name="userrole"),
            server_default="member",
        ),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_login", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # leads
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "planning_app_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("planning_applications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "epc_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("epc_data.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("postcode", sa.String(10), nullable=False),
        sa.Column("work_type", sa.String(50)),
        sa.Column("work_description", sa.Text),
        sa.Column("lead_score", sa.Float, server_default="0.0"),
        sa.Column("score_breakdown", postgresql.JSONB, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("new", "contacted", "quoted", "won", "lost", name="leadstatus"),
            server_default="new",
        ),
        sa.Column("property_value_estimate", sa.Float),
        sa.Column("distance_km", sa.Float),
        sa.Column("unified_data", postgresql.JSONB, server_default="{}"),
        sa.Column("notes", postgresql.JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("contacted_at", sa.DateTime),
        sa.Column("quoted_at", sa.DateTime),
        sa.Column("won_at", sa.DateTime),
    )

    # letters
    op.create_table(
        "letters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text),
        sa.Column("pdf_url", sa.String(500)),
        sa.Column("pdf_storage_path", sa.String(500)),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "approved", "queued", "printed", "posted", "delivered",
                name="letterstatus",
            ),
            server_default="draft",
        ),
        sa.Column("stannp_job_id", sa.String(100)),
        sa.Column("qr_code_url", sa.String(500)),
        sa.Column("qr_scan_count", sa.Integer, server_default="0"),
        sa.Column("first_scan_at", sa.DateTime),
        sa.Column("phone_call_received", sa.Boolean, server_default="false"),
        sa.Column("quote_requested", sa.Boolean, server_default="false"),
        sa.Column("generation_cost_gbp", sa.Float, server_default="0.0"),
        sa.Column("print_cost_gbp", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("sent_at", sa.DateTime),
    )

    # qr_scans
    op.create_table(
        "qr_scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "letter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("letters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scanned_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("redirect_url", sa.String(500)),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("changes", postgresql.JSONB, server_default="{}"),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("qr_scans")
    op.drop_table("letters")
    op.drop_table("leads")
    op.drop_table("users")
    op.drop_table("epc_data")
    op.drop_table("planning_extracted")
    op.drop_table("planning_applications")
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS leadstatus")
    op.execute("DROP TYPE IF EXISTS letterstatus")
