"""Phase AI8 Disposition Copilot and buyer intelligence foundation.

Revision ID: 0050_disposition_copilot
Revises: 0049_enable_completed_copilots
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0050_disposition_copilot"
down_revision: str | None = "0049_enable_completed_copilots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STRING_ARRAY = {"type": "array", "items": {"type": "string"}}
BUYER_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "buyer_id": {"type": "string"},
        "buyer_name": {"type": "string"},
        "recommendation": {
            "type": "string",
            "enum": ["priority", "backup", "hold", "exclude"],
        },
        "rationale": STRING_ARRAY,
        "risks": STRING_ARRAY,
        "evidence": STRING_ARRAY,
    },
    "required": [
        "buyer_id",
        "buyer_name",
        "recommendation",
        "rationale",
        "risks",
        "evidence",
    ],
}
OFFER_COMPARISON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "offer_id": {"type": "string"},
        "buyer_name": {"type": "string"},
        "strength": {
            "type": "string",
            "enum": ["strong", "acceptable", "weak", "ineligible"],
        },
        "rationale": STRING_ARRAY,
        "risks": STRING_ARRAY,
    },
    "required": ["offer_id", "buyer_name", "strength", "rationale", "risks"],
}
DISPOSITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status_summary": {"type": "string"},
        "package_gaps": STRING_ARRAY,
        "package_highlights": STRING_ARRAY,
        "recommended_buyers": {
            "type": "array",
            "items": BUYER_RECOMMENDATION_SCHEMA,
        },
        "offer_comparison": {
            "type": "array",
            "items": OFFER_COMPARISON_SCHEMA,
        },
        "buyer_outreach_subject": {"type": "string"},
        "buyer_outreach_body": {"type": "string"},
        "recommended_internal_actions": STRING_ARRAY,
        "relationship_update_proposals": STRING_ARRAY,
        "risk_alerts": STRING_ARRAY,
        "uncertainties": STRING_ARRAY,
        "evidence": STRING_ARRAY,
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "status_summary",
        "package_gaps",
        "package_highlights",
        "recommended_buyers",
        "offer_comparison",
        "buyer_outreach_subject",
        "buyer_outreach_body",
        "recommended_internal_actions",
        "relationship_update_proposals",
        "risk_alerts",
        "uncertainties",
        "evidence",
        "confidence",
    ],
}


def upgrade() -> None:
    op.create_table(
        "disposition_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("disposition_case_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["disposition_case_id"],
            ["disposition_cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
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
            name="uq_disposition_copilot_org_idempotency",
        ),
    )
    op.create_index(
        "ix_disposition_copilot_case",
        "disposition_copilot_recommendations",
        ["disposition_case_id"],
    )
    op.create_index(
        "ix_disposition_copilot_transaction",
        "disposition_copilot_recommendations",
        ["transaction_id"],
    )
    op.create_index(
        "ix_disposition_copilot_run",
        "disposition_copilot_recommendations",
        ["ai_run_log_id"],
    )
    op.create_index(
        "ix_disposition_copilot_org_status",
        "disposition_copilot_recommendations",
        ["organization_id", "status"],
    )

    op.create_table(
        "disposition_copilot_reviews",
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
            ["disposition_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_disposition_copilot_review_recommendation",
        ),
    )
    op.create_index(
        "ix_disposition_copilot_review_org",
        "disposition_copilot_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_disposition_copilot_review_recommendation",
        "disposition_copilot_reviews",
        ["recommendation_id"],
    )
    op.create_index(
        "ix_disposition_copilot_reviewer",
        "disposition_copilot_reviews",
        ["reviewed_by_user_id"],
    )

    op.execute(
        sa.text(
            """
            UPDATE ai_capability_runtime_policies
            SET status = 'enabled',
                output_schema = CAST(:output_schema AS JSON),
                requires_human_review = true
            WHERE capability_key = 'disposition.match'
            """
        ).bindparams(
            sa.bindparam(
                "output_schema",
                json.dumps(DISPOSITION_SCHEMA),
                type_=sa.String(),
            )
        )
    )


def downgrade() -> None:
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
    )
    op.execute(
        policies.update()
        .where(policies.c.capability_key == "disposition.match")
        .values(status="disabled")
    )
    op.drop_table("disposition_copilot_reviews")
    op.drop_table("disposition_copilot_recommendations")
