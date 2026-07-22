"""Versioned compensation, role credits, disposition modes, and market launch controls.

Revision ID: 0031_operating_controls
Revises: 0030_operating_model_foundation
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0031_operating_controls"
down_revision: str | None = "0030_operating_model_foundation"
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
    _create_compensation_tables()
    _create_market_launch_tables()
    _link_existing_finance_and_transaction_tables()


def _create_compensation_tables() -> None:
    op.create_table(
        "compensation_plan_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("acquisition_reserve_cents", sa.BigInteger(), nullable=False),
        sa.Column("target_company_margin_basis_points", sa.Integer(), nullable=False),
        sa.Column("effective_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "name",
            "version_number",
            name="uq_compensation_plan_versions_org_name_version",
        ),
    )
    _indexes("compensation_plan_versions", "organization_id", "status")

    op.create_table(
        "compensation_plan_roles",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("basis_points", sa.Integer(), nullable=False),
        sa.Column("cap_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["compensation_plan_version_id"],
            ["compensation_plan_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "compensation_plan_version_id",
            "role_key",
            name="uq_compensation_plan_roles_plan_role",
        ),
    )
    _indexes("compensation_plan_roles", "organization_id", "compensation_plan_version_id")

    op.create_table(
        "disposition_operating_modes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("human_share_min_basis_points", sa.Integer(), nullable=False),
        sa.Column("human_share_max_basis_points", sa.Integer(), nullable=False),
        sa.Column("expected_company_share_min_basis_points", sa.Integer(), nullable=False),
        sa.Column("expected_company_share_max_basis_points", sa.Integer(), nullable=False),
        sa.Column("ai_authority_level", sa.String(80), nullable=False),
        sa.Column("activation_requirements", sa.JSON(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["compensation_plan_version_id"],
            ["compensation_plan_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "compensation_plan_version_id",
            "key",
            name="uq_disposition_operating_modes_plan_key",
        ),
    )
    _indexes(
        "disposition_operating_modes",
        "organization_id",
        "compensation_plan_version_id",
        "status",
    )

    op.create_table(
        "role_credits",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("transaction_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("credit_basis_points", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["compensation_plan_version_id"], ["compensation_plan_versions.id"]
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _indexes(
        "role_credits",
        "organization_id",
        "compensation_plan_version_id",
        "lead_id",
        "deal_id",
        "transaction_id",
        "user_id",
        "role_key",
        "status",
    )


def _create_market_launch_tables() -> None:
    op.create_table(
        "market_launch_checklists",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_id",
            "version_number",
            name="uq_market_launch_checklists_market_version",
        ),
    )
    _indexes("market_launch_checklists", "organization_id", "market_id", "status")

    op.create_table(
        "market_launch_checklist_items",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("market_launch_checklist_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_notes", sa.String(2000), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        id_column(),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["market_launch_checklist_id"],
            ["market_launch_checklists.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_launch_checklist_id",
            "item_key",
            name="uq_market_launch_checklist_items_checklist_key",
        ),
    )
    _indexes(
        "market_launch_checklist_items",
        "organization_id",
        "market_launch_checklist_id",
        "status",
    )


def _link_existing_finance_and_transaction_tables() -> None:
    op.add_column(
        "transactions",
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("disposition_operating_mode_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_transactions_compensation_plan_version_id",
        "transactions",
        "compensation_plan_versions",
        ["compensation_plan_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_transactions_disposition_operating_mode_id",
        "transactions",
        "disposition_operating_modes",
        ["disposition_operating_mode_id"],
        ["id"],
    )
    op.create_index(
        "ix_transactions_compensation_plan_version_id",
        "transactions",
        ["compensation_plan_version_id"],
    )
    op.create_index(
        "ix_transactions_disposition_operating_mode_id",
        "transactions",
        ["disposition_operating_mode_id"],
    )

    op.add_column(
        "compensation_rules",
        sa.Column("compensation_plan_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "compensation_rules",
        sa.Column("compensation_plan_role_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_compensation_rules_plan_version_id",
        "compensation_rules",
        "compensation_plan_versions",
        ["compensation_plan_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_compensation_rules_plan_role_id",
        "compensation_rules",
        "compensation_plan_roles",
        ["compensation_plan_role_id"],
        ["id"],
    )
    op.create_index(
        "ix_compensation_rules_compensation_plan_version_id",
        "compensation_rules",
        ["compensation_plan_version_id"],
    )
    op.create_index(
        "ix_compensation_rules_compensation_plan_role_id",
        "compensation_rules",
        ["compensation_plan_role_id"],
    )


def _indexes(table_name: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table_name}_{column}", table_name, [column])


def downgrade() -> None:
    op.drop_index(
        "ix_compensation_rules_compensation_plan_role_id",
        table_name="compensation_rules",
    )
    op.drop_index(
        "ix_compensation_rules_compensation_plan_version_id",
        table_name="compensation_rules",
    )
    op.drop_constraint(
        "fk_compensation_rules_plan_role_id", "compensation_rules", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_compensation_rules_plan_version_id", "compensation_rules", type_="foreignkey"
    )
    op.drop_column("compensation_rules", "compensation_plan_role_id")
    op.drop_column("compensation_rules", "compensation_plan_version_id")

    op.drop_index(
        "ix_transactions_disposition_operating_mode_id",
        table_name="transactions",
    )
    op.drop_index(
        "ix_transactions_compensation_plan_version_id",
        table_name="transactions",
    )
    op.drop_constraint(
        "fk_transactions_disposition_operating_mode_id", "transactions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_transactions_compensation_plan_version_id", "transactions", type_="foreignkey"
    )
    op.drop_column("transactions", "disposition_operating_mode_id")
    op.drop_column("transactions", "compensation_plan_version_id")

    op.drop_table("market_launch_checklist_items")
    op.drop_table("market_launch_checklists")
    op.drop_table("role_credits")
    op.drop_table("disposition_operating_modes")
    op.drop_table("compensation_plan_roles")
    op.drop_table("compensation_plan_versions")
