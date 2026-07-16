"""underwriting market analyses

Revision ID: 0016_underwriting_market_analyses
Revises: 0015_ai_control_center
Create Date: 2026-07-16 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_underwriting_market_analyses"
down_revision: str | None = "0015_ai_control_center"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "underwriting_market_analyses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("underwriting_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("requested_address", sa.String(length=500), nullable=False),
        sa.Column("estimated_value_cents", sa.BigInteger(), nullable=True),
        sa.Column("estimated_value_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("estimated_value_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("arv_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("repair_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("repair_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("mao_low_cents", sa.BigInteger(), nullable=True),
        sa.Column("mao_high_cents", sa.BigInteger(), nullable=True),
        sa.Column("recommended_offer_cents", sa.BigInteger(), nullable=True),
        sa.Column("assignment_fee_cents", sa.BigInteger(), nullable=True),
        sa.Column("offer_low_percentage", sa.Integer(), nullable=False),
        sa.Column("offer_high_percentage", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("selected_comp_count", sa.Integer(), nullable=False),
        sa.Column("rejected_comp_count", sa.Integer(), nullable=False),
        sa.Column("selected_comps", sa.JSON(), nullable=False),
        sa.Column("rejected_comps", sa.JSON(), nullable=False),
        sa.Column("subject_property", sa.JSON(), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["underwriting_version_id"], ["underwriting_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_underwriting_market_analyses_organization_id",
        "underwriting_market_analyses",
        ["organization_id"],
    )
    op.create_index(
        "ix_underwriting_market_analyses_lead_id",
        "underwriting_market_analyses",
        ["lead_id"],
    )
    op.create_index(
        "ix_underwriting_market_analyses_property_id",
        "underwriting_market_analyses",
        ["property_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_underwriting_market_analyses_property_id",
        table_name="underwriting_market_analyses",
    )
    op.drop_index(
        "ix_underwriting_market_analyses_lead_id",
        table_name="underwriting_market_analyses",
    )
    op.drop_index(
        "ix_underwriting_market_analyses_organization_id",
        table_name="underwriting_market_analyses",
    )
    op.drop_table("underwriting_market_analyses")
