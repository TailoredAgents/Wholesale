"""Add governed conversion experiments and variant attribution.

Revision ID: 0072_conversion_experiments
Revises: 0071_public_trust_proof
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_conversion_experiments"
down_revision: str | None = "0071_public_trust_proof"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketing_experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("experiment_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("hypothesis", sa.String(1000), nullable=False),
        sa.Column("surface_key", sa.String(80), nullable=False),
        sa.Column("primary_metric", sa.String(80), nullable=False),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column(
            "minimum_sessions_per_variant",
            sa.Integer(),
            server_default="50",
            nullable=False,
        ),
        sa.Column(
            "minimum_runtime_days",
            sa.Integer(),
            server_default="14",
            nullable=False,
        ),
        sa.Column("decision_rule", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(40), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "accumulated_runtime_seconds",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_notes", sa.String(2000), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'running', 'paused', 'completed')",
            name="ck_marketing_experiments_status",
        ),
        sa.CheckConstraint(
            "primary_metric IN "
            "('form_submit', 'qualified_lead', 'appointment_scheduled', "
            "'contract_signed', 'funded_deal')",
            name="ck_marketing_experiments_primary_metric",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "experiment_key",
            name="uq_marketing_experiments_org_key",
        ),
    )
    op.create_index(
        "ix_marketing_experiments_organization_id",
        "marketing_experiments",
        ["organization_id"],
    )
    op.create_index(
        "ix_marketing_experiments_surface_key",
        "marketing_experiments",
        ["surface_key"],
    )
    op.create_index(
        "ix_marketing_experiments_status",
        "marketing_experiments",
        ["status"],
    )

    op.create_table(
        "marketing_experiment_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(120), nullable=False),
        sa.Column("variant_key", sa.String(80), nullable=False),
        sa.Column(
            "device_category",
            sa.String(20),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["experiment_id"], ["marketing_experiments.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "experiment_id",
            "session_id",
            name="uq_marketing_experiment_assignments_session",
        ),
    )
    for column in (
        "organization_id",
        "experiment_id",
        "session_id",
        "variant_key",
        "lead_id",
    ):
        op.create_index(
            f"ix_marketing_experiment_assignments_{column}",
            "marketing_experiment_assignments",
            [column],
        )

    op.add_column(
        "conversion_events",
        sa.Column("experiment_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column("experiment_variant", sa.String(80), nullable=True),
    )
    op.add_column(
        "conversion_events",
        sa.Column(
            "device_category",
            sa.String(20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_conversion_events_experiment_id",
        "conversion_events",
        "marketing_experiments",
        ["experiment_id"],
        ["id"],
    )
    op.create_index(
        "ix_conversion_events_experiment_id",
        "conversion_events",
        ["experiment_id"],
    )
    op.create_index(
        "ix_conversion_events_experiment_variant",
        "conversion_events",
        ["experiment_variant"],
    )
    op.create_index(
        "ix_conversion_events_device_category",
        "conversion_events",
        ["device_category"],
    )


def downgrade() -> None:
    for column in (
        "device_category",
        "experiment_variant",
        "experiment_id",
    ):
        op.drop_index(f"ix_conversion_events_{column}", table_name="conversion_events")
    op.drop_constraint(
        "fk_conversion_events_experiment_id",
        "conversion_events",
        type_="foreignkey",
    )
    op.drop_column("conversion_events", "device_category")
    op.drop_column("conversion_events", "experiment_variant")
    op.drop_column("conversion_events", "experiment_id")

    for column in (
        "lead_id",
        "variant_key",
        "session_id",
        "experiment_id",
        "organization_id",
    ):
        op.drop_index(
            f"ix_marketing_experiment_assignments_{column}",
            table_name="marketing_experiment_assignments",
        )
    op.drop_table("marketing_experiment_assignments")
    op.drop_index(
        "ix_marketing_experiments_status",
        table_name="marketing_experiments",
    )
    op.drop_index(
        "ix_marketing_experiments_surface_key",
        table_name="marketing_experiments",
    )
    op.drop_index(
        "ix_marketing_experiments_organization_id",
        table_name="marketing_experiments",
    )
    op.drop_table("marketing_experiments")
