"""Persist business-visible lead close-out metadata.

Revision ID: 0095_lead_close_out_metadata
Revises: 0094_esign_send_intents
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0095_lead_close_out_metadata"
down_revision: str | None = "0094_esign_send_intents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("close_out_disposition", sa.String(40), nullable=True))
    op.add_column("leads", sa.Column("close_out_reason", sa.String(500), nullable=True))
    op.add_column("leads", sa.Column("closed_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "leads",
        sa.Column(
            "closed_out_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_leads_closed_out_at", "leads", ["closed_out_at"])
    terminal_leads = "SELECT id FROM leads WHERE stage_key IN ('dead', 'disqualified')"
    legacy_reason = "Legacy terminal lead reconciled into the close-out workflow."
    op.execute(
        sa.text(
            "UPDATE leads SET "
            "archived_at = COALESCE(archived_at, updated_at, created_at, CURRENT_TIMESTAMP), "
            "close_out_disposition = stage_key, "
            "close_out_reason = :legacy_reason, "
            "closed_out_at = COALESCE(archived_at, updated_at, created_at, CURRENT_TIMESTAMP), "
            "appointment_status = CASE "
            "WHEN appointment_status IN ('appointment_requested', 'needs_scheduling', "
            "'scheduled', 'rescheduled', 'confirmed') THEN 'cancelled' "
            "ELSE appointment_status END, "
            "next_follow_up_at = NULL "
            "WHERE stage_key IN ('dead', 'disqualified')"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE tasks SET status = 'cancelled', "
            "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP), "
            "outcome = 'lead_closed_out', completion_notes = :legacy_reason "
            f"WHERE lead_id IN ({terminal_leads}) AND status IN ('open', 'in_progress')"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE calendar_events SET status = 'cancelled' WHERE appointment_id IN ("
            "SELECT id FROM appointments "
            f"WHERE lead_id IN ({terminal_leads}) "
            "AND status IN ('scheduled', 'rescheduled'))"
        )
    )
    op.execute(
        sa.text(
            "UPDATE appointments SET status = 'cancelled', outcome = :legacy_reason "
            f"WHERE lead_id IN ({terminal_leads}) "
            "AND status IN ('scheduled', 'rescheduled')"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE follow_up_enrollments "
            "SET status = 'cancelled:' || CAST(id AS VARCHAR), "
            "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
            f"WHERE lead_id IN ({terminal_leads}) AND status = 'active'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE approval_requests SET status = 'cancelled', "
            "decision_notes = :legacy_reason, decided_at = CURRENT_TIMESTAMP "
            "WHERE status = 'pending' AND ("
            f"(entity_type = 'lead' AND entity_id IN ({terminal_leads})) OR "
            "(request_type IN ('offer_ceiling', 'offer_concession') "
            "AND entity_id IN (SELECT id FROM offer_negotiation_plans "
            f"WHERE lead_id IN ({terminal_leads}))) OR "
            "(request_type = 'offer_concession' AND entity_id IN ("
            "SELECT id FROM offer_concessions "
            f"WHERE lead_id IN ({terminal_leads}))) OR "
            "(request_type = 'contract_send' AND entity_id IN ("
            "SELECT contract_packages.id FROM contract_packages "
            "JOIN transactions ON transactions.id = contract_packages.transaction_id "
            f"WHERE transactions.lead_id IN ({terminal_leads}))) OR "
            "EXISTS (SELECT 1 FROM leads WHERE leads.stage_key IN ('dead', 'disqualified') "
            "AND CAST(approval_requests.metadata AS TEXT) LIKE "
            "'%' || CAST(leads.id AS VARCHAR) || '%'))"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE offer_negotiation_plans SET status = 'cancelled' "
            f"WHERE lead_id IN ({terminal_leads}) AND status IN ('pending', 'approved')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE offer_concessions SET status = 'cancelled', "
            "decision_notes = :legacy_reason, decided_at = CURRENT_TIMESTAMP "
            f"WHERE lead_id IN ({terminal_leads}) "
            "AND status IN ('pending', 'authorized', 'approved')"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE voice_call_intents SET status = 'cancelled' "
            f"WHERE lead_id IN ({terminal_leads}) AND status IN ('pending', 'started')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE prospect_calling_batch_entries SET status = 'completed', "
            "completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) WHERE id IN ("
            "SELECT prospecting_attempts.batch_entry_id FROM prospecting_attempts "
            "JOIN prospect_handoffs ON prospect_handoffs.attempt_id = prospecting_attempts.id "
            f"WHERE prospect_handoffs.lead_id IN ({terminal_leads}) "
            "AND prospect_handoffs.status = 'pending')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE prospect_handoffs SET status = 'cancelled', "
            "reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP), "
            "decision_code = COALESCE(decision_code, 'rejected_other'), "
            "review_reason = COALESCE(review_reason, :legacy_reason) "
            f"WHERE lead_id IN ({terminal_leads}) AND status = 'pending'"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE calling_list_entries SET status = 'completed', "
            "disposition = (SELECT stage_key FROM leads "
            "WHERE leads.id = calling_list_entries.lead_id), "
            "notes = :legacy_reason, completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) "
            f"WHERE lead_id IN ({terminal_leads}) AND status != 'completed'"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE lead_management_cases SET status = 'closed', "
            "closed_at = COALESCE(closed_at, CURRENT_TIMESTAMP), "
            "next_action_type = NULL, next_action_due_at = NULL "
            f"WHERE lead_id IN ({terminal_leads})"
        )
    )
    op.execute(
        sa.text(
            "UPDATE conversations SET status = 'closed', queue_key = 'closed', unread_count = 0, "
            "closed_at = COALESCE(closed_at, CURRENT_TIMESTAMP) "
            f"WHERE lead_id IN ({terminal_leads})"
        )
    )
    op.execute(
        sa.text(
            "UPDATE ai_orchestrator_events SET status = 'dismissed', "
            "processed_at = COALESCE(processed_at, CURRENT_TIMESTAMP), "
            "last_error = :legacy_reason WHERE entity_type = 'lead' "
            f"AND entity_id IN ({terminal_leads}) "
            "AND status IN ('queued', 'processing', 'needs_review')"
        ).bindparams(legacy_reason=legacy_reason)
    )
    op.execute(
        sa.text(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE read_at IS NULL AND ("
            f"(entity_type = 'lead' AND entity_id IN ({terminal_leads})) OR "
            "(entity_type = 'task' AND entity_id IN (SELECT id FROM tasks "
            f"WHERE lead_id IN ({terminal_leads}))) OR "
            "(entity_type = 'appointment' AND entity_id IN (SELECT id FROM appointments "
            f"WHERE lead_id IN ({terminal_leads}))) OR "
            "(entity_type = 'lead_management_case' AND entity_id IN ("
            f"SELECT id FROM lead_management_cases WHERE lead_id IN ({terminal_leads}))) OR "
            "(entity_type = 'conversation' AND entity_id IN (SELECT id FROM conversations "
            f"WHERE lead_id IN ({terminal_leads}))) OR "
            "(entity_type = 'prospect_handoff' AND entity_id IN (SELECT id FROM prospect_handoffs "
            f"WHERE lead_id IN ({terminal_leads}))))"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_leads_closed_out_at", table_name="leads")
    op.drop_column("leads", "closed_out_by_user_id")
    op.drop_column("leads", "closed_out_at")
    op.drop_column("leads", "close_out_reason")
    op.drop_column("leads", "close_out_disposition")
