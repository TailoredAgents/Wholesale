"""foundation

Revision ID: 0001_foundation
Revises:
Create Date: 2026-07-10 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def create_timestamp_columns() -> list[sa.Column]:
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
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *create_timestamp_columns(),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("external_auth_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *create_timestamp_columns(),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *create_timestamp_columns(),
        sa.UniqueConstraint("organization_id", "key", name="uq_roles_org_key"),
    )

    op.create_table(
        "role_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id"), nullable=False),
        *create_timestamp_columns(),
        sa.UniqueConstraint("user_id", "role_id", name="uq_role_assignments_user_role"),
    )

    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("preferred_name", sa.String(length=255), nullable=True),
        sa.Column("contact_type", sa.String(length=80), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        *create_timestamp_columns(),
    )
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])

    op.create_table(
        "properties",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("street_address", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("county", sa.String(length=120), nullable=True),
        sa.Column("property_type", sa.String(length=80), nullable=True),
        *create_timestamp_columns(),
    )
    op.create_index("ix_properties_organization_id", "properties", ["organization_id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("property_id", sa.Uuid(), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("stage_key", sa.String(length=120), nullable=False),
        sa.Column("lead_temperature", sa.String(length=80), nullable=True),
        *create_timestamp_columns(),
    )
    op.create_index("ix_leads_organization_id", "leads", ["organization_id"])

    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("property_id", sa.Uuid(), sa.ForeignKey("properties.id"), nullable=False),
        sa.Column("stage_key", sa.String(length=120), nullable=False),
        sa.Column("contract_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("assignment_fee_cents", sa.BigInteger(), nullable=True),
        *create_timestamp_columns(),
    )
    op.create_index("ix_deals_organization_id", "deals", ["organization_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("responsible_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.String(length=80), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        *create_timestamp_columns(),
    )
    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"])

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_activity_events_organization_id", "activity_events", ["organization_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_type", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("activity_events")
    op.drop_table("tasks")
    op.drop_table("deals")
    op.drop_table("leads")
    op.drop_table("properties")
    op.drop_table("contacts")
    op.drop_table("role_assignments")
    op.drop_table("roles")
    op.drop_table("users")
    op.drop_table("organizations")
