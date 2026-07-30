"""Add explicit cold-calling eligibility to workspace users.

Revision ID: 0077_user_calling_eligibility
Revises: 0076_retire_multi_line
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0077_user_calling_eligibility"
down_revision: str | None = "0076_retire_multi_line"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "calling_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        """
        UPDATE users
        SET calling_enabled = true
        WHERE id IN (
            SELECT role_assignments.user_id
            FROM role_assignments
            JOIN roles ON roles.id = role_assignments.role_id
            WHERE roles.key IN (
                'owner',
                'founder_operator',
                'ceo',
                'administrator',
                'acquisition_manager',
                'prospecting_caller'
            )
        )
        """
    )


def downgrade() -> None:
    op.drop_column("users", "calling_enabled")
