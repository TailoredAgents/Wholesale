"""Phase AI5 Prospecting Copilot and call quality.

Revision ID: 0045_prospecting_copilot
Revises: 0044_lead_manager_copilot
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0045_prospecting_copilot"
down_revision: str | None = "0044_lead_manager_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROSPECTING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pre_call_summary": {"type": "string"},
        "priority_explanation": {"type": "string"},
        "property_context": {"type": "array", "items": {"type": "string"}},
        "prior_attempt_context": {"type": "array", "items": {"type": "string"}},
        "opening_guidance": {"type": "string"},
        "required_questions": {"type": "array", "items": {"type": "string"}},
        "disposition_guidance": {"type": "array", "items": {"type": "string"}},
        "data_quality_warnings": {"type": "array", "items": {"type": "string"}},
        "compliance_reminders": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "pre_call_summary",
        "priority_explanation",
        "property_context",
        "prior_attempt_context",
        "opening_guidance",
        "required_questions",
        "disposition_guidance",
        "data_quality_warnings",
        "compliance_reminders",
        "evidence",
        "confidence",
    ],
}
CALL_QUALITY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "call_summary": {"type": "string"},
        "suggested_disposition": {
            "type": "string",
            "enum": [
                "no_answer",
                "left_voicemail",
                "callback_requested",
                "follow_up",
                "interested",
                "appointment_set",
                "not_interested",
                "wrong_number",
                "do_not_call",
            ],
        },
        "disposition_reason": {"type": "string"},
        "callback_recommendation": {"type": "string"},
        "handoff_draft": {"type": "string"},
        "script_adherence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "qualification_completeness_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "objection_handling_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "data_quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "handoff_quality_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "coaching_points": {"type": "array", "items": {"type": "string"}},
        "compliance_flags": {"type": "array", "items": {"type": "string"}},
        "evidence_timestamps": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "call_summary",
        "suggested_disposition",
        "disposition_reason",
        "callback_recommendation",
        "handoff_draft",
        "script_adherence_score",
        "qualification_completeness_score",
        "objection_handling_score",
        "data_quality_score",
        "handoff_quality_score",
        "coaching_points",
        "compliance_flags",
        "evidence_timestamps",
        "confidence",
    ],
}
LEGACY_PROSPECTING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ranked_lead_ids": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ranked_lead_ids", "rationale"],
}


def upgrade() -> None:
    op.create_table(
        "prospecting_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("batch_entry_id", sa.Uuid(), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("generated_for_user_id", sa.Uuid(), nullable=False),
        sa.Column("ai_run_log_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("priority_band", sa.String(40), nullable=False),
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
        sa.ForeignKeyConstraint(["ai_run_log_id"], ["ai_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["batch_entry_id"],
            ["prospect_calling_batch_entries.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["generated_for_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_prospecting_copilot_org_idempotency",
        ),
    )
    for column in (
        "organization_id",
        "batch_entry_id",
        "prospect_id",
        "generated_for_user_id",
        "ai_run_log_id",
        "status",
    ):
        op.create_index(
            f"ix_prospecting_copilot_recommendations_{column}",
            "prospecting_copilot_recommendations",
            [column],
        )
    op.create_index(
        "ix_prospecting_copilot_org_status",
        "prospecting_copilot_recommendations",
        ["organization_id", "status"],
    )

    op.create_table(
        "prospecting_copilot_reviews",
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
            ["prospecting_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_prospecting_copilot_review_recommendation",
        ),
    )
    for column in (
        "organization_id",
        "recommendation_id",
        "reviewed_by_user_id",
        "decision",
    ):
        op.create_index(
            f"ix_prospecting_copilot_reviews_{column}",
            "prospecting_copilot_reviews",
            [column],
        )

    op.create_table(
        "prospecting_call_quality_reviews",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("call_record_id", sa.Uuid()),
        sa.Column("transcript_id", sa.Uuid()),
        sa.Column("ai_run_log_id", sa.Uuid()),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("deterministic_scores", sa.JSON(), nullable=False),
        sa.Column("ai_output", sa.JSON()),
        sa.Column("final_output", sa.JSON()),
        sa.Column("compliance_flags", sa.JSON(), nullable=False),
        sa.Column(
            "escalation_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("reviewed_by_user_id", sa.Uuid()),
        sa.Column("review_notes", sa.String(2000)),
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
        sa.ForeignKeyConstraint(["ai_run_log_id"], ["ai_run_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["attempt_id"], ["prospecting_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["call_record_id"], ["call_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["caller_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transcript_id"], ["call_transcripts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            name="uq_prospecting_call_quality_attempt",
        ),
    )
    for column in (
        "organization_id",
        "attempt_id",
        "caller_user_id",
        "call_record_id",
        "transcript_id",
        "ai_run_log_id",
        "status",
    ):
        op.create_index(
            f"ix_prospecting_call_quality_reviews_{column}",
            "prospecting_call_quality_reviews",
            [column],
        )
    op.create_index(
        "ix_prospecting_call_quality_org_status",
        "prospecting_call_quality_reviews",
        ["organization_id", "status"],
    )
    _update_priority_schema(PROSPECTING_SCHEMA)
    _install_quality_capability()


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        bind.execute(
            sa.text(
                "DELETE FROM ai_capability_runtime_policies "
                "WHERE capability_key = 'call.quality_coach'"
            )
        )
    _update_priority_schema(LEGACY_PROSPECTING_SCHEMA)
    op.drop_table("prospecting_call_quality_reviews")
    op.drop_table("prospecting_copilot_reviews")
    op.drop_table("prospecting_copilot_recommendations")


def _update_priority_schema(schema: dict[str, object]) -> None:
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("output_schema", sa.JSON()),
    )
    serialized = json.dumps(schema, separators=(",", ":"))
    value = sa.cast(sa.literal(serialized), sa.JSON()) if op.get_context().as_sql else schema
    op.execute(
        policies.update()
        .where(policies.c.capability_key == "prospecting.prioritize")
        .values(output_schema=value)
    )


def _install_quality_capability() -> None:
    if op.get_context().as_sql:
        return
    bind = op.get_bind()
    agents = sa.table(
        "ai_agent_definitions",
        sa.column("id", sa.Uuid()),
        sa.column("organization_id", sa.Uuid()),
        sa.column("rollback_owner_user_id", sa.Uuid()),
        sa.column("key", sa.String()),
    )
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("organization_id", sa.Uuid()),
        sa.column("agent_definition_id", sa.Uuid()),
        sa.column("capability_key", sa.String()),
        sa.column("status", sa.String()),
        sa.column("model_route", sa.String()),
        sa.column("output_schema", sa.JSON()),
        sa.column("allowed_tool_keys", sa.JSON()),
        sa.column("allowed_knowledge_keys", sa.JSON()),
        sa.column("max_output_tokens", sa.Integer()),
        sa.column("max_cost_microusd_per_run", sa.BigInteger()),
        sa.column("requires_human_review", sa.Boolean()),
        sa.column("updated_by_user_id", sa.Uuid()),
        sa.column("id", sa.Uuid()),
    )
    rows = bind.execute(
        sa.select(
            agents.c.id,
            agents.c.organization_id,
            agents.c.rollback_owner_user_id,
        ).where(agents.c.key == "call_intelligence")
    ).all()
    for agent_id, organization_id, owner_user_id in rows:
        existing = bind.execute(
            sa.select(policies.c.id).where(
                policies.c.organization_id == organization_id,
                policies.c.capability_key == "call.quality_coach",
            )
        ).first()
        if existing:
            continue
        bind.execute(
            policies.insert().values(
                organization_id=organization_id,
                agent_definition_id=agent_id,
                capability_key="call.quality_coach",
                status="disabled",
                model_route="escalation",
                output_schema=CALL_QUALITY_SCHEMA,
                allowed_tool_keys=["call.summarize.read"],
                allowed_knowledge_keys=[
                    "operating_model",
                    "prospecting_scripts",
                    "ai_agent_policy",
                ],
                max_output_tokens=1600,
                max_cost_microusd_per_run=100_000,
                requires_human_review=True,
                updated_by_user_id=owner_user_id,
                id=uuid.uuid4(),
            )
        )
