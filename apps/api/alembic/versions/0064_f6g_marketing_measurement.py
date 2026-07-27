"""Extend offline conversions into governed marketing measurement.

Revision ID: 0064_f6g_marketing_measurement
Revises: 0063_f6_bank_reconciliation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_f6g_marketing_measurement"
down_revision: str | None = "0063_f6_bank_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("offline_conversion_exports", sa.Column("event_key", sa.String(255)))
    op.add_column("offline_conversion_exports", sa.Column("source_record_type", sa.String(80)))
    op.add_column("offline_conversion_exports", sa.Column("source_record_id", sa.Uuid()))
    op.add_column(
        "offline_conversion_exports",
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
    )
    op.add_column("offline_conversion_exports", sa.Column("attribution_model", sa.String(120)))
    op.add_column("offline_conversion_exports", sa.Column("consent_basis", sa.String(160)))
    op.add_column("offline_conversion_exports", sa.Column("payload_hash", sa.String(64)))
    op.add_column("offline_conversion_exports", sa.Column("payload_snapshot", sa.JSON()))
    op.add_column("offline_conversion_exports", sa.Column("delivery_mode", sa.String(40)))
    op.add_column(
        "offline_conversion_exports",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "offline_conversion_exports",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "offline_conversion_exports",
        sa.Column("provider_request_id", sa.String(255)),
    )
    op.add_column("offline_conversion_exports", sa.Column("provider_response", sa.JSON()))

    op.execute(
        sa.text(
            """
            UPDATE offline_conversion_exports
            SET event_key = CONCAT('legacy:', id),
                source_record_type = 'revenue_record',
                source_record_id = COALESCE(revenue_record_id, conversion_event_id, id),
                occurred_at = created_at,
                attribution_model = 'last_eligible_platform_click',
                consent_basis = 'privacy_notice_first_party_measurement',
                payload_hash = REPEAT('0', 64),
                payload_snapshot = '{}',
                delivery_mode = 'legacy'
            """
        )
    )
    for column in (
        "event_key",
        "source_record_type",
        "source_record_id",
        "occurred_at",
        "attribution_model",
        "consent_basis",
        "payload_hash",
        "payload_snapshot",
        "delivery_mode",
    ):
        op.alter_column("offline_conversion_exports", column, nullable=False)

    op.create_index(
        "ix_offline_conversion_exports_source_record_id",
        "offline_conversion_exports",
        ["source_record_id"],
    )
    op.create_index(
        "ix_offline_exports_org_status_due",
        "offline_conversion_exports",
        ["organization_id", "status", "next_attempt_at"],
    )
    op.create_unique_constraint(
        "uq_offline_exports_org_platform_event",
        "offline_conversion_exports",
        ["organization_id", "platform", "event_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_offline_exports_org_platform_event",
        "offline_conversion_exports",
        type_="unique",
    )
    op.drop_index("ix_offline_exports_org_status_due", table_name="offline_conversion_exports")
    op.drop_index(
        "ix_offline_conversion_exports_source_record_id",
        table_name="offline_conversion_exports",
    )
    for column in (
        "provider_response",
        "provider_request_id",
        "next_attempt_at",
        "last_attempt_at",
        "delivery_mode",
        "payload_snapshot",
        "payload_hash",
        "consent_basis",
        "attribution_model",
        "occurred_at",
        "source_record_id",
        "source_record_type",
        "event_key",
    ):
        op.drop_column("offline_conversion_exports", column)
