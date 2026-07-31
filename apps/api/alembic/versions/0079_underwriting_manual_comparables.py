"""Add verified manual comparable evidence.

Revision ID: 0079_underwriting_manual_comps
Revises: 0078_tasks_primary_actions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0079_underwriting_manual_comps"
down_revision: str | None = "0078_tasks_primary_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_manual_comparables",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("street_address", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("formatted_address", sa.String(length=500), nullable=False),
        sa.Column("normalized_address_key", sa.String(length=500), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("sale_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("property_type", sa.String(length=80), nullable=False),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("bathrooms_hundredths", sa.Integer(), nullable=True),
        sa.Column("square_footage", sa.Integer(), nullable=False),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("distance_hundredths", sa.Integer(), nullable=True),
        sa.Column("subdivision", sa.String(length=255), nullable=True),
        sa.Column(
            "condition_classification",
            sa.String(length=40),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("condition_evidence", sa.String(length=1000), nullable=True),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("verification_notes", sa.String(length=2000), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "lead_id",
        "property_id",
        "status",
        "normalized_address_key",
        "sale_date",
        "source_type",
    ):
        op.create_index(
            f"ix_underwriting_manual_comparables_{column}",
            "underwriting_manual_comparables",
            [column],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("underwriting_manual_comparables")
