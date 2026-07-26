"""Persist verified SignWell provider setup.

Revision ID: 0058_signwell_provider_setup
Revises: 0057_f5_buyer_discovery
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_signwell_provider_setup"
down_revision: str | None = "0057_f5_buyer_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "esign_provider_configurations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("configured_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("webhook_id", sa.String(255), nullable=False),
        sa.Column("callback_url", sa.String(1000), nullable=False),
        sa.Column("account_email", sa.String(320)),
        sa.Column("account_name", sa.String(255)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_details", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["configured_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            name="uq_esign_provider_configuration",
        ),
    )
    op.create_index(
        "ix_esign_provider_configurations_organization_id",
        "esign_provider_configurations",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_table("esign_provider_configurations")
