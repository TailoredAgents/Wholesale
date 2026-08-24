"""Add explicit asset mapping to BatchDialer campaigns.

Revision ID: 0112_batchdialer_campaign_assets
Revises: 0111_batchdialer_va_facts
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0112_batchdialer_campaign_assets"
down_revision: str | None = "0111_batchdialer_va_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("asset_class", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("asset_class_mapped_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("asset_class_mapped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_batchdialer_campaigns_asset_class",
        "batchdialer_campaigns",
        "asset_class IS NULL OR asset_class IN ('house', 'land')",
    )
    op.create_foreign_key(
        "fk_batchdialer_campaigns_asset_mapped_by_user",
        "batchdialer_campaigns",
        "users",
        ["asset_class_mapped_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_batchdialer_campaigns_asset_mapped_by_user",
        "batchdialer_campaigns",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_batchdialer_campaigns_asset_class",
        "batchdialer_campaigns",
        type_="check",
    )
    op.drop_column("batchdialer_campaigns", "asset_class_mapped_at")
    op.drop_column("batchdialer_campaigns", "asset_class_mapped_by_user_id")
    op.drop_column("batchdialer_campaigns", "asset_class")
