"""Phase 10 governed AI orchestrator and evaluation harness.

Revision ID: 0040_ai_orchestrator
Revises: 0039_dispositions_reconciliation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0040_ai_orchestrator"
down_revision: str | None = "0039_dispositions_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.add_column(
        "ai_agent_definitions",
        sa.Column("autonomy_level", sa.String(40), server_default="observe", nullable=False),
    )
    op.add_column(
        "ai_agent_definitions",
        sa.Column(
            "max_cost_microusd_per_run",
            sa.BigInteger(),
            server_default="100000",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_agent_definitions",
        sa.Column(
            "max_daily_cost_microusd",
            sa.BigInteger(),
            server_default="1000000",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_agent_definitions",
        sa.Column("max_attempts", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column(
        "ai_agent_definitions",
        sa.Column("rollback_owner_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_agents_rollback_owner",
        "ai_agent_definitions",
        "users",
        ["rollback_owner_user_id"],
        ["id"],
    )

    op.create_table(
        "ai_orchestrator_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(120), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_ai_events_org_key"),
    )
    op.create_index(
        "ix_ai_events_org_status", "ai_orchestrator_events", ["organization_id", "status"]
    )

    op.add_column("ai_run_logs", sa.Column("orchestrator_event_id", sa.Uuid(), nullable=True))
    op.add_column("ai_run_logs", sa.Column("parent_run_id", sa.Uuid(), nullable=True))
    op.add_column("ai_run_logs", sa.Column("requested_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ai_run_logs",
        sa.Column("execution_mode", sa.String(40), server_default="manual", nullable=False),
    )
    op.add_column(
        "ai_run_logs",
        sa.Column("capability_key", sa.String(160), server_default="manual", nullable=False),
    )
    op.add_column(
        "ai_run_logs",
        sa.Column("attempt_number", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("ai_run_logs", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.add_column("ai_run_logs", sa.Column("budget_limit_microusd", sa.BigInteger(), nullable=True))
    op.add_column(
        "ai_run_logs",
        sa.Column("budget_status", sa.String(40), server_default="within_budget", nullable=False),
    )
    op.add_column(
        "ai_run_logs",
        sa.Column("trace_status", sa.String(40), server_default="unreviewed", nullable=False),
    )
    op.add_column("ai_run_logs", sa.Column("trace_reviewed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ai_run_logs", sa.Column("trace_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("ai_run_logs", sa.Column("trace_review_notes", sa.String(2000), nullable=True))
    op.add_column(
        "ai_run_logs",
        sa.Column("rollback_status", sa.String(40), server_default="not_required", nullable=False),
    )
    op.create_foreign_key(
        "fk_ai_runs_orchestrator_event",
        "ai_run_logs",
        "ai_orchestrator_events",
        ["orchestrator_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_ai_runs_parent",
        "ai_run_logs",
        "ai_run_logs",
        ["parent_run_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_ai_runs_requested_by",
        "ai_run_logs",
        "users",
        ["requested_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_ai_runs_trace_reviewer",
        "ai_run_logs",
        "users",
        ["trace_reviewed_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_ai_runs_org_idempotency",
        "ai_run_logs",
        ["organization_id", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "ai_evaluation_datasets",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("minimum_case_count", sa.Integer(), nullable=False),
        sa.Column("minimum_pass_rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("maximum_critical_failures", sa.Integer(), nullable=False),
        sa.Column("maximum_average_latency_ms", sa.Integer(), nullable=True),
        sa.Column("maximum_average_cost_microusd", sa.BigInteger(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "agent_definition_id",
            "capability_key",
            "version_number",
            name="uq_ai_eval_dataset_version",
        ),
    )
    op.create_index("ix_ai_eval_datasets_org", "ai_evaluation_datasets", ["organization_id"])

    op.create_table(
        "ai_evaluation_cases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("case_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("expected_output", sa.JSON(), nullable=False),
        sa.Column("candidate_output", sa.JSON(), nullable=True),
        sa.Column("deterministic_checks", sa.JSON(), nullable=False),
        sa.Column("risk_tags", sa.JSON(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["ai_evaluation_datasets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dataset_id", "case_key", name="uq_ai_eval_case_key"),
    )

    op.create_table(
        "ai_evaluation_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("execution_mode", sa.String(40), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_case_count", sa.Integer(), nullable=False),
        sa.Column("pass_rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("critical_failure_count", sa.Integer(), nullable=False),
        sa.Column("average_latency_ms", sa.Integer(), nullable=True),
        sa.Column("average_cost_microusd", sa.BigInteger(), nullable=True),
        sa.Column("total_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("thresholds_passed", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["ai_evaluation_datasets.id"]),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["ai_prompt_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )

    op.create_table(
        "ai_evaluation_results",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("critical_failure", sa.Boolean(), nullable=False),
        sa.Column("actual_output", sa.JSON(), nullable=True),
        sa.Column("check_results", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["ai_evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["evaluation_case_id"], ["ai_evaluation_cases.id"]),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "evaluation_case_id",
            name="uq_ai_eval_result_case",
        ),
    )

    op.create_table(
        "ai_capability_promotions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(160), nullable=False),
        sa.Column("evaluation_run_id", sa.Uuid(), nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("from_level", sa.String(40), nullable=False),
        sa.Column("to_level", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("decision_notes", sa.String(2000), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.String(2000), nullable=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["ai_evaluation_runs.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_ai_promotions_org_status",
        "ai_capability_promotions",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("ai_capability_promotions")
    op.drop_table("ai_evaluation_results")
    op.drop_table("ai_evaluation_runs")
    op.drop_table("ai_evaluation_cases")
    op.drop_table("ai_evaluation_datasets")
    op.drop_index("ix_ai_runs_org_idempotency", table_name="ai_run_logs")
    op.drop_constraint("fk_ai_runs_trace_reviewer", "ai_run_logs", type_="foreignkey")
    op.drop_constraint("fk_ai_runs_requested_by", "ai_run_logs", type_="foreignkey")
    op.drop_constraint("fk_ai_runs_parent", "ai_run_logs", type_="foreignkey")
    op.drop_constraint("fk_ai_runs_orchestrator_event", "ai_run_logs", type_="foreignkey")
    for column in (
        "rollback_status",
        "trace_review_notes",
        "trace_reviewed_at",
        "trace_reviewed_by_user_id",
        "trace_status",
        "budget_status",
        "budget_limit_microusd",
        "idempotency_key",
        "attempt_number",
        "capability_key",
        "execution_mode",
        "requested_by_user_id",
        "parent_run_id",
        "orchestrator_event_id",
    ):
        op.drop_column("ai_run_logs", column)
    op.drop_table("ai_orchestrator_events")
    op.drop_constraint("fk_ai_agents_rollback_owner", "ai_agent_definitions", type_="foreignkey")
    for column in (
        "rollback_owner_user_id",
        "max_attempts",
        "max_daily_cost_microusd",
        "max_cost_microusd_per_run",
        "autonomy_level",
    ):
        op.drop_column("ai_agent_definitions", column)
