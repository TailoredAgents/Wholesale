"""Phase AI10 controlled external-action policy and simulation foundation.

Revision ID: 0052_ai10_action_controls
Revises: 0051_management_copilots
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052_ai10_action_controls"
down_revision: str | None = "0051_management_copilots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_external_action_policies",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1200), nullable=False),
        sa.Column("capability_key", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("provider_key", sa.String(120), nullable=False),
        sa.Column("owner_role_key", sa.String(120), nullable=False),
        sa.Column(
            "status",
            sa.String(40),
            nullable=False,
            server_default="control_only",
        ),
        sa.Column("audience_policy", sa.JSON(), nullable=False),
        sa.Column("consent_policy", sa.JSON(), nullable=False),
        sa.Column("template_policy", sa.JSON(), nullable=False),
        sa.Column("schedule_policy", sa.JSON(), nullable=False),
        sa.Column("volume_policy", sa.JSON(), nullable=False),
        sa.Column("cost_policy", sa.JSON(), nullable=False),
        sa.Column("quality_policy", sa.JSON(), nullable=False),
        sa.Column("canary_policy", sa.JSON(), nullable=False),
        sa.Column("pause_policy", sa.JSON(), nullable=False),
        sa.Column("rollback_policy", sa.JSON(), nullable=False),
        sa.Column("prohibited_actions", sa.JSON(), nullable=False),
        sa.Column("dry_run_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "external_delivery_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("last_pause_reason", sa.String(1000)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "action_key",
            name="uq_ai_external_action_policy_org_key",
        ),
    )
    op.create_index(
        "ix_ai_external_action_policy_org_status",
        "ai_external_action_policies",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_ai_external_action_policies_organization_id",
        "ai_external_action_policies",
        ["organization_id"],
    )

    op.create_table(
        "ai_external_action_attempts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column(
            "execution_mode",
            sa.String(40),
            nullable=False,
            server_default="simulation",
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("audience_count", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("policy_checks", sa.JSON(), nullable=False),
        sa.Column("block_reasons", sa.JSON(), nullable=False),
        sa.Column(
            "external_delivery_attempted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "delivered_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["ai_external_action_policies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_ai_external_action_attempt_org_idempotency",
        ),
    )
    op.create_index(
        "ix_ai_external_action_attempt_policy_created",
        "ai_external_action_attempts",
        ["policy_id", "created_at"],
    )
    op.create_index(
        "ix_ai_external_action_attempts_organization_id",
        "ai_external_action_attempts",
        ["organization_id"],
    )
    op.create_index(
        "ix_ai_external_action_attempts_policy_id",
        "ai_external_action_attempts",
        ["policy_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_external_action_attempts_policy_id",
        table_name="ai_external_action_attempts",
    )
    op.drop_index(
        "ix_ai_external_action_attempts_organization_id",
        table_name="ai_external_action_attempts",
    )
    op.drop_index(
        "ix_ai_external_action_attempt_policy_created",
        table_name="ai_external_action_attempts",
    )
    op.drop_table("ai_external_action_attempts")
    op.drop_index(
        "ix_ai_external_action_policies_organization_id",
        table_name="ai_external_action_policies",
    )
    op.drop_index(
        "ix_ai_external_action_policy_org_status",
        table_name="ai_external_action_policies",
    )
    op.drop_table("ai_external_action_policies")
