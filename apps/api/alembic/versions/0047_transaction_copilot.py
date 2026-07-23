"""Phase AI7 Transaction Copilot and document intelligence foundation.

Revision ID: 0047_transaction_copilot
Revises: 0046_acquisitions_copilot
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_transaction_copilot"
down_revision: str | None = "0046_acquisitions_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEADLINE_RISK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "item": {"type": "string"},
        "due_at": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["info", "warning", "critical"],
        },
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["item", "due_at", "severity", "reason", "evidence"],
}
DOCUMENT_FINDING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "finding": {"type": "string"},
        "document_id": {"type": ["string", "null"]},
        "source_page": {"type": ["integer", "null"], "minimum": 1},
        "evidence": {"type": "string"},
    },
    "required": ["finding", "document_id", "source_page", "evidence"],
}
TRANSACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status_summary": {"type": "string"},
        "missing_items": {"type": "array", "items": {"type": "string"}},
        "deadline_risks": {
            "type": "array",
            "items": DEADLINE_RISK_SCHEMA,
        },
        "document_findings": {
            "type": "array",
            "items": DOCUMENT_FINDING_SCHEMA,
        },
        "party_gaps": {"type": "array", "items": {"type": "string"}},
        "recommended_internal_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "closing_attorney_email_draft": {"type": "string"},
        "seller_email_draft": {"type": "string"},
        "legal_escalations": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": [
        "status_summary",
        "missing_items",
        "deadline_risks",
        "document_findings",
        "party_gaps",
        "recommended_internal_actions",
        "closing_attorney_email_draft",
        "seller_email_draft",
        "legal_escalations",
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
        "transaction_document_facts",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("field_key", sa.String(120), nullable=False),
        sa.Column("value_text", sa.String(2000), nullable=False),
        sa.Column("source_page", sa.Integer()),
        sa.Column("source_excerpt", sa.String(1000)),
        sa.Column("extraction_method", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confidence_score", sa.Integer()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid()),
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
            ["transaction_id"], ["transactions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["transaction_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_document_facts_transaction",
        "transaction_document_facts",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_document_facts_document",
        "transaction_document_facts",
        ["document_id"],
    )
    op.create_index(
        "ix_transaction_document_facts_field",
        "transaction_document_facts",
        ["field_key"],
    )
    op.create_index(
        "ix_transaction_document_facts_status",
        "transaction_document_facts",
        ["organization_id", "status"],
    )

    op.create_table(
        "transaction_copilot_recommendations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
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
            ["transaction_id"], ["transactions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["generated_for_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["ai_run_log_id"], ["ai_run_logs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_transaction_copilot_org_idempotency",
        ),
    )
    op.create_index(
        "ix_transaction_copilot_transaction",
        "transaction_copilot_recommendations",
        ["transaction_id"],
    )
    op.create_index(
        "ix_transaction_copilot_lead",
        "transaction_copilot_recommendations",
        ["lead_id"],
    )
    op.create_index(
        "ix_transaction_copilot_run",
        "transaction_copilot_recommendations",
        ["ai_run_log_id"],
    )
    op.create_index(
        "ix_transaction_copilot_org_status",
        "transaction_copilot_recommendations",
        ["organization_id", "status"],
    )

    op.create_table(
        "transaction_copilot_reviews",
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
            ["transaction_copilot_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_transaction_copilot_review_recommendation",
        ),
    )
    op.create_index(
        "ix_transaction_copilot_review_org",
        "transaction_copilot_reviews",
        ["organization_id"],
    )
    op.create_index(
        "ix_transaction_copilot_review_recommendation",
        "transaction_copilot_reviews",
        ["recommendation_id"],
    )
    op.create_index(
        "ix_transaction_copilot_reviewer",
        "transaction_copilot_reviews",
        ["reviewed_by_user_id"],
    )
    _update_capability_schema(TRANSACTION_SCHEMA)


def downgrade() -> None:
    _update_capability_schema(LEGACY_SCHEMA)
    op.drop_table("transaction_copilot_reviews")
    op.drop_table("transaction_copilot_recommendations")
    op.drop_table("transaction_document_facts")


def _update_capability_schema(schema: dict[str, object]) -> None:
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
        .where(policies.c.capability_key == "transaction.coordinate")
        .values(output_schema=value)
    )
