"""Persist address-only website leads until contact intake is completed.

Revision ID: 0102_address_only_website_leads
Revises: 0101_meta_click_capture_time
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0102_address_only_website_leads"
down_revision: str | None = "0101_meta_click_capture_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead_form_submissions",
        sa.Column("intake_attempt_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "lead_form_submissions",
        sa.Column(
            "completion_status",
            sa.String(length=40),
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "lead_form_submissions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE lead_form_submissions "
            "SET completed_at = created_at "
            "WHERE completed_at IS NULL"
        )
    )
    op.create_index(
        "ix_lead_form_submissions_org_completion_created",
        "lead_form_submissions",
        ["organization_id", "completion_status", "created_at"],
    )
    op.create_unique_constraint(
        "uq_lead_form_submissions_org_intake_attempt",
        "lead_form_submissions",
        ["organization_id", "intake_attempt_id"],
    )
    op.create_check_constraint(
        "ck_lead_form_submissions_completion_state",
        "lead_form_submissions",
        "(completion_status = 'address_only' AND intake_attempt_id IS NOT NULL "
        "AND completed_at IS NULL) OR "
        "completion_status = 'completed'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_lead_form_submissions_completion_state",
        "lead_form_submissions",
        type_="check",
    )
    op.drop_constraint(
        "uq_lead_form_submissions_org_intake_attempt",
        "lead_form_submissions",
        type_="unique",
    )
    op.drop_index(
        "ix_lead_form_submissions_org_completion_created",
        table_name="lead_form_submissions",
    )
    op.drop_column("lead_form_submissions", "completed_at")
    op.drop_column("lead_form_submissions", "completion_status")
    op.drop_column("lead_form_submissions", "intake_attempt_id")
