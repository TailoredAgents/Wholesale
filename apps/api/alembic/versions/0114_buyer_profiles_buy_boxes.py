"""Add buyer profiles and independently versioned House and Land buy boxes.

Revision ID: 0114_buyer_profiles_buy_boxes
Revises: 0113_buyer_network_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0114_buyer_profiles_buy_boxes"
down_revision: str | None = "0113_buyer_network_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "buyers",
        sa.Column("tier", sa.String(length=40), nullable=False, server_default="unclassified"),
    )
    op.add_column(
        "buyers",
        sa.Column("temperature", sa.String(length=40), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "buyers",
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "buyers",
        sa.Column(
            "relationship_status", sa.String(length=40), nullable=False, server_default="new"
        ),
    )
    op.add_column("buyers", sa.Column("next_follow_up_at", sa.DateTime(timezone=True)))
    op.add_column(
        "buyers",
        sa.Column(
            "verification_status",
            sa.String(length=40),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column("buyers", sa.Column("verified_by_user_id", sa.Uuid()))
    op.add_column("buyers", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_buyers_verified_by_user",
        "buyers",
        "users",
        ["verified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_buyers_relationship_status", "buyers", ["relationship_status"])
    op.create_index("ix_buyers_next_follow_up_at", "buyers", ["next_follow_up_at"])
    op.create_index("ix_buyers_verification_status", "buyers", ["verification_status"])
    op.create_index("ix_buyers_verified_by_user_id", "buyers", ["verified_by_user_id"])
    op.create_index(
        "ix_buyers_org_relationship_follow_up",
        "buyers",
        ["organization_id", "relationship_status", "next_follow_up_at"],
    )

    op.create_table(
        "buyer_buy_boxes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("asset_class", sa.String(length=40), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "asset_class IN ('house', 'land')", name="ck_buyer_buy_boxes_asset_class"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "buyer_id",
            "asset_class",
            name="uq_buyer_buy_boxes_org_buyer_asset",
        ),
    )
    op.create_index("ix_buyer_buy_boxes_organization_id", "buyer_buy_boxes", ["organization_id"])
    op.create_index("ix_buyer_buy_boxes_buyer_id", "buyer_buy_boxes", ["buyer_id"])
    op.create_index("ix_buyer_buy_boxes_asset_class", "buyer_buy_boxes", ["asset_class"])

    op.create_table(
        "buyer_buy_box_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("buy_box_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criteria_payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column(
            "verification_status",
            sa.String(length=40),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("verified_by_user_id", sa.Uuid()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["buy_box_id"], ["buyer_buy_boxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "buy_box_id",
            "version_number",
            name="uq_buyer_buy_box_versions_number",
        ),
    )
    op.create_index(
        "ix_buyer_buy_box_versions_organization_id",
        "buyer_buy_box_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_buyer_buy_box_versions_buy_box_id",
        "buyer_buy_box_versions",
        ["buy_box_id"],
    )
    op.create_index(
        "ix_buyer_buy_box_versions_created_by_user_id",
        "buyer_buy_box_versions",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_buyer_buy_box_versions_history",
        "buyer_buy_box_versions",
        ["organization_id", "buy_box_id", "version_number"],
    )
    op.create_index(
        "uq_buyer_buy_box_versions_current",
        "buyer_buy_box_versions",
        ["organization_id", "buy_box_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )

    op.add_column("buyer_proof_documents", sa.Column("verified_by_user_id", sa.Uuid()))
    op.add_column(
        "buyer_proof_documents", sa.Column("verified_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "buyer_proof_documents", sa.Column("verification_source", sa.String(length=120))
    )
    op.create_foreign_key(
        "fk_buyer_proof_documents_verified_by_user",
        "buyer_proof_documents",
        "users",
        ["verified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_buyer_proof_documents_verified_by_user_id",
        "buyer_proof_documents",
        ["verified_by_user_id"],
    )
    # Older rows had no reviewer identity or review timestamp. Keep the evidence,
    # but require the new explicit human review before it can qualify a buyer.
    op.execute(
        sa.text(
            "UPDATE buyer_proof_documents "
            "SET status = 'received' "
            "WHERE status = 'verified'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE buyers "
            "SET proof_of_funds_status = CASE "
            "WHEN EXISTS ("
            "SELECT 1 FROM buyer_proof_documents "
            "WHERE buyer_proof_documents.buyer_id = buyers.id "
            "AND buyer_proof_documents.organization_id = buyers.organization_id "
            "AND buyer_proof_documents.status = 'received' "
            "AND buyer_proof_documents.deleted_at IS NULL"
            ") THEN 'received' ELSE 'unknown' END, "
            "proof_of_funds_expires_at = NULL "
            "WHERE proof_of_funds_status = 'verified'"
        )
    )

    op.alter_column("buyer_engagements", "disposition_case_id", nullable=True)
    op.add_column("buyer_engagements", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_buyer_engagements_relationship_schedule",
        "buyer_engagements",
        ["organization_id", "buyer_id", "status", "scheduled_at"],
    )

    op.add_column("disposition_matches", sa.Column("buy_box_version_id", sa.Uuid()))
    op.add_column(
        "disposition_matches", sa.Column("matcher_version", sa.String(length=80))
    )
    op.add_column("disposition_matches", sa.Column("criteria_snapshot", sa.JSON()))
    op.create_foreign_key(
        "fk_disposition_matches_buy_box_version",
        "disposition_matches",
        "buyer_buy_box_versions",
        ["buy_box_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_disposition_matches_buy_box_version_id",
        "disposition_matches",
        ["buy_box_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_disposition_matches_buy_box_version_id", table_name="disposition_matches")
    op.drop_constraint(
        "fk_disposition_matches_buy_box_version", "disposition_matches", type_="foreignkey"
    )
    op.drop_column("disposition_matches", "criteria_snapshot")
    op.drop_column("disposition_matches", "matcher_version")
    op.drop_column("disposition_matches", "buy_box_version_id")

    op.drop_index(
        "ix_buyer_engagements_relationship_schedule", table_name="buyer_engagements"
    )
    # Relationship-only activity cannot be represented by the pre-DS3 schema,
    # where every engagement was required to belong to a disposition case.
    # Remove those rows explicitly so restoring the NOT NULL constraint is safe.
    op.execute(
        sa.text("DELETE FROM buyer_engagements WHERE disposition_case_id IS NULL")
    )
    op.drop_column("buyer_engagements", "completed_at")
    op.alter_column("buyer_engagements", "disposition_case_id", nullable=False)

    op.drop_index(
        "ix_buyer_proof_documents_verified_by_user_id", table_name="buyer_proof_documents"
    )
    op.drop_constraint(
        "fk_buyer_proof_documents_verified_by_user",
        "buyer_proof_documents",
        type_="foreignkey",
    )
    op.drop_column("buyer_proof_documents", "verification_source")
    op.drop_column("buyer_proof_documents", "verified_at")
    op.drop_column("buyer_proof_documents", "verified_by_user_id")

    op.drop_index("uq_buyer_buy_box_versions_current", table_name="buyer_buy_box_versions")
    op.drop_index("ix_buyer_buy_box_versions_history", table_name="buyer_buy_box_versions")
    op.drop_index(
        "ix_buyer_buy_box_versions_created_by_user_id", table_name="buyer_buy_box_versions"
    )
    op.drop_index("ix_buyer_buy_box_versions_buy_box_id", table_name="buyer_buy_box_versions")
    op.drop_index(
        "ix_buyer_buy_box_versions_organization_id", table_name="buyer_buy_box_versions"
    )
    op.drop_table("buyer_buy_box_versions")
    op.drop_index("ix_buyer_buy_boxes_asset_class", table_name="buyer_buy_boxes")
    op.drop_index("ix_buyer_buy_boxes_buyer_id", table_name="buyer_buy_boxes")
    op.drop_index("ix_buyer_buy_boxes_organization_id", table_name="buyer_buy_boxes")
    op.drop_table("buyer_buy_boxes")

    op.drop_index("ix_buyers_org_relationship_follow_up", table_name="buyers")
    op.drop_index("ix_buyers_verified_by_user_id", table_name="buyers")
    op.drop_index("ix_buyers_verification_status", table_name="buyers")
    op.drop_index("ix_buyers_next_follow_up_at", table_name="buyers")
    op.drop_index("ix_buyers_relationship_status", table_name="buyers")
    op.drop_constraint("fk_buyers_verified_by_user", "buyers", type_="foreignkey")
    op.drop_column("buyers", "verified_at")
    op.drop_column("buyers", "verified_by_user_id")
    op.drop_column("buyers", "verification_status")
    op.drop_column("buyers", "next_follow_up_at")
    op.drop_column("buyers", "relationship_status")
    op.drop_column("buyers", "tags")
    op.drop_column("buyers", "temperature")
    op.drop_column("buyers", "tier")
