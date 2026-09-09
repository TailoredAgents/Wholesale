"""Reserve the callback line for Marin and the human line for staff.

Revision ID: 0128_realtime_seller_line
Revises: 0127_retire_legacy_tasks
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0128_realtime_seller_line"
down_revision: str | None = "0127_retire_legacy_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_LINE = "+16785417725"
HUMAN_LINE = "+14047772631"


def upgrade() -> None:
    voice_lines = sa.table(
        "voice_lines",
        sa.column("phone_number", sa.String()),
        sa.column("label", sa.String()),
        sa.column("department_key", sa.String()),
        sa.column("purpose_key", sa.String()),
        sa.column("inbound_route", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    op.execute(
        voice_lines.update()
        .where(voice_lines.c.phone_number == AI_LINE)
        .values(
            label="Marin seller callback",
            department_key="acquisitions",
            purpose_key="seller_callback_ai",
            inbound_route="openai_realtime",
            is_default=False,
        )
    )
    op.execute(
        voice_lines.update()
        .where(voice_lines.c.phone_number == HUMAN_LINE)
        .values(
            department_key="acquisitions",
            purpose_key="seller_conversations",
            inbound_route="conversation_owner",
            is_default=True,
        )
    )


def downgrade() -> None:
    voice_lines = sa.table(
        "voice_lines",
        sa.column("phone_number", sa.String()),
        sa.column("label", sa.String()),
        sa.column("purpose_key", sa.String()),
        sa.column("inbound_route", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    op.execute(
        voice_lines.update()
        .where(voice_lines.c.phone_number == AI_LINE)
        .values(
            label="Stonegate Acquisitions",
            purpose_key="seller_conversations",
            inbound_route="conversation_owner",
            is_default=True,
        )
    )
    op.execute(
        voice_lines.update()
        .where(voice_lines.c.phone_number == HUMAN_LINE)
        .values(is_default=False)
    )
