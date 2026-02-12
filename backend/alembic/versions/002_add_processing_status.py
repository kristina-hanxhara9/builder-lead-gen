"""Add processing_status columns to planning_applications.

Tracks batch processing state: new → processing → processed/failed.

Revision ID: 002
Revises: 001
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add processing columns
    op.add_column(
        "planning_applications",
        sa.Column(
            "processing_status",
            sa.String(20),
            server_default="new",
            nullable=False,
        ),
    )
    op.add_column(
        "planning_applications",
        sa.Column("processing_started_at", sa.DateTime, nullable=True),
    )
    op.add_column(
        "planning_applications",
        sa.Column("processing_error", sa.Text, nullable=True),
    )

    # Index for efficient batch queries
    op.create_index(
        "ix_planning_processing_status",
        "planning_applications",
        ["processing_status"],
    )

    # Backfill: mark existing apps that already have leads as "processed"
    op.execute("""
        UPDATE planning_applications
        SET processing_status = 'processed'
        WHERE id IN (SELECT planning_app_id FROM leads)
    """)


def downgrade() -> None:
    op.drop_index("ix_planning_processing_status", table_name="planning_applications")
    op.drop_column("planning_applications", "processing_error")
    op.drop_column("planning_applications", "processing_started_at")
    op.drop_column("planning_applications", "processing_status")
