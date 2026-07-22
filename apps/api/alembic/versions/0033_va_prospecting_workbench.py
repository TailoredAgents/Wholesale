"""VA prospecting scripts, attempts, callbacks, and handoff review.

Revision ID: 0033_va_prospecting_workbench
Revises: 0032_campaign_list_management
Create Date: 2026-07-22 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_va_prospecting_workbench"
down_revision: str | None = "0032_campaign_list_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), nullable=False)


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.add_column(
        "prospect_calling_batch_entries",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prospect_calling_batch_entries",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_prospect_calling_batch_entries_next_attempt_at",
        "prospect_calling_batch_entries",
        ["next_attempt_at"],
    )

    op.create_table(
        "prospecting_script_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("opening_script", sa.Text(), nullable=False),
        sa.Column("qualification_questions", sa.JSON(), nullable=False),
        sa.Column("disposition_rules", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_prospecting_scripts_org_version",
        ),
    )
    op.create_index(
        "ix_prospecting_script_versions_organization_id",
        "prospecting_script_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_prospecting_script_versions_status",
        "prospecting_script_versions",
        ["status"],
    )

    op.create_table(
        "prospecting_attempts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("batch_entry_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("script_version_id", sa.Uuid(), nullable=False),
        sa.Column("call_record_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(80), nullable=True),
        sa.Column("contact_made", sa.Boolean(), nullable=True),
        sa.Column("qualification_answers", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("callback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("required_answer_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("answered_required_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("quality_score_basis_points", sa.Integer(), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["batch_entry_id"], ["prospect_calling_batch_entries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["caller_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["script_version_id"], ["prospecting_script_versions.id"]),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "batch_entry_id",
        "prospect_id",
        "caller_user_id",
        "script_version_id",
        "call_record_id",
        "status",
        "outcome",
    ):
        op.create_index(f"ix_prospecting_attempts_{column}", "prospecting_attempts", [column])
    op.create_index(
        "uq_prospecting_attempts_active_caller",
        "prospecting_attempts",
        ["organization_id", "caller_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )
    op.create_index(
        "uq_prospecting_attempts_active_entry",
        "prospecting_attempts",
        ["batch_entry_id"],
        unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.create_table(
        "prospect_handoffs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(1000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["attempt_id"], ["prospecting_attempts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_prospect_handoffs_attempt"),
    )
    for column in (
        "organization_id",
        "prospect_id",
        "attempt_id",
        "lead_id",
        "assigned_user_id",
        "submitted_by_user_id",
        "status",
    ):
        op.create_index(f"ix_prospect_handoffs_{column}", "prospect_handoffs", [column])


def downgrade() -> None:
    op.drop_table("prospect_handoffs")
    op.drop_table("prospecting_attempts")
    op.drop_table("prospecting_script_versions")
    op.drop_index(
        "ix_prospect_calling_batch_entries_next_attempt_at",
        table_name="prospect_calling_batch_entries",
    )
    op.drop_column("prospect_calling_batch_entries", "completed_at")
    op.drop_column("prospect_calling_batch_entries", "next_attempt_at")
