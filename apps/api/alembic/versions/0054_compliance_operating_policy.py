"""Phase F3 compliance and operating policy.

Revision ID: 0054_compliance_policy
Revises: 0053_company_config
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0054_compliance_policy"
down_revision: str | None = "0053_company_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_policy_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("policy_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scope_state_code", sa.String(2), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("policy_config", sa.JSON(), nullable=False),
        sa.Column("legal_review_status", sa.String(40), nullable=False),
        sa.Column("legal_reviewer_name", sa.String(255)),
        sa.Column("legal_reviewer_company", sa.String(255)),
        sa.Column("legal_evidence_reference", sa.String(1000)),
        sa.Column("legal_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("review_due_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "policy_key",
            "version_number",
            name="uq_compliance_policy_version",
        ),
    )
    op.create_index(
        "ix_compliance_policy_versions_organization_id",
        "compliance_policy_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_compliance_policy_versions_policy_key",
        "compliance_policy_versions",
        ["policy_key"],
    )
    op.create_index(
        "ix_compliance_policy_versions_scope_state_code",
        "compliance_policy_versions",
        ["scope_state_code"],
    )
    op.create_index(
        "ix_compliance_policy_versions_status",
        "compliance_policy_versions",
        ["status"],
    )
    op.create_index(
        "ix_compliance_policy_versions_review_due_at",
        "compliance_policy_versions",
        ["review_due_at"],
    )

    op.create_table(
        "dnc_screening_sources",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("account_reference", sa.String(255)),
        sa.Column("coverage_area_codes", sa.JSON(), nullable=False),
        sa.Column("refresh_interval_days", sa.Integer(), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("next_refresh_due_at", sa.DateTime(timezone=True)),
        sa.Column("latest_evidence_reference", sa.String(1000)),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            name="uq_dnc_screening_sources_org_name",
        ),
    )
    for column in (
        "organization_id",
        "status",
        "last_refreshed_at",
        "next_refresh_due_at",
    ):
        op.create_index(
            f"ix_dnc_screening_sources_{column}",
            "dnc_screening_sources",
            [column],
        )

    op.create_table(
        "compliance_training_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("training_key", sa.String(160), nullable=False),
        sa.Column("training_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("score_basis_points", sa.Integer()),
        sa.Column("completion_evidence", sa.String(2000)),
        sa.Column("employee_attestation", sa.String(2000)),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("manager_notes", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "training_key",
            "training_version",
            name="uq_compliance_training_assignment",
        ),
    )
    for column in ("organization_id", "user_id", "training_key", "status"):
        op.create_index(
            f"ix_compliance_training_records_{column}",
            "compliance_training_records",
            [column],
        )

    op.create_table(
        "compliance_incidents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid()),
        sa.Column("lead_id", sa.Uuid()),
        sa.Column("prospect_id", sa.Uuid()),
        sa.Column("call_record_id", sa.Uuid()),
        sa.Column("incident_type", sa.String(120), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", sa.String(4000)),
        sa.Column("reported_by_user_id", sa.Uuid()),
        sa.Column("assigned_to_user_id", sa.Uuid()),
        sa.Column("resolved_by_user_id", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"]),
        sa.ForeignKeyConstraint(["reported_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "contact_id",
        "lead_id",
        "prospect_id",
        "call_record_id",
        "incident_type",
        "channel",
        "severity",
        "status",
    ):
        op.create_index(
            f"ix_compliance_incidents_{column}",
            "compliance_incidents",
            [column],
        )

    op.create_table(
        "compliance_control_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["run_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_control_runs_organization_id",
        "compliance_control_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_compliance_control_runs_status",
        "compliance_control_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_control_runs_status", table_name="compliance_control_runs")
    op.drop_index(
        "ix_compliance_control_runs_organization_id",
        table_name="compliance_control_runs",
    )
    op.drop_table("compliance_control_runs")
    for column in reversed(
        (
            "organization_id",
            "contact_id",
            "lead_id",
            "prospect_id",
            "call_record_id",
            "incident_type",
            "channel",
            "severity",
            "status",
        )
    ):
        op.drop_index(f"ix_compliance_incidents_{column}", table_name="compliance_incidents")
    op.drop_table("compliance_incidents")
    for column in reversed(("organization_id", "user_id", "training_key", "status")):
        op.drop_index(
            f"ix_compliance_training_records_{column}",
            table_name="compliance_training_records",
        )
    op.drop_table("compliance_training_records")
    for column in reversed(
        ("organization_id", "status", "last_refreshed_at", "next_refresh_due_at")
    ):
        op.drop_index(
            f"ix_dnc_screening_sources_{column}",
            table_name="dnc_screening_sources",
        )
    op.drop_table("dnc_screening_sources")
    for column in reversed(
        (
            "organization_id",
            "policy_key",
            "scope_state_code",
            "status",
            "review_due_at",
        )
    ):
        op.drop_index(
            f"ix_compliance_policy_versions_{column}",
            table_name="compliance_policy_versions",
        )
    op.drop_table("compliance_policy_versions")
