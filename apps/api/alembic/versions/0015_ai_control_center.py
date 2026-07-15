"""ai control center

Revision ID: 0015_ai_control_center
Revises: 0014_marketing_intelligence
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_ai_control_center"
down_revision: str | None = "0014_marketing_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("request_type", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("decision_notes", sa.String(length=2000), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_requests_organization_id",
        "approval_requests",
        ["organization_id"],
    )

    op.create_table(
        "ai_agent_definitions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("risk_level", sa.String(length=80), nullable=False),
        sa.Column("requires_human_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "key", name="uq_ai_agents_org_key"),
    )
    op.create_index(
        "ix_ai_agent_definitions_organization_id", "ai_agent_definitions", ["organization_id"]
    )

    op.create_table(
        "ai_prompt_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("prompt_text", sa.String(length=8000), nullable=False),
        sa.Column("change_notes", sa.String(length=2000), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_definition_id",
            "version_number",
            name="uq_ai_prompt_versions_agent_version",
        ),
    )
    op.create_index(
        "ix_ai_prompt_versions_organization_id", "ai_prompt_versions", ["organization_id"]
    )
    op.create_index(
        "ix_ai_prompt_versions_agent_definition_id",
        "ai_prompt_versions",
        ["agent_definition_id"],
    )

    op.create_table(
        "ai_tool_permissions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("tool_key", sa.String(length=160), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("permission_level", sa.String(length=80), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_definition_id",
            "tool_key",
            name="uq_ai_tool_permissions_agent_tool",
        ),
    )
    op.create_index(
        "ix_ai_tool_permissions_organization_id", "ai_tool_permissions", ["organization_id"]
    )
    op.create_index(
        "ix_ai_tool_permissions_agent_definition_id",
        "ai_tool_permissions",
        ["agent_definition_id"],
    )

    op.create_table(
        "ai_run_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("input_summary", sa.String(length=4000), nullable=False),
        sa.Column("output_summary", sa.String(length=4000), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["ai_prompt_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_run_logs_organization_id", "ai_run_logs", ["organization_id"])
    op.create_index("ix_ai_run_logs_agent_definition_id", "ai_run_logs", ["agent_definition_id"])
    op.create_index("ix_ai_run_logs_prompt_version_id", "ai_run_logs", ["prompt_version_id"])
    op.create_index("ix_ai_run_logs_lead_id", "ai_run_logs", ["lead_id"])

    op.create_table(
        "ai_tool_call_logs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_log_id", sa.Uuid(), nullable=False),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("tool_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["ai_run_log_id"], ["ai_run_logs.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_tool_call_logs_organization_id", "ai_tool_call_logs", ["organization_id"]
    )
    op.create_index("ix_ai_tool_call_logs_ai_run_log_id", "ai_tool_call_logs", ["ai_run_log_id"])
    op.create_index(
        "ix_ai_tool_call_logs_approval_request_id",
        "ai_tool_call_logs",
        ["approval_request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_tool_call_logs_approval_request_id", table_name="ai_tool_call_logs")
    op.drop_index("ix_ai_tool_call_logs_ai_run_log_id", table_name="ai_tool_call_logs")
    op.drop_index("ix_ai_tool_call_logs_organization_id", table_name="ai_tool_call_logs")
    op.drop_table("ai_tool_call_logs")
    op.drop_index("ix_ai_run_logs_lead_id", table_name="ai_run_logs")
    op.drop_index("ix_ai_run_logs_prompt_version_id", table_name="ai_run_logs")
    op.drop_index("ix_ai_run_logs_agent_definition_id", table_name="ai_run_logs")
    op.drop_index("ix_ai_run_logs_organization_id", table_name="ai_run_logs")
    op.drop_table("ai_run_logs")
    op.drop_index("ix_ai_tool_permissions_agent_definition_id", table_name="ai_tool_permissions")
    op.drop_index("ix_ai_tool_permissions_organization_id", table_name="ai_tool_permissions")
    op.drop_table("ai_tool_permissions")
    op.drop_index("ix_ai_prompt_versions_agent_definition_id", table_name="ai_prompt_versions")
    op.drop_index("ix_ai_prompt_versions_organization_id", table_name="ai_prompt_versions")
    op.drop_table("ai_prompt_versions")
    op.drop_index("ix_ai_agent_definitions_organization_id", table_name="ai_agent_definitions")
    op.drop_table("ai_agent_definitions")
    op.drop_index("ix_approval_requests_organization_id", table_name="approval_requests")
    op.drop_table("approval_requests")
