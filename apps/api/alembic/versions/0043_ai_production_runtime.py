"""Phase AI3 production runtime, tools, and monitoring.

Revision ID: 0043_ai_production_runtime
Revises: 0042_ai_evaluation_standards
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_ai_production_runtime"
down_revision: str | None = "0042_ai_evaluation_standards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_knowledge_sources", sa.Column("content_snapshot", sa.Text()))

    op.create_table(
        "ai_runtime_policies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_status", sa.String(40), nullable=False, server_default="disabled"),
        sa.Column("emergency_stop", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("emergency_stop_reason", sa.String(1000)),
        sa.Column("high_volume_model", sa.String(120), nullable=False),
        sa.Column("default_model", sa.String(120), nullable=False),
        sa.Column("escalation_model", sa.String(120), nullable=False),
        sa.Column(
            "max_context_characters", sa.Integer(), nullable=False, server_default="24000"
        ),
        sa.Column(
            "max_requests_per_minute", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.Column(
            "max_daily_cost_microusd",
            sa.BigInteger(),
            nullable=False,
            server_default="10000000",
        ),
        sa.Column(
            "circuit_failure_threshold", sa.Integer(), nullable=False, server_default="3"
        ),
        sa.Column(
            "circuit_cooldown_seconds", sa.Integer(), nullable=False, server_default="300"
        ),
        sa.Column(
            "consecutive_failure_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True)),
        sa.Column(
            "trace_redaction_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "external_actions_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_ai_runtime_policy_org"),
    )
    op.create_index(
        "ix_ai_runtime_policies_organization_id",
        "ai_runtime_policies",
        ["organization_id"],
    )

    op.create_table(
        "ai_capability_runtime_policies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="disabled"),
        sa.Column("model_route", sa.String(40), nullable=False, server_default="default"),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("allowed_tool_keys", sa.JSON(), nullable=False),
        sa.Column("allowed_knowledge_keys", sa.JSON(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column(
            "max_cost_microusd_per_run",
            sa.BigInteger(),
            nullable=False,
            server_default="100000",
        ),
        sa.Column(
            "requires_human_review", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "capability_key",
            name="uq_ai_capability_runtime_org_key",
        ),
    )
    op.create_index(
        "ix_ai_capability_runtime_policies_agent_definition_id",
        "ai_capability_runtime_policies",
        ["agent_definition_id"],
    )
    op.create_index(
        "ix_ai_capability_runtime_policies_organization_id",
        "ai_capability_runtime_policies",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_capability_runtime_org_status",
        "ai_capability_runtime_policies",
        ["organization_id", "status"],
    )

    op.create_table(
        "ai_knowledge_use_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_log_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_source_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("source_version_number", sa.Integer(), nullable=False),
        sa.Column("content_checksum", sa.String(128), nullable=False),
        sa.Column("content_reference", sa.String(1000), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["ai_run_log_id"], ["ai_run_logs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["knowledge_source_id"], ["ai_knowledge_sources.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ai_run_log_id",
            "knowledge_source_id",
            name="uq_ai_knowledge_use_run_source",
        ),
    )
    op.create_index(
        "ix_ai_knowledge_use_logs_ai_run_log_id",
        "ai_knowledge_use_logs",
        ["ai_run_log_id"],
    )
    op.create_index(
        "ix_ai_knowledge_use_logs_knowledge_source_id",
        "ai_knowledge_use_logs",
        ["knowledge_source_id"],
    )
    op.create_index(
        "ix_ai_knowledge_use_logs_organization_id",
        "ai_knowledge_use_logs",
        ["organization_id"],
    )

    op.create_table(
        "ai_evaluation_comparisons",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("challenger_evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("regression_blocked", sa.Boolean(), nullable=False),
        sa.Column("quality_delta_basis_points", sa.Integer(), nullable=False),
        sa.Column("latency_delta_ms", sa.Integer()),
        sa.Column("cost_delta_microusd", sa.BigInteger()),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["ai_evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(
            ["baseline_evaluation_run_id"], ["ai_evaluation_runs.id"]
        ),
        sa.ForeignKeyConstraint(
            ["challenger_evaluation_run_id"], ["ai_evaluation_runs.id"]
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "baseline_evaluation_run_id",
            "challenger_evaluation_run_id",
            name="uq_ai_evaluation_comparison_runs",
        ),
    )
    for column in (
        "organization_id",
        "dataset_id",
        "baseline_evaluation_run_id",
        "challenger_evaluation_run_id",
    ):
        op.create_index(
            f"ix_ai_evaluation_comparisons_{column}",
            "ai_evaluation_comparisons",
            [column],
        )


def downgrade() -> None:
    op.drop_table("ai_evaluation_comparisons")
    op.drop_table("ai_knowledge_use_logs")
    op.drop_table("ai_capability_runtime_policies")
    op.drop_table("ai_runtime_policies")
    op.drop_column("ai_knowledge_sources", "content_snapshot")
