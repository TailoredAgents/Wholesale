"""speed to lead tasks

Revision ID: 0005_speed_to_lead_tasks
Revises: 0004_duplicate_detection
Create Date: 2026-07-12 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_speed_to_lead_tasks"
down_revision: str | None = "0004_duplicate_detection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("lead_id", sa.Uuid(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column("task_type", sa.String(length=120), nullable=False, server_default="general"),
    )
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_tasks_lead_id_leads", "tasks", "leads", ["lead_id"], ["id"])
    op.create_index("ix_tasks_lead_id", "tasks", ["lead_id"])
    op.alter_column("tasks", "task_type", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_tasks_lead_id", table_name="tasks")
    op.drop_constraint("fk_tasks_lead_id_leads", "tasks", type_="foreignkey")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "task_type")
    op.drop_column("tasks", "lead_id")
