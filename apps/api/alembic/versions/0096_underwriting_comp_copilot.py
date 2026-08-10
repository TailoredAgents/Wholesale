"""Add persistent evidence-grounded underwriting Comp Copilot threads.

Revision ID: 0096_underwriting_comp_copilot
Revises: 0095_lead_close_out_metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0096_underwriting_comp_copilot"
down_revision: str | None = "0095_lead_close_out_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underwriting_comp_copilot_threads",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("market_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["market_analysis_id"],
            ["underwriting_market_analyses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "market_analysis_id",
            name="uq_underwriting_comp_copilot_analysis",
        ),
    )
    op.create_index(
        "ix_underwriting_comp_copilot_threads_organization_id",
        "underwriting_comp_copilot_threads",
        ["organization_id"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_threads_lead_id",
        "underwriting_comp_copilot_threads",
        ["lead_id"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_threads_market_analysis_id",
        "underwriting_comp_copilot_threads",
        ["market_analysis_id"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_threads_status",
        "underwriting_comp_copilot_threads",
        ["status"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_threads_last_message_at",
        "underwriting_comp_copilot_threads",
        ["last_message_at"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_lead",
        "underwriting_comp_copilot_threads",
        ["organization_id", "lead_id"],
    )

    op.create_table(
        "underwriting_comp_copilot_messages",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("suggested_actions", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("used_ai", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["underwriting_comp_copilot_threads.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_underwriting_comp_copilot_messages_organization_id",
        "underwriting_comp_copilot_messages",
        ["organization_id"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_messages_thread_id",
        "underwriting_comp_copilot_messages",
        ["thread_id"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_message_thread",
        "underwriting_comp_copilot_messages",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "ix_underwriting_comp_copilot_message_org",
        "underwriting_comp_copilot_messages",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("underwriting_comp_copilot_messages")
    op.drop_table("underwriting_comp_copilot_threads")
