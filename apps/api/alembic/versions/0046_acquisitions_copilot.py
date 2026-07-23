"""Phase AI6 Acquisitions Copilot.

Revision ID: 0046_acquisitions_copilot
Revises: 0045_prospecting_copilot
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_acquisitions_copilot"
down_revision: str | None = "0045_prospecting_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OBJECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "objection": {"type": "string"},
        "response_guidance": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["objection", "response_guidance", "evidence"],
}
PREPARATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_brief": {"type": "string"},
        "seller_goals": {"type": "array", "items": {"type": "string"}},
        "meeting_objectives": {"type": "array", "items": {"type": "string"}},
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        "walkthrough_focus": {"type": "array", "items": {"type": "string"}},
        "underwriting_explanation": {"type": "array", "items": {"type": "string"}},
        "comp_review_questions": {"type": "array", "items": {"type": "string"}},
        "repair_evidence_gaps": {"type": "array", "items": {"type": "string"}},
        "negotiation_questions": {"type": "array", "items": {"type": "string"}},
        "objection_guidance": {"type": "array", "items": OBJECTION_SCHEMA},
        "authority_reminders": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "executive_brief",
        "seller_goals",
        "meeting_objectives",
        "unresolved_questions",
        "walkthrough_focus",
        "underwriting_explanation",
        "comp_review_questions",
        "repair_evidence_gaps",
        "negotiation_questions",
        "objection_guidance",
        "authority_reminders",
        "risks",
        "evidence",
        "confidence",
    ],
}
FOLLOW_UP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "meeting_summary": {"type": "string"},
        "seller_position": {"type": "array", "items": {"type": "string"}},
        "confirmed_facts": {"type": "array", "items": {"type": "string"}},
        "unresolved_items": {"type": "array", "items": {"type": "string"}},
        "objection_review": {"type": "array", "items": OBJECTION_SCHEMA},
        "authority_status": {"type": "string"},
        "recommended_internal_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "seller_follow_up_draft": {"type": "string"},
        "missing_documentation": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "meeting_summary",
        "seller_position",
        "confirmed_facts",
        "unresolved_items",
        "objection_review",
        "authority_status",
        "recommended_internal_actions",
        "seller_follow_up_draft",
        "missing_documentation",
        "risks",
        "evidence",
        "confidence",
    ],
}
LEGACY_SCHEMA = {
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


def upgrade() -> None:
    op.create_table(
        "acquisitions_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_type", sa.String(40), nullable=False),
        sa.Column("field_meeting_brief_id", sa.Uuid()),
        sa.Column("field_inspection_id", sa.Uuid()),
        sa.Column("field_negotiation_session_id", sa.Uuid()),
        sa.Column("underwriting_version_id", sa.Uuid()),
        sa.Column("offer_negotiation_plan_id", sa.Uuid()),
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
        sa.ForeignKeyConstraint(
            ["ai_run_log_id"], ["ai_run_logs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"], ["appointments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["field_inspection_id"], ["field_inspections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["field_meeting_brief_id"],
            ["field_meeting_briefs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["field_negotiation_session_id"],
            ["field_negotiation_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["generated_for_user_id"], ["users.id"]
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["offer_negotiation_plan_id"],
            ["offer_negotiation_plans.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["underwriting_version_id"],
            ["underwriting_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_acquisitions_copilot_org_idempotency",
        ),
    )
    for name, column in (
        ("ix_acq_copilot_appointment", "appointment_id"),
        ("ix_acq_copilot_lead", "lead_id"),
        ("ix_acq_copilot_type", "recommendation_type"),
        ("ix_acq_copilot_brief", "field_meeting_brief_id"),
        ("ix_acq_copilot_inspection", "field_inspection_id"),
        ("ix_acq_copilot_negotiation", "field_negotiation_session_id"),
        ("ix_acq_copilot_underwriting", "underwriting_version_id"),
        ("ix_acq_copilot_offer_plan", "offer_negotiation_plan_id"),
        ("ix_acq_copilot_assignee", "generated_for_user_id"),
        ("ix_acq_copilot_run", "ai_run_log_id"),
    ):
        op.create_index(name, "acquisitions_copilot_recommendations", [column])
    op.create_index(
        "ix_acquisitions_copilot_org_status",
        "acquisitions_copilot_recommendations",
        ["organization_id", "status"],
    )

    op.create_table(
        "acquisitions_copilot_reviews",
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
            ["acquisitions_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_acquisitions_copilot_review_recommendation",
        ),
    )
    for name, column in (
        ("ix_acq_copilot_review_org", "organization_id"),
        ("ix_acq_copilot_review_recommendation", "recommendation_id"),
        ("ix_acq_copilot_reviewer", "reviewed_by_user_id"),
        ("ix_acq_copilot_review_decision", "decision"),
    ):
        op.create_index(name, "acquisitions_copilot_reviews", [column])

    _update_capability_schema("appointment.brief", PREPARATION_SCHEMA)
    _update_capability_schema("negotiation.coach", FOLLOW_UP_SCHEMA)


def downgrade() -> None:
    _update_capability_schema("appointment.brief", LEGACY_SCHEMA)
    _update_capability_schema("negotiation.coach", LEGACY_SCHEMA)
    op.drop_table("acquisitions_copilot_reviews")
    op.drop_table("acquisitions_copilot_recommendations")


def _update_capability_schema(
    capability_key: str,
    schema: dict[str, object],
) -> None:
    policies = sa.table(
        "ai_capability_runtime_policies",
        sa.column("capability_key", sa.String()),
        sa.column("output_schema", sa.JSON()),
    )
    serialized = json.dumps(schema, separators=(",", ":"))
    value = (
        sa.cast(sa.literal(serialized), sa.JSON())
        if op.get_context().as_sql
        else schema
    )
    op.execute(
        policies.update()
        .where(policies.c.capability_key == capability_key)
        .values(output_schema=value)
    )
