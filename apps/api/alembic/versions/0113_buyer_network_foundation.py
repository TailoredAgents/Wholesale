"""Add the buyer-network identity and lifecycle foundation.

Revision ID: 0113_buyer_network_foundation
Revises: 0112_batchdialer_campaign_assets
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0113_buyer_network_foundation"
down_revision: str | None = "0112_batchdialer_campaign_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("buyers", sa.Column("normalized_email", sa.String(length=320)))
    op.add_column("buyers", sa.Column("normalized_phone", sa.String(length=32)))
    op.add_column("buyers", sa.Column("normalized_company_name", sa.String(length=255)))
    op.add_column(
        "buyers",
        sa.Column("source_key", sa.String(length=80), nullable=False, server_default="legacy"),
    )
    op.add_column("buyers", sa.Column("source_detail", sa.String(length=255)))
    op.add_column("buyers", sa.Column("source_external_key", sa.String(length=255)))
    op.add_column("buyers", sa.Column("created_by_user_id", sa.Uuid()))
    op.add_column("buyers", sa.Column("relationship_owner_user_id", sa.Uuid()))
    op.add_column("buyers", sa.Column("last_verified_at", sa.DateTime(timezone=True)))
    op.add_column("buyers", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("buyers", sa.Column("archived_by_user_id", sa.Uuid()))
    op.add_column("buyers", sa.Column("archive_reason", sa.String(length=500)))

    op.execute(
        """
        UPDATE buyers
        SET normalized_email = CASE
                WHEN btrim(coalesce(email, '')) ~*
                    '^[A-Z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Z0-9.-]+\\.[A-Z]{2,}$'
                    THEN lower(btrim(email))
                ELSE NULL
            END,
            normalized_phone = CASE
                WHEN length(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g')) = 10
                    THEN '+1' || regexp_replace(phone, '[^0-9]', '', 'g')
                WHEN length(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g')) = 11
                    AND regexp_replace(phone, '[^0-9]', '', 'g') LIKE '1%'
                    THEN '+' || regexp_replace(phone, '[^0-9]', '', 'g')
                WHEN length(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g'))
                    BETWEEN 11 AND 15
                    THEN '+' || regexp_replace(phone, '[^0-9]', '', 'g')
                ELSE NULL
            END,
            normalized_company_name = NULLIF(
                lower(regexp_replace(btrim(coalesce(company_name, '')), '\\s+', ' ', 'g')),
                ''
            )
        """
    )
    op.execute(
        """
        UPDATE buyers
        SET status = 'needs_review'
        WHERE status = 'active'
          AND normalized_email IS NULL
          AND normalized_phone IS NULL
        """
    )

    op.create_foreign_key(
        "fk_buyers_created_by_user",
        "buyers",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_buyers_org_source_external_key",
        "buyers",
        ["organization_id", "source_key", "source_external_key"],
    )
    op.create_foreign_key(
        "fk_buyers_relationship_owner_user",
        "buyers",
        "users",
        ["relationship_owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_buyers_archived_by_user",
        "buyers",
        "users",
        ["archived_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_buyers_source_key", "buyers", ["source_key"])
    op.create_index("ix_buyers_source_external_key", "buyers", ["source_external_key"])
    op.create_index("ix_buyers_created_by_user_id", "buyers", ["created_by_user_id"])
    op.create_index(
        "ix_buyers_relationship_owner_user_id", "buyers", ["relationship_owner_user_id"]
    )
    op.create_index("ix_buyers_archived_at", "buyers", ["archived_at"])
    op.create_index(
        "ix_buyers_org_normalized_phone", "buyers", ["organization_id", "normalized_phone"]
    )
    op.create_index(
        "ix_buyers_org_normalized_email", "buyers", ["organization_id", "normalized_email"]
    )
    op.create_index(
        "ix_buyers_org_normalized_company",
        "buyers",
        ["organization_id", "normalized_company_name"],
    )
    op.create_index(
        "ix_buyers_org_status_created", "buyers", ["organization_id", "status", "created_at"]
    )

    op.add_column("buyer_criteria", sa.Column("version_number", sa.Integer()))
    op.add_column("buyer_criteria", sa.Column("is_current", sa.Boolean()))
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY organization_id, buyer_id
                       ORDER BY created_at ASC, id ASC
                   ) AS version_number,
                   row_number() OVER (
                       PARTITION BY organization_id, buyer_id
                       ORDER BY created_at DESC, id DESC
                   ) AS current_rank
            FROM buyer_criteria
        )
        UPDATE buyer_criteria AS criteria
        SET version_number = ranked.version_number,
            is_current = ranked.current_rank = 1
        FROM ranked
        WHERE criteria.id = ranked.id
        """
    )
    op.alter_column(
        "buyer_criteria", "version_number", nullable=False, server_default="1"
    )
    op.alter_column("buyer_criteria", "is_current", nullable=False, server_default=sa.true())
    op.create_unique_constraint(
        "uq_buyer_criteria_buyer_version",
        "buyer_criteria",
        ["organization_id", "buyer_id", "version_number"],
    )
    op.create_index(
        "ix_buyer_criteria_current",
        "buyer_criteria",
        ["organization_id", "buyer_id", "is_current"],
    )
    op.create_index(
        "uq_buyer_criteria_one_current",
        "buyer_criteria",
        ["organization_id", "buyer_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_buyer_criteria_one_current", table_name="buyer_criteria")
    op.drop_index("ix_buyer_criteria_current", table_name="buyer_criteria")
    op.drop_constraint(
        "uq_buyer_criteria_buyer_version", "buyer_criteria", type_="unique"
    )
    op.drop_column("buyer_criteria", "is_current")
    op.drop_column("buyer_criteria", "version_number")

    op.drop_index("ix_buyers_org_status_created", table_name="buyers")
    op.drop_index("ix_buyers_org_normalized_company", table_name="buyers")
    op.drop_index("ix_buyers_org_normalized_email", table_name="buyers")
    op.drop_index("ix_buyers_org_normalized_phone", table_name="buyers")
    op.drop_index("ix_buyers_archived_at", table_name="buyers")
    op.drop_index("ix_buyers_relationship_owner_user_id", table_name="buyers")
    op.drop_index("ix_buyers_created_by_user_id", table_name="buyers")
    op.drop_index("ix_buyers_source_key", table_name="buyers")
    op.drop_index("ix_buyers_source_external_key", table_name="buyers")
    op.drop_constraint("fk_buyers_archived_by_user", "buyers", type_="foreignkey")
    op.drop_constraint("uq_buyers_org_source_external_key", "buyers", type_="unique")
    op.drop_constraint("fk_buyers_relationship_owner_user", "buyers", type_="foreignkey")
    op.drop_constraint("fk_buyers_created_by_user", "buyers", type_="foreignkey")
    op.drop_column("buyers", "archive_reason")
    op.drop_column("buyers", "archived_by_user_id")
    op.drop_column("buyers", "archived_at")
    op.drop_column("buyers", "last_verified_at")
    op.drop_column("buyers", "relationship_owner_user_id")
    op.drop_column("buyers", "created_by_user_id")
    op.drop_column("buyers", "source_detail")
    op.drop_column("buyers", "source_external_key")
    op.drop_column("buyers", "source_key")
    op.drop_column("buyers", "normalized_company_name")
    op.drop_column("buyers", "normalized_phone")
    op.drop_column("buyers", "normalized_email")
