"""Phase AI4 Lead Manager Copilot.

Revision ID: 0044_lead_manager_copilot
Revises: 0043_ai_production_runtime
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0044_lead_manager_copilot"
down_revision: str | None = "0043_ai_production_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEAD_MANAGER_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "priority_explanation": {"type": "string"},
        "qualification_gaps": {"type": "array", "items": {"type": "string"}},
        "recommended_questions": {"type": "array", "items": {"type": "string"}},
        "message_draft": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "channel": {"type": "string", "enum": ["none", "sms", "email"]},
                "body": {"type": "string"},
            },
            "required": ["channel", "body"],
        },
        "next_task": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "reason": {"type": "string"},
                "due_timing": {"type": "string"},
            },
            "required": ["title", "reason", "due_timing"],
        },
        "appointment_proposal": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "recommended": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["recommended", "reason"],
        },
        "handoff_summary": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "summary",
        "priority_explanation",
        "qualification_gaps",
        "recommended_questions",
        "message_draft",
        "next_task",
        "appointment_proposal",
        "handoff_summary",
        "risks",
        "evidence",
        "confidence",
    ],
}
LEGACY_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "requires_human_approval": {"type": "boolean"},
                },
                "required": [
                    "action",
                    "reason",
                    "confidence",
                    "evidence",
                    "requires_human_approval",
                ],
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "knowledge_citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_key": {"type": "string"},
                    "version": {"type": "integer"},
                    "checksum": {"type": "string"},
                },
                "required": ["source_key", "version", "checksum"],
            },
        },
    },
    "required": [
        "summary",
        "recommended_actions",
        "risks",
        "uncertainties",
        "knowledge_citations",
    ],
}


def _update_lead_manager_schema(schema: dict[str, object]) -> None:
    serialized = json.dumps(schema, separators=(",", ":"))
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("output_schema", sa.JSON()),
    )
    value = (
        sa.cast(sa.literal(serialized), sa.JSON())
        if op.get_context().as_sql
        else schema
    )
    op.execute(
        policies.update()
        .where(policies.c.capability_key == "lead.next_action")
        .values(output_schema=value)
    )


def upgrade() -> None:
    op.create_table(
        "lead_manager_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_log_id", sa.Uuid()),
        sa.Column("generated_for_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("priority_band", sa.String(40), nullable=False),
        sa.Column("model_name", sa.String(120)),
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
        sa.ForeignKeyConstraint(
            ["ai_run_log_id"], ["ai_run_logs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["lead_management_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["generated_for_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_lead_manager_copilot_org_idempotency",
        ),
    )
    for column in (
        "organization_id",
        "case_id",
        "lead_id",
        "ai_run_log_id",
        "generated_for_user_id",
        "status",
    ):
        op.create_index(
            f"ix_lead_manager_copilot_recommendations_{column}",
            "lead_manager_copilot_recommendations",
            [column],
        )
    op.create_index(
        "ix_lead_manager_copilot_org_status",
        "lead_manager_copilot_recommendations",
        ["organization_id", "status"],
    )

    op.create_table(
        "lead_manager_copilot_reviews",
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
            ["lead_manager_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_lead_manager_copilot_review_recommendation",
        ),
    )
    for column in (
        "organization_id",
        "recommendation_id",
        "reviewed_by_user_id",
        "decision",
    ):
        op.create_index(
            f"ix_lead_manager_copilot_reviews_{column}",
            "lead_manager_copilot_reviews",
            [column],
        )
    _update_lead_manager_schema(LEAD_MANAGER_OUTPUT_SCHEMA)


def downgrade() -> None:
    _update_lead_manager_schema(LEGACY_OUTPUT_SCHEMA)
    op.drop_table("lead_manager_copilot_reviews")
    op.drop_table("lead_manager_copilot_recommendations")
