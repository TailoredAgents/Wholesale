"""Phase F2 company configuration and role acceptance.

Revision ID: 0053_company_config
Revises: 0052_ai10_action_controls
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0053_company_config"
down_revision: str | None = "0052_ai10_action_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operating_seats",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("seat_key", sa.String(120), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("primary_user_id", sa.Uuid()),
        sa.Column("backup_user_id", sa.Uuid()),
        sa.Column("notes", sa.String(1000)),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["primary_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["backup_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "seat_key",
            name="uq_operating_seats_org_key",
        ),
    )
    op.create_index("ix_operating_seats_organization_id", "operating_seats", ["organization_id"])
    op.create_index("ix_operating_seats_role_key", "operating_seats", ["role_key"])
    op.create_index("ix_operating_seats_status", "operating_seats", ["status"])

    op.create_table(
        "business_counterparties",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid()),
        sa.Column("counterparty_type", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(40)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("verified_by_user_id", sa.Uuid()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.String(2000)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_counterparties_organization_id",
        "business_counterparties",
        ["organization_id"],
    )
    op.create_index(
        "ix_business_counterparties_market_id",
        "business_counterparties",
        ["market_id"],
    )
    op.create_index(
        "ix_business_counterparties_counterparty_type",
        "business_counterparties",
        ["counterparty_type"],
    )
    op.create_index(
        "ix_business_counterparties_status",
        "business_counterparties",
        ["status"],
    )

    op.create_table(
        "staff_role_acceptances",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("manual_key", sa.String(160), nullable=False),
        sa.Column("manual_version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_test_evidence", sa.String(2000)),
        sa.Column("employee_notes", sa.String(2000)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("manager_notes", sa.String(2000)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            "role_key",
            "manual_key",
            "manual_version",
            name="uq_staff_role_acceptance_assignment",
        ),
    )
    op.create_index(
        "ix_staff_role_acceptances_organization_id",
        "staff_role_acceptances",
        ["organization_id"],
    )
    op.create_index("ix_staff_role_acceptances_user_id", "staff_role_acceptances", ["user_id"])
    op.create_index("ix_staff_role_acceptances_role_key", "staff_role_acceptances", ["role_key"])
    op.create_index("ix_staff_role_acceptances_status", "staff_role_acceptances", ["status"])


def downgrade() -> None:
    op.drop_index("ix_staff_role_acceptances_status", table_name="staff_role_acceptances")
    op.drop_index("ix_staff_role_acceptances_role_key", table_name="staff_role_acceptances")
    op.drop_index("ix_staff_role_acceptances_user_id", table_name="staff_role_acceptances")
    op.drop_index(
        "ix_staff_role_acceptances_organization_id",
        table_name="staff_role_acceptances",
    )
    op.drop_table("staff_role_acceptances")
    op.drop_index("ix_business_counterparties_status", table_name="business_counterparties")
    op.drop_index(
        "ix_business_counterparties_counterparty_type",
        table_name="business_counterparties",
    )
    op.drop_index("ix_business_counterparties_market_id", table_name="business_counterparties")
    op.drop_index(
        "ix_business_counterparties_organization_id",
        table_name="business_counterparties",
    )
    op.drop_table("business_counterparties")
    op.drop_index("ix_operating_seats_status", table_name="operating_seats")
    op.drop_index("ix_operating_seats_role_key", table_name="operating_seats")
    op.drop_index("ix_operating_seats_organization_id", table_name="operating_seats")
    op.drop_table("operating_seats")
