"""Correct Marin and Stonegate human-line assignments.

Revision ID: 0129_correct_realtime_line
Revises: 0128_realtime_seller_line
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0129_correct_realtime_line"
down_revision: str | None = "0128_realtime_seller_line"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_LINE = "+14708887952"
HUMAN_LINE = "+16785417725"
UNRELATED_LINE = "+14047772631"


def upgrade() -> None:
    voice_lines = sa.table(
        "voice_lines",
        sa.column("organization_id", sa.Uuid()),
        sa.column("phone_number", sa.String()),
        sa.column("label", sa.String()),
        sa.column("department_key", sa.String()),
        sa.column("purpose_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("inbound_route", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
    )
    stonegate_organization_ids = sa.select(organizations.c.id).where(
        organizations.c.slug == "stonegate-home-buyers"
    )
    # Revision 0128 temporarily made the unrelated line Stonegate's default. Clear it
    # first so databases that enforce one default line per organization can switch safely.
    op.execute(
        voice_lines.update()
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == UNRELATED_LINE,
        )
        .values(status="inactive", is_default=False)
    )
    op.execute(
        voice_lines.update()
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == AI_LINE,
        )
        .values(
            label="Marin seller callback",
            department_key="acquisitions",
            purpose_key="seller_callback_ai",
            status="active",
            inbound_route="openai_realtime",
            is_default=False,
        )
    )
    op.execute(
        voice_lines.update()
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == HUMAN_LINE,
        )
        .values(
            label="Stonegate Acquisitions",
            department_key="acquisitions",
            purpose_key="seller_conversations",
            status="active",
            inbound_route="conversation_owner",
            is_default=True,
        )
    )


def downgrade() -> None:
    voice_lines = sa.table(
        "voice_lines",
        sa.column("organization_id", sa.Uuid()),
        sa.column("phone_number", sa.String()),
        sa.column("label", sa.String()),
        sa.column("department_key", sa.String()),
        sa.column("purpose_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("inbound_route", sa.String()),
        sa.column("is_default", sa.Boolean()),
    )
    organizations = sa.table(
        "organizations",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
    )
    stonegate_organization_ids = sa.select(organizations.c.id).where(
        organizations.c.slug == "stonegate-home-buyers"
    )
    op.execute(
        voice_lines.update()
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == AI_LINE,
        )
        .values(
            label="Stonegate Dispositions",
            department_key="dispositions",
            purpose_key="buyer_relations",
            inbound_route="assigned_user",
            is_default=False,
        )
    )
    op.execute(
        voice_lines.update()
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == HUMAN_LINE,
        )
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
        .where(
            voice_lines.c.organization_id.in_(stonegate_organization_ids),
            voice_lines.c.phone_number == UNRELATED_LINE,
        )
        .values(status="active", is_default=True)
    )
