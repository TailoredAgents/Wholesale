"""Add PropStream import lineage and ranked prospect contacts.

Revision ID: 0074_propstream_pipeline
Revises: 0073_va_dialer_metrics
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_propstream_pipeline"
down_revision: str | None = "0073_va_dialer_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prospect_import_batches", sa.Column("cohort_id", sa.Uuid(), nullable=True))
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_name", sa.String(160), nullable=True),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column(
            "source_profile",
            sa.String(40),
            server_default="general_csv",
            nullable=False,
        ),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_export_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_list_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_list_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_exported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("source_filters", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "prospect_import_batches",
        sa.Column("matched_existing_rows", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE prospect_import_batches
            SET source_name = COALESCE(
                (
                    SELECT pim.source_name
                    FROM prospect_import_mappings pim
                    WHERE pim.id = prospect_import_batches.mapping_id
                ),
                'CSV import'
            )
            """
        )
    )
    op.alter_column(
        "prospect_import_batches",
        "source_name",
        existing_type=sa.String(160),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_prospect_import_batches_cohort_id",
        "prospect_import_batches",
        "prospecting_cohorts",
        ["cohort_id"],
        ["id"],
    )
    for column in ("cohort_id", "source_export_id", "source_list_id"):
        op.create_index(
            f"ix_prospect_import_batches_{column}",
            "prospect_import_batches",
            [column],
        )

    op.create_table(
        "prospect_source_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("cohort_id", sa.Uuid(), nullable=True),
        sa.Column("first_import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("latest_import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=False),
        sa.Column("source_profile", sa.String(40), nullable=False),
        sa.Column("source_record_key", sa.String(255), nullable=True),
        sa.Column("source_list_key", sa.String(255), nullable=False),
        sa.Column("source_list_name", sa.String(255), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("appearance_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("relationship_state_at_latest_import", sa.String(40), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["cohort_id"], ["prospecting_cohorts.id"]),
        sa.ForeignKeyConstraint(["first_import_batch_id"], ["prospect_import_batches.id"]),
        sa.ForeignKeyConstraint(["latest_import_batch_id"], ["prospect_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prospect_id",
            "source_name",
            "source_list_key",
            name="uq_prospect_source_memberships_prospect_source_list",
        ),
    )
    for column in (
        "organization_id",
        "prospect_id",
        "campaign_id",
        "cohort_id",
        "first_import_batch_id",
        "latest_import_batch_id",
        "source_name",
        "source_record_key",
    ):
        op.create_index(
            f"ix_prospect_source_memberships_{column}",
            "prospect_source_memberships",
            [column],
        )
    op.create_index(
        "ix_psm_latest_relationship_state",
        "prospect_source_memberships",
        ["relationship_state_at_latest_import"],
    )

    op.create_table(
        "prospect_contact_points",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("source_membership_id", sa.Uuid(), nullable=True),
        sa.Column("contact_type", sa.String(20), nullable=False),
        sa.Column("value", sa.String(320), nullable=False),
        sa.Column("normalized_value", sa.String(320), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("validation_status", sa.String(40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(
            ["source_membership_id"],
            ["prospect_source_memberships.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "prospect_id",
            "contact_type",
            "normalized_value",
            name="uq_prospect_contact_points_prospect_value",
        ),
    )
    for column in (
        "organization_id",
        "prospect_id",
        "source_membership_id",
        "contact_type",
        "normalized_value",
    ):
        op.create_index(
            f"ix_prospect_contact_points_{column}",
            "prospect_contact_points",
            [column],
        )

    op.add_column(
        "prospect_import_rows",
        sa.Column("source_membership_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_prospect_import_rows_source_membership_id",
        "prospect_import_rows",
        "prospect_source_memberships",
        ["source_membership_id"],
        ["id"],
    )
    op.create_index(
        "ix_prospect_import_rows_source_membership_id",
        "prospect_import_rows",
        ["source_membership_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prospect_import_rows_source_membership_id",
        table_name="prospect_import_rows",
    )
    op.drop_constraint(
        "fk_prospect_import_rows_source_membership_id",
        "prospect_import_rows",
        type_="foreignkey",
    )
    op.drop_column("prospect_import_rows", "source_membership_id")

    for column in (
        "normalized_value",
        "contact_type",
        "source_membership_id",
        "prospect_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_prospect_contact_points_{column}",
            table_name="prospect_contact_points",
        )
    op.drop_table("prospect_contact_points")

    op.drop_index(
        "ix_psm_latest_relationship_state",
        table_name="prospect_source_memberships",
    )
    for column in (
        "source_record_key",
        "source_name",
        "latest_import_batch_id",
        "first_import_batch_id",
        "cohort_id",
        "campaign_id",
        "prospect_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_prospect_source_memberships_{column}",
            table_name="prospect_source_memberships",
        )
    op.drop_table("prospect_source_memberships")

    for column in ("source_list_id", "source_export_id", "cohort_id"):
        op.drop_index(
            f"ix_prospect_import_batches_{column}",
            table_name="prospect_import_batches",
        )
    op.drop_constraint(
        "fk_prospect_import_batches_cohort_id",
        "prospect_import_batches",
        type_="foreignkey",
    )
    for column in (
        "matched_existing_rows",
        "source_filters",
        "source_exported_at",
        "source_list_name",
        "source_list_id",
        "source_export_id",
        "source_profile",
        "source_name",
        "cohort_id",
    ):
        op.drop_column("prospect_import_batches", column)
