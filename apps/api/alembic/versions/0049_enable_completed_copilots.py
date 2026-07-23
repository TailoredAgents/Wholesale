"""Enable every completed Copilot in supervised draft-only mode.

Revision ID: 0049_enable_completed_copilots
Revises: 0048_enable_transaction_copilot
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0049_enable_completed_copilots"
down_revision: str | None = "0048_enable_transaction_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPLETED_CAPABILITIES = (
    "lead.next_action",
    "prospecting.prioritize",
    "call.quality_coach",
    "appointment.brief",
    "negotiation.coach",
    "transaction.coordinate",
)


def upgrade() -> None:
    capabilities = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("requires_human_review", sa.Boolean()),
    )
    runtimes = sa.table(
        "ai_runtime_policies",
        sa.column("provider_status", sa.String()),
        sa.column("external_actions_enabled", sa.Boolean()),
    )
    op.execute(
        capabilities.update()
        .where(capabilities.c.capability_key.in_(COMPLETED_CAPABILITIES))
        .values(status="enabled", requires_human_review=True)
    )
    op.execute(
        runtimes.update().values(
            provider_status="enabled",
            external_actions_enabled=False,
        )
    )


def downgrade() -> None:
    capabilities = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
    )
    runtimes = sa.table(
        "ai_runtime_policies",
        sa.column("provider_status", sa.String()),
    )
    op.execute(
        capabilities.update()
        .where(
            capabilities.c.capability_key.in_(
                tuple(
                    key
                    for key in COMPLETED_CAPABILITIES
                    if key != "transaction.coordinate"
                )
            )
        )
        .values(status="disabled")
    )
    op.execute(runtimes.update().values(provider_status="disabled"))
