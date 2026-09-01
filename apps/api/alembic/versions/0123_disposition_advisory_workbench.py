"""Make disposition setup and package readiness advisory.

Revision ID: 0123_disposition_advisory
Revises: 0122_disposition_execution
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0123_disposition_advisory"
down_revision: str | None = "0122_disposition_execution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STALE_DISPOSITION_MANAGER_GLOBAL_BULK_DELETE_SQL = (
    "DELETE FROM role_permissions "
    "WHERE EXISTS ("
    "SELECT 1 FROM roles "
    "JOIN permissions ON permissions.id = role_permissions.permission_id "
    "WHERE roles.id = role_permissions.role_id "
    "AND roles.organization_id = role_permissions.organization_id "
    "AND roles.key = 'disposition_manager' "
    "AND permissions.key = 'communications:send_bulk'"
    ")"
)


def upgrade() -> None:
    with op.batch_alter_table("disposition_cases") as batch_op:
        batch_op.alter_column("owner_user_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column(
            "compensation_plan_version_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
        batch_op.alter_column(
            "disposition_operating_mode_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )
    op.add_column(
        "disposition_buyer_selections",
        sa.Column("advisory_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "disposition_package_share_links",
        sa.Column("package_status_at_issue", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "disposition_package_share_links",
        sa.Column("was_current_at_issue", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "disposition_provider_listing_revisions",
        sa.Column("package_status_at_prepare", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "disposition_provider_listing_revisions",
        sa.Column("package_was_current_at_prepare", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "disposition_outreach_revisions",
        sa.Column("package_status_at_prepare", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "disposition_outreach_revisions",
        sa.Column("package_was_current_at_prepare", sa.Boolean(), nullable=True),
    )
    # Older bootstrap definitions granted this built-in role the global marketing
    # bulk-send permission. Remove only that exact tenant-scoped built-in pairing;
    # bootstrap grants the new Dispositions-specific permission from current role
    # definitions without changing custom roles or other built-in roles.
    op.get_bind().execute(
        sa.text(STALE_DISPOSITION_MANAGER_GLOBAL_BULK_DELETE_SQL)
    )


def downgrade() -> None:
    null_setup_count = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM disposition_cases "
            "WHERE owner_user_id IS NULL "
            "OR compensation_plan_version_id IS NULL "
            "OR disposition_operating_mode_id IS NULL"
        )
    ).scalar_one()
    if null_setup_count:
        raise RuntimeError(
            "Cannot downgrade 0123: disposition case setup is incomplete. "
            "Assign an owner, compensation plan, and operating mode to every case first."
        )
    with op.batch_alter_table("disposition_outreach_revisions") as batch_op:
        batch_op.drop_column("package_was_current_at_prepare")
        batch_op.drop_column("package_status_at_prepare")
    with op.batch_alter_table("disposition_provider_listing_revisions") as batch_op:
        batch_op.drop_column("package_was_current_at_prepare")
        batch_op.drop_column("package_status_at_prepare")
    with op.batch_alter_table("disposition_package_share_links") as batch_op:
        batch_op.drop_column("was_current_at_issue")
        batch_op.drop_column("package_status_at_issue")
    with op.batch_alter_table("disposition_buyer_selections") as batch_op:
        batch_op.drop_column("advisory_snapshot")
    with op.batch_alter_table("disposition_cases") as batch_op:
        batch_op.alter_column(
            "disposition_operating_mode_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.alter_column(
            "compensation_plan_version_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.alter_column("owner_user_id", existing_type=sa.Uuid(), nullable=False)
