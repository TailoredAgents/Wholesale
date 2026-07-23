"""Phase AI1 role copilots and data governance.

Revision ID: 0041_ai_copilot_governance
Revises: 0040_ai_orchestrator
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041_ai_copilot_governance"
down_revision: str | None = "0040_ai_orchestrator"
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


def approval_columns() -> tuple[sa.Column[object], ...]:
    return (
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )


def approval_foreign_keys() -> tuple[sa.ForeignKeyConstraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
    )


def upgrade() -> None:
    op.create_table(
        "ai_copilot_definitions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1200), nullable=False),
        sa.Column("human_owner_role_key", sa.String(120), nullable=False),
        sa.Column("human_owner_title", sa.String(255), nullable=False),
        sa.Column("human_authority_summary", sa.String(1200), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("phase_key", sa.String(40), nullable=False),
        *approval_columns(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        *approval_foreign_keys(),
        sa.UniqueConstraint("organization_id", "key", name="uq_ai_copilots_org_key"),
    )
    op.create_index(
        "ix_ai_copilots_org_status",
        "ai_copilot_definitions",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_copilot_definitions_organization_id",
        "ai_copilot_definitions",
        ["organization_id"],
    )

    op.create_table(
        "ai_copilot_agent_mappings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("copilot_definition_id", sa.Uuid(), nullable=False),
        sa.Column("agent_definition_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(800), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["copilot_definition_id"],
            ["ai_copilot_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["agent_definition_id"], ["ai_agent_definitions.id"]),
        sa.UniqueConstraint(
            "copilot_definition_id",
            "agent_definition_id",
            name="uq_ai_copilot_agent_mapping",
        ),
    )
    op.create_index(
        "ix_ai_copilot_agent_mappings_organization_id",
        "ai_copilot_agent_mappings",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_copilot_agent_mappings_copilot_definition_id",
        "ai_copilot_agent_mappings",
        ["copilot_definition_id"],
    )
    op.create_index(
        "ix_ai_copilot_agent_mappings_agent_definition_id",
        "ai_copilot_agent_mappings",
        ["agent_definition_id"],
    )

    op.create_table(
        "ai_capability_contracts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("copilot_definition_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("owner_role_key", sa.String(120), nullable=False),
        sa.Column("trigger_events", sa.JSON(), nullable=False),
        sa.Column("input_requirements", sa.JSON(), nullable=False),
        sa.Column("output_requirements", sa.JSON(), nullable=False),
        sa.Column("allowed_tool_scopes", sa.JSON(), nullable=False),
        sa.Column("evidence_requirements", sa.JSON(), nullable=False),
        sa.Column("approval_policy", sa.JSON(), nullable=False),
        sa.Column("escalation_policy", sa.JSON(), nullable=False),
        sa.Column("prohibited_actions", sa.JSON(), nullable=False),
        *approval_columns(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["copilot_definition_id"],
            ["ai_copilot_definitions.id"],
            ondelete="CASCADE",
        ),
        *approval_foreign_keys(),
        sa.UniqueConstraint(
            "copilot_definition_id",
            "capability_key",
            "version_number",
            name="uq_ai_capability_contract_version",
        ),
    )
    op.create_index(
        "ix_ai_capability_contracts_org_status",
        "ai_capability_contracts",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_capability_contracts_organization_id",
        "ai_capability_contracts",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_capability_contracts_copilot_definition_id",
        "ai_capability_contracts",
        ["copilot_definition_id"],
    )

    op.create_table(
        "ai_data_governance_policies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("data_category", sa.String(120), nullable=False),
        sa.Column("field_scope", sa.JSON(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_precedence", sa.JSON(), nullable=False),
        sa.Column("overwrite_policy", sa.String(1600), nullable=False),
        sa.Column("redaction_rule", sa.String(1600), nullable=False),
        sa.Column("retention_rule", sa.String(1600), nullable=False),
        sa.Column("permitted_role_keys", sa.JSON(), nullable=False),
        *approval_columns(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        *approval_foreign_keys(),
        sa.UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_data_governance_policy_version",
        ),
    )
    op.create_index(
        "ix_ai_data_governance_org_status",
        "ai_data_governance_policies",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_data_governance_policies_organization_id",
        "ai_data_governance_policies",
        ["organization_id"],
    )

    op.create_table(
        "ai_knowledge_sources",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("content_reference", sa.String(1000), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("owner_role_key", sa.String(120), nullable=False),
        sa.Column("audience_role_keys", sa.JSON(), nullable=False),
        sa.Column("is_authoritative", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_checksum", sa.String(128), nullable=True),
        *approval_columns(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        *approval_foreign_keys(),
        sa.UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_knowledge_source_version",
        ),
    )
    op.create_index(
        "ix_ai_knowledge_sources_org_status",
        "ai_knowledge_sources",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_knowledge_sources_organization_id",
        "ai_knowledge_sources",
        ["organization_id"],
    )

    op.create_table(
        "ai_data_quality_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("record_type", sa.String(120), nullable=False),
        sa.Column("field_scope", sa.JSON(), nullable=False),
        sa.Column("rule_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(40), nullable=False),
        sa.Column("is_deterministic", sa.Boolean(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("resolution_action", sa.String(1000), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        *approval_columns(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        *approval_foreign_keys(),
        sa.UniqueConstraint(
            "organization_id",
            "key",
            "version_number",
            name="uq_ai_data_quality_rule_version",
        ),
    )
    op.create_index(
        "ix_ai_data_quality_rules_org_status",
        "ai_data_quality_rules",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_data_quality_rules_organization_id",
        "ai_data_quality_rules",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_data_quality_rules_organization_id",
        table_name="ai_data_quality_rules",
    )
    op.drop_index("ix_ai_data_quality_rules_org_status", table_name="ai_data_quality_rules")
    op.drop_table("ai_data_quality_rules")
    op.drop_index(
        "ix_ai_knowledge_sources_organization_id",
        table_name="ai_knowledge_sources",
    )
    op.drop_index("ix_ai_knowledge_sources_org_status", table_name="ai_knowledge_sources")
    op.drop_table("ai_knowledge_sources")
    op.drop_index(
        "ix_ai_data_governance_policies_organization_id",
        table_name="ai_data_governance_policies",
    )
    op.drop_index("ix_ai_data_governance_org_status", table_name="ai_data_governance_policies")
    op.drop_table("ai_data_governance_policies")
    op.drop_index(
        "ix_ai_capability_contracts_copilot_definition_id",
        table_name="ai_capability_contracts",
    )
    op.drop_index(
        "ix_ai_capability_contracts_organization_id",
        table_name="ai_capability_contracts",
    )
    op.drop_index("ix_ai_capability_contracts_org_status", table_name="ai_capability_contracts")
    op.drop_table("ai_capability_contracts")
    op.drop_index(
        "ix_ai_copilot_agent_mappings_agent_definition_id",
        table_name="ai_copilot_agent_mappings",
    )
    op.drop_index(
        "ix_ai_copilot_agent_mappings_copilot_definition_id",
        table_name="ai_copilot_agent_mappings",
    )
    op.drop_index(
        "ix_ai_copilot_agent_mappings_organization_id",
        table_name="ai_copilot_agent_mappings",
    )
    op.drop_table("ai_copilot_agent_mappings")
    op.drop_index(
        "ix_ai_copilot_definitions_organization_id",
        table_name="ai_copilot_definitions",
    )
    op.drop_index("ix_ai_copilots_org_status", table_name="ai_copilot_definitions")
    op.drop_table("ai_copilot_definitions")
