"""Route BatchDialer campaigns to seller or investor workflows.

Revision ID: 0133_batchdialer_campaign_route
Revises: 0132_manual_inbox_reminders
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0133_batchdialer_campaign_route"
down_revision: str | None = "0132_manual_inbox_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("workflow_purpose", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("disposition_case_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("workflow_mapped_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "batchdialer_campaigns",
        sa.Column("workflow_mapped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_batchdialer_campaigns_workflow_purpose",
        "batchdialer_campaigns",
        "workflow_purpose IS NULL OR workflow_purpose IN "
        "('seller_acquisition', 'investor_disposition')",
    )
    op.create_foreign_key(
        "fk_batchdialer_campaigns_disposition_case",
        "batchdialer_campaigns",
        "disposition_cases",
        ["disposition_case_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_batchdialer_campaigns_workflow_mapped_by_user",
        "batchdialer_campaigns",
        "users",
        ["workflow_mapped_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_batchdialer_campaigns_disposition_case_id",
        "batchdialer_campaigns",
        ["disposition_case_id"],
    )
    op.execute(
        "UPDATE batchdialer_campaigns "
        "SET workflow_purpose = 'seller_acquisition', "
        "workflow_mapped_by_user_id = asset_class_mapped_by_user_id, "
        "workflow_mapped_at = asset_class_mapped_at "
        "WHERE asset_class IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_batchdialer_campaigns_disposition_case_id",
        table_name="batchdialer_campaigns",
    )
    op.drop_constraint(
        "fk_batchdialer_campaigns_workflow_mapped_by_user",
        "batchdialer_campaigns",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_batchdialer_campaigns_disposition_case",
        "batchdialer_campaigns",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_batchdialer_campaigns_workflow_purpose",
        "batchdialer_campaigns",
        type_="check",
    )
    op.drop_column("batchdialer_campaigns", "workflow_mapped_at")
    op.drop_column("batchdialer_campaigns", "workflow_mapped_by_user_id")
    op.drop_column("batchdialer_campaigns", "disposition_case_id")
    op.drop_column("batchdialer_campaigns", "workflow_purpose")
