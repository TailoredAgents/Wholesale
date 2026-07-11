"""duplicate detection

Revision ID: 0004_duplicate_detection
Revises: 0003_public_intake_records
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_duplicate_detection"
down_revision: str | None = "0003_public_intake_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column("properties", sa.Column("normalized_address_key", sa.String(500), nullable=True))
    op.create_index(
        "ix_properties_org_normalized_address_key",
        "properties",
        ["organization_id", "normalized_address_key"],
    )

    op.create_table(
        "contact_methods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("method_type", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=320), nullable=False),
        sa.Column("normalized_value", sa.String(length=320), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        *timestamp_columns(),
    )
    op.create_index("ix_contact_methods_organization_id", "contact_methods", ["organization_id"])
    op.create_index("ix_contact_methods_contact_id", "contact_methods", ["contact_id"])
    op.create_index(
        "ix_contact_methods_org_type_normalized",
        "contact_methods",
        ["organization_id", "method_type", "normalized_value"],
    )


def downgrade() -> None:
    op.drop_table("contact_methods")
    op.drop_index("ix_properties_org_normalized_address_key", table_name="properties")
    op.drop_column("properties", "normalized_address_key")
