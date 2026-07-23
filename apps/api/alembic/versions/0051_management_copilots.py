"""Phase AI9 finance, marketing, and executive copilot foundation.

Revision ID: 0051_management_copilots
Revises: 0050_disposition_copilot
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_management_copilots"
down_revision: str | None = "0050_disposition_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STRING_ARRAY = {"type": "array", "items": {"type": "string"}}
FACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string"},
        "value": {"type": "string"},
        "evidence": STRING_ARRAY,
    },
    "required": ["label", "value", "evidence"],
}
EXCEPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "severity": {
            "type": "string",
            "enum": ["info", "warning", "critical"],
        },
        "category": {"type": "string"},
        "title": {"type": "string"},
        "detail": {"type": "string"},
        "evidence": STRING_ARRAY,
    },
    "required": ["severity", "category", "title", "detail", "evidence"],
}
ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {"type": "string"},
        "subject": {"type": "string"},
        "signal": {
            "type": "string",
            "enum": ["positive", "neutral", "warning", "critical"],
        },
        "analysis": {"type": "string"},
        "evidence": STRING_ARRAY,
    },
    "required": ["category", "subject", "signal", "analysis", "evidence"],
}
ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string"},
        "reason": {"type": "string"},
        "owner": {"type": "string"},
        "workspace": {
            "type": "string",
            "enum": [
                "dashboard",
                "finance",
                "marketing",
                "operations",
                "dispositions",
                "transactions",
                "ai",
            ],
        },
        "evidence": STRING_ARRAY,
        "requires_human_decision": {"type": "boolean", "const": True},
    },
    "required": [
        "action",
        "reason",
        "owner",
        "workspace",
        "evidence",
        "requires_human_decision",
    ],
}
DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string"},
        "why_now": {"type": "string"},
        "options": STRING_ARRAY,
        "evidence": STRING_ARRAY,
    },
    "required": ["decision", "why_now", "options", "evidence"],
}
MANAGEMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "brief": {"type": "string"},
        "confirmed_facts": {"type": "array", "items": FACT_SCHEMA},
        "exceptions": {"type": "array", "items": EXCEPTION_SCHEMA},
        "analysis": {"type": "array", "items": ANALYSIS_SCHEMA},
        "draft_actions": {"type": "array", "items": ACTION_SCHEMA},
        "decision_requests": {"type": "array", "items": DECISION_SCHEMA},
        "uncertainties": STRING_ARRAY,
        "evidence": STRING_ARRAY,
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "brief",
        "confirmed_facts",
        "exceptions",
        "analysis",
        "draft_actions",
        "decision_requests",
        "uncertainties",
        "evidence",
        "confidence",
    ],
}


def upgrade() -> None:
    op.create_table(
        "management_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("capability_key", sa.String(120), nullable=False),
        sa.Column("reporting_period_days", sa.Integer(), nullable=False),
        sa.Column("generated_for_user_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_log_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("output_payload", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("confidence_score", sa.Integer()),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
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
        sa.ForeignKeyConstraint(["generated_for_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["ai_run_log_id"],
            ["ai_run_logs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_management_copilot_org_idempotency",
        ),
    )
    op.create_index(
        "ix_management_copilot_org_capability_status",
        "management_copilot_recommendations",
        ["organization_id", "capability_key", "status"],
    )
    op.create_index(
        "ix_management_copilot_run",
        "management_copilot_recommendations",
        ["ai_run_log_id"],
    )

    op.create_table(
        "management_copilot_reviews",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("original_output", sa.JSON(), nullable=False),
        sa.Column("final_output", sa.JSON()),
        sa.Column("notes", sa.String(2000)),
        sa.Column(
            "estimated_time_saved_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["management_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_management_copilot_review_recommendation",
        ),
    )
    op.create_index(
        "ix_management_copilot_review_org",
        "management_copilot_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_management_copilot_reviewer",
        "management_copilot_reviews",
        ["reviewed_by_user_id"],
    )

    op.execute(
        sa.text(
            """
            UPDATE ai_capability_runtime_policies
            SET status = 'enabled',
                output_schema = CAST(:output_schema AS JSON),
                requires_human_review = true
            WHERE capability_key IN (
                'finance.reconcile',
                'marketing.analyze',
                'operations.brief'
            )
            """
        ).bindparams(
            sa.bindparam(
                "output_schema",
                json.dumps(MANAGEMENT_SCHEMA),
                type_=sa.String(),
            )
        )
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE ai_capability_runtime_policies
        SET status = 'disabled'
        WHERE capability_key IN (
            'finance.reconcile',
            'marketing.analyze',
            'operations.brief'
        )
        """
    )
    op.drop_table("management_copilot_reviews")
    op.drop_table("management_copilot_recommendations")
