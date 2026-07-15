"""appointments

Revision ID: 0009_appointments
Revises: 0008_communication_records
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_appointments"
down_revision: str | None = "0008_communication_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("appointment_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_type", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("outcome", sa.String(length=1000), nullable=True),
        sa.Column("external_calendar_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appointments_organization_id", "appointments", ["organization_id"])
    op.create_index("ix_appointments_lead_id", "appointments", ["lead_id"])
    op.create_index("ix_appointments_contact_id", "appointments", ["contact_id"])
    op.create_index("ix_appointments_property_id", "appointments", ["property_id"])


def downgrade() -> None:
    op.drop_index("ix_appointments_property_id", table_name="appointments")
    op.drop_index("ix_appointments_contact_id", table_name="appointments")
    op.drop_index("ix_appointments_lead_id", table_name="appointments")
    op.drop_index("ix_appointments_organization_id", table_name="appointments")
    op.drop_table("appointments")
