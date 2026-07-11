"""public intake records

Revision ID: 0003_public_intake_records
Revises: 0002_rbac_permissions
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_public_intake_records"
down_revision: str | None = "0002_rbac_permissions"
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
    op.create_table(
        "consent_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("wording_version", sa.String(length=80), nullable=False),
        sa.Column("wording", sa.String(length=1000), nullable=False),
        sa.Column("captured_ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        *timestamp_columns(),
    )
    op.create_index("ix_consent_records_organization_id", "consent_records", ["organization_id"])
    op.create_index("ix_consent_records_contact_id", "consent_records", ["contact_id"])

    op.create_table(
        "lead_form_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("landing_page", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        *timestamp_columns(),
    )
    op.create_index(
        "ix_lead_form_submissions_organization_id",
        "lead_form_submissions",
        ["organization_id"],
    )

    op.create_table(
        "attribution_touches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("touch_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("medium", sa.String(length=120), nullable=True),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("term", sa.String(length=255), nullable=True),
        sa.Column("content", sa.String(length=255), nullable=True),
        sa.Column("gclid", sa.String(length=255), nullable=True),
        sa.Column("fbclid", sa.String(length=255), nullable=True),
        sa.Column("landing_page", sa.String(length=255), nullable=True),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        *timestamp_columns(),
    )
    op.create_index(
        "ix_attribution_touches_organization_id", "attribution_touches", ["organization_id"]
    )
    op.create_index("ix_attribution_touches_lead_id", "attribution_touches", ["lead_id"])


def downgrade() -> None:
    op.drop_table("attribution_touches")
    op.drop_table("lead_form_submissions")
    op.drop_table("consent_records")
