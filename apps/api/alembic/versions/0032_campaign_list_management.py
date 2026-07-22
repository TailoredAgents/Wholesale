"""Campaign imports, screening evidence, costs, and prospect calling batches.

Revision ID: 0032_campaign_list_management
Revises: 0031_operating_controls
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0032_campaign_list_management"
down_revision: str | None = "0031_operating_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), nullable=False)


def timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    _create_import_tables()
    _extend_prospects()
    _create_screening_and_cost_tables()
    _create_calling_batch_tables()


def _create_import_tables() -> None:
    op.create_table(
        "prospect_import_mappings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("source_name", sa.String(160), nullable=True),
        sa.Column("field_mapping", sa.JSON(), nullable=False),
        sa.Column("default_values", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_prospect_import_mappings_org_name"),
    )
    _indexes("prospect_import_mappings", "organization_id", "is_active")

    op.create_table(
        "prospect_import_batches",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_id", sa.Uuid(), nullable=False),
        sa.Column("default_assignee_user_id", sa.Uuid(), nullable=True),
        sa.Column("imported_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("valid_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("suppressed_rows", sa.Integer(), nullable=False),
        sa.Column("review_required_rows", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["mapping_id"], ["prospect_import_mappings.id"]),
        sa.ForeignKeyConstraint(["default_assignee_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "prospect_import_batches",
        "organization_id",
        "campaign_id",
        "mapping_id",
        "default_assignee_user_id",
        "file_sha256",
        "status",
    )

    op.create_table(
        "prospect_import_rows",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_prospect_id", sa.Uuid(), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("eligibility_reasons", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["prospect_import_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["duplicate_prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_batch_id", "row_number", name="uq_prospect_import_rows_batch_row"
        ),
    )
    _indexes(
        "prospect_import_rows",
        "organization_id",
        "import_batch_id",
        "prospect_id",
        "duplicate_prospect_id",
        "status",
    )


def _extend_prospects() -> None:
    op.add_column("prospects", sa.Column("import_batch_id", sa.Uuid(), nullable=True))
    op.add_column(
        "prospects",
        sa.Column(
            "phone_validation_status", sa.String(40), server_default="unverified", nullable=False
        ),
    )
    op.add_column(
        "prospects",
        sa.Column(
            "address_validation_status", sa.String(40), server_default="unverified", nullable=False
        ),
    )
    op.add_column(
        "prospects",
        sa.Column(
            "call_eligibility", sa.String(40), server_default="review_required", nullable=False
        ),
    )
    op.create_foreign_key(
        "fk_prospects_import_batch_id",
        "prospects",
        "prospect_import_batches",
        ["import_batch_id"],
        ["id"],
    )
    _indexes(
        "prospects",
        "import_batch_id",
        "phone_validation_status",
        "address_validation_status",
        "call_eligibility",
    )


def _create_screening_and_cost_tables() -> None:
    op.create_table(
        "prospect_suppression_checks",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("import_row_id", sa.Uuid(), nullable=True),
        sa.Column("prospect_id", sa.Uuid(), nullable=True),
        sa.Column("check_type", sa.String(80), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("normalized_value", sa.String(320), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["import_row_id"], ["prospect_import_rows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "prospect_suppression_checks",
        "organization_id",
        "import_row_id",
        "prospect_id",
        "check_type",
        "status",
    )

    op.create_table(
        "campaign_costs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("worker_user_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("vendor_name", sa.String(160), nullable=True),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("labor_minutes", sa.Integer(), nullable=True),
        sa.Column("hourly_rate_cents", sa.BigInteger(), nullable=True),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["prospect_import_batches.id"]),
        sa.ForeignKeyConstraint(["worker_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "campaign_costs",
        "organization_id",
        "campaign_id",
        "import_batch_id",
        "worker_user_id",
        "category",
        "incurred_on",
    )


def _create_calling_batch_tables() -> None:
    op.create_table(
        "prospect_calling_batches",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["prospect_import_batches.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_prospect_calling_batches_org_name"),
    )
    _indexes(
        "prospect_calling_batches",
        "organization_id",
        "campaign_id",
        "import_batch_id",
        "assigned_user_id",
        "status",
    )

    op.create_table(
        "prospect_calling_batch_entries",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_calling_batch_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("disposition", sa.String(120), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["prospect_calling_batch_id"], ["prospect_calling_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prospect_calling_batch_id",
            "prospect_id",
            name="uq_prospect_calling_batch_entries_batch_prospect",
        ),
    )
    _indexes(
        "prospect_calling_batch_entries",
        "organization_id",
        "prospect_calling_batch_id",
        "prospect_id",
        "assigned_user_id",
        "status",
    )


def _indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def downgrade() -> None:
    op.drop_table("prospect_calling_batch_entries")
    op.drop_table("prospect_calling_batches")
    op.drop_table("campaign_costs")
    op.drop_table("prospect_suppression_checks")

    for column in (
        "call_eligibility",
        "address_validation_status",
        "phone_validation_status",
        "import_batch_id",
    ):
        op.drop_index(f"ix_prospects_{column}", table_name="prospects")
    op.drop_constraint("fk_prospects_import_batch_id", "prospects", type_="foreignkey")
    op.drop_column("prospects", "call_eligibility")
    op.drop_column("prospects", "address_validation_status")
    op.drop_column("prospects", "phone_validation_status")
    op.drop_column("prospects", "import_batch_id")

    op.drop_table("prospect_import_rows")
    op.drop_table("prospect_import_batches")
    op.drop_table("prospect_import_mappings")
