"""Add the F6 accounting and tax foundation.

Revision ID: 0059_f6_accounting_tax
Revises: 0058_signwell_provider_setup
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_f6_accounting_tax"
down_revision: str | None = "0058_signwell_provider_setup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounting_profiles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_name", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("federal_tax_classification", sa.String(80), nullable=False),
        sa.Column("accounting_method", sa.String(40), nullable=False),
        sa.Column("tax_year_end_month", sa.Integer(), nullable=False),
        sa.Column("tax_year_end_day", sa.Integer(), nullable=False),
        sa.Column("books_start_date", sa.Date()),
        sa.Column("home_state", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("owner_compensation_treatment", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("tax_rule_year", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(2000)),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            name="uq_accounting_profiles_organization",
        ),
    )
    op.create_index(
        "ix_accounting_profiles_organization_id",
        "accounting_profiles",
        ["organization_id"],
    )
    op.create_index(
        "ix_accounting_profiles_status",
        "accounting_profiles",
        ["status"],
    )

    op.create_table(
        "accounting_accounts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("accounting_profile_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("system_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(40), nullable=False),
        sa.Column("subtype", sa.String(80), nullable=False),
        sa.Column("normal_balance", sa.String(10), nullable=False),
        sa.Column("tax_category", sa.String(120), nullable=False),
        sa.Column("deal_tracking", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["accounting_profile_id"],
            ["accounting_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "policy_version",
            "code",
            name="uq_accounting_accounts_org_version_code",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "policy_version",
            "system_key",
            name="uq_accounting_accounts_org_version_key",
        ),
    )
    op.create_index(
        "ix_accounting_accounts_organization_id",
        "accounting_accounts",
        ["organization_id"],
    )
    op.create_index(
        "ix_accounting_accounts_accounting_profile_id",
        "accounting_accounts",
        ["accounting_profile_id"],
    )
    op.create_index(
        "ix_accounting_accounts_org_type",
        "accounting_accounts",
        ["organization_id", "account_type", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("accounting_accounts")
    op.drop_table("accounting_profiles")
