"""Add provider-neutral email aliases and sender grants.

Revision ID: 0066_f8_email_foundation
Revises: 0065_f7_underwriting_calibration
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_f8_email_foundation"
down_revision: str | None = "0065_f7_underwriting_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_sender_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid()),
        sa.Column("assigned_team_id", sa.Uuid()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("provider_identity_id", sa.String(320)),
        sa.Column("email_address", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("alias_type", sa.String(40), nullable=False),
        sa.Column("purpose_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("inbound_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("outbound_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("signature_text", sa.String(4000)),
        sa.Column("metadata", sa.JSON()),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_team_id"], ["teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "email_address",
            name="uq_email_sender_aliases_org_address",
        ),
    )
    op.create_index(
        "ix_email_sender_aliases_organization_id",
        "email_sender_aliases",
        ["organization_id"],
    )
    op.create_index(
        "ix_email_sender_aliases_owner_user_id",
        "email_sender_aliases",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_email_sender_aliases_assigned_team_id",
        "email_sender_aliases",
        ["assigned_team_id"],
    )
    op.create_index(
        "ix_email_sender_aliases_status",
        "email_sender_aliases",
        ["status"],
    )

    op.create_table(
        "email_sender_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email_sender_alias_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(40), nullable=False),
        sa.Column("can_send", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "receives_notifications",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["email_sender_alias_id"],
            ["email_sender_aliases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "email_sender_alias_id",
            "user_id",
            name="uq_email_sender_grants_alias_user",
        ),
    )
    op.create_index(
        "ix_email_sender_grants_organization_id",
        "email_sender_grants",
        ["organization_id"],
    )
    op.create_index(
        "ix_email_sender_grants_email_sender_alias_id",
        "email_sender_grants",
        ["email_sender_alias_id"],
    )
    op.create_index(
        "ix_email_sender_grants_user_id",
        "email_sender_grants",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_sender_grants_user_id",
        table_name="email_sender_grants",
    )
    op.drop_index(
        "ix_email_sender_grants_email_sender_alias_id",
        table_name="email_sender_grants",
    )
    op.drop_index(
        "ix_email_sender_grants_organization_id",
        table_name="email_sender_grants",
    )
    op.drop_table("email_sender_grants")
    op.drop_index(
        "ix_email_sender_aliases_status",
        table_name="email_sender_aliases",
    )
    op.drop_index(
        "ix_email_sender_aliases_assigned_team_id",
        table_name="email_sender_aliases",
    )
    op.drop_index(
        "ix_email_sender_aliases_owner_user_id",
        table_name="email_sender_aliases",
    )
    op.drop_index(
        "ix_email_sender_aliases_organization_id",
        table_name="email_sender_aliases",
    )
    op.drop_table("email_sender_aliases")
