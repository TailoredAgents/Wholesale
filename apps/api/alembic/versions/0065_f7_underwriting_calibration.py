"""Add governed underwriting calibration decisions.

Revision ID: 0065_f7_underwriting_calibration
Revises: 0064_f6g_marketing_measurement
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0065_f7_underwriting_calibration"
down_revision: str | None = "0064_f6g_marketing_measurement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_calibration_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by_user_id", sa.Uuid()),
        sa.Column("decided_by_user_id", sa.Uuid()),
        sa.Column("scope_key", sa.String(255), nullable=False),
        sa.Column("decision_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("rationale", sa.String(3000), nullable=False),
        sa.Column("current_methodology_version", sa.String(80)),
        sa.Column("proposed_methodology_version", sa.String(80)),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("minimum_sample_required", sa.Integer(), nullable=False),
        sa.Column("decision_notes", sa.String(2000)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
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
        sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_underwriting_calibration_decisions_organization_id",
        "underwriting_calibration_decisions",
        ["organization_id"],
    )
    op.create_index(
        "ix_underwriting_calibration_decisions_status",
        "underwriting_calibration_decisions",
        ["status"],
    )
    op.create_index(
        "ix_underwriting_calibration_decisions_org_scope",
        "underwriting_calibration_decisions",
        ["organization_id", "scope_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_underwriting_calibration_decisions_org_scope",
        table_name="underwriting_calibration_decisions",
    )
    op.drop_index(
        "ix_underwriting_calibration_decisions_status",
        table_name="underwriting_calibration_decisions",
    )
    op.drop_index(
        "ix_underwriting_calibration_decisions_organization_id",
        table_name="underwriting_calibration_decisions",
    )
    op.drop_table("underwriting_calibration_decisions")
