import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import Principal, principal_for_user
from app.core.config import Settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    ActivityEvent,
    AiCapabilityRuntimePolicy,
    AiOrchestratorEvent,
    AiRunLog,
    AuditEvent,
    CommunicationRecord,
    Lead,
    Role,
    RoleAssignment,
    User,
)
from app.schemas.ai import AiRuntimeExecuteCreate
from app.schemas.tasks import AiOperationReviewRead, AiOperationReviewRequest

SUPPORTED_EVENT_CAPABILITIES = {
    "lead.created": "lead.next_action",
    "property.research_ready": "lead.next_action",
}
ACTIVE_EVENT_STATUSES = {"queued", "processing", "needs_review"}
TERMINAL_EVENT_STATUSES = {"completed", "failed", "blocked", "dismissed"}
OPERATIONS_ROLE_PRIORITY = {
    "acquisition_manager": 0,
    "acquisition_rep": 1,
    "owner": 2,
    "founder_operator": 3,
    "ceo": 4,
}


def enqueue_lead_created_ai_work(
    db: Session,
    lead: Lead,
    *,
    source: str,
) -> AiOrchestratorEvent:
    event_key = f"lead.created:{lead.id}"
    existing = db.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.organization_id == lead.organization_id,
            AiOrchestratorEvent.event_key == event_key,
        )
    )
    if existing is not None:
        return existing

    assigned_user_id = lead.assigned_user_id or default_ai_work_owner(db, lead.organization_id)
    now = datetime.now(UTC)
    event = AiOrchestratorEvent(
        organization_id=lead.organization_id,
        event_key=event_key,
        event_type="lead.created",
        entity_type="lead",
        entity_id=lead.id,
        status="queued",
        payload={
            "capability_key": "lead.next_action",
            "title": "Review AI lead brief",
            "summary": "Stonegate is preparing the seller summary and recommended next action.",
            "priority": "high",
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "source_url": f"/os/leads/{lead.id}",
            "due_at": (now + timedelta(minutes=5)).isoformat(),
            "trigger_source": source,
            "attempt_count": 0,
        },
        occurred_at=now,
        processed_at=None,
        last_error=None,
    )
    db.add(event)
    db.flush()
    return event


def enqueue_property_research_ai_work(
    db: Session,
    *,
    lead: Lead,
    snapshot_id: UUID,
) -> AiOrchestratorEvent:
    event_key = f"property.research_ready:{snapshot_id}:{lead.id}"
    existing = db.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.organization_id == lead.organization_id,
            AiOrchestratorEvent.event_key == event_key,
        )
    )
    if existing is not None:
        return existing
    assigned_user_id = lead.assigned_user_id or default_ai_work_owner(db, lead.organization_id)
    now = datetime.now(UTC)
    event = AiOrchestratorEvent(
        organization_id=lead.organization_id,
        event_key=event_key,
        event_type="property.research_ready",
        entity_type="lead",
        entity_id=lead.id,
        status="queued",
        payload={
            "capability_key": "lead.next_action",
            "title": "Review researched lead brief",
            "summary": "Stonegate is updating the lead brief with saved property intelligence.",
            "priority": "high",
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "source_url": f"/os/leads/{lead.id}?tab=property",
            "due_at": now.isoformat(),
            "trigger_source": "property_research",
            "property_intelligence_snapshot_id": str(snapshot_id),
            "attempt_count": 0,
        },
        occurred_at=now,
        processed_at=None,
        last_error=None,
    )
    db.add(event)
    db.flush()
    return event


def enqueue_call_intelligence_ai_work(
    db: Session,
    *,
    transcript_id: UUID,
    lead: Lead,
    actor_user_id: UUID | None,
    conversation_id: UUID | None,
) -> AiOrchestratorEvent:
    event_key = f"call.notes:{transcript_id}"
    existing = db.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.organization_id == lead.organization_id,
            AiOrchestratorEvent.event_key == event_key,
        )
    )
    if existing is not None:
        return existing
    assigned_user_id = (
        actor_user_id or lead.assigned_user_id or default_ai_work_owner(db, lead.organization_id)
    )
    now = datetime.now(UTC)
    source_url = (
        f"/os/inbox?conversation={conversation_id}" if conversation_id else f"/os/leads/{lead.id}"
    )
    event = AiOrchestratorEvent(
        organization_id=lead.organization_id,
        event_key=event_key,
        event_type="call.notes.ready",
        entity_type="lead",
        entity_id=lead.id,
        status="processing",
        payload={
            "capability_key": "call.summarize",
            "title": "Review AI call notes",
            "summary": "Stonegate is transcribing the call and preparing structured seller notes.",
            "priority": "high",
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "source_url": source_url,
            "due_at": now.isoformat(),
            "transcript_id": str(transcript_id),
            "attempt_count": 1,
        },
        occurred_at=now,
        processed_at=None,
        last_error=None,
    )
    db.add(event)
    db.flush()
    return event


def mark_call_intelligence_ai_work(
    db: Session,
    *,
    event_id: UUID,
    status: str,
    run_id: UUID | None,
    summary: str | None = None,
    approval_request_id: UUID | None = None,
    error_message: str | None = None,
) -> None:
    event = db.get(AiOrchestratorEvent, event_id)
    if event is None:
        return
    payload = dict(event.payload or {})
    if run_id is not None:
        payload["run_id"] = str(run_id)
    if approval_request_id is not None:
        payload["approval_request_id"] = str(approval_request_id)
    if summary:
        payload["summary"] = summary[:2000]
    event.payload = payload
    event.status = status
    event.processed_at = datetime.now(UTC)
    event.last_error = error_message[:2000] if error_message else None


def mark_call_intelligence_reviewed(
    db: Session,
    *,
    run_id: UUID | None,
    decision: str,
    reviewer_user_id: UUID,
) -> None:
    if run_id is None:
        return
    run = db.get(AiRunLog, run_id)
    if run is None or run.orchestrator_event_id is None:
        return
    event = db.get(AiOrchestratorEvent, run.orchestrator_event_id)
    if event is None:
        return
    event.status = "completed"
    event.processed_at = datetime.now(UTC)
    event.payload = {
        **(event.payload or {}),
        "review_outcome": decision,
        "reviewed_by_user_id": str(reviewer_user_id),
        "reviewed_at": datetime.now(UTC).isoformat(),
    }


def process_next_ai_operation(
    db: Session,
    _settings: Settings,
) -> UUID | None:
    from app.services.ai_runtime import execute_runtime

    stale_before = datetime.now(UTC) - timedelta(minutes=15)
    event = db.scalar(
        select(AiOrchestratorEvent)
        .where(
            AiOrchestratorEvent.event_type.in_(SUPPORTED_EVENT_CAPABILITIES),
            or_(
                AiOrchestratorEvent.status == "queued",
                (
                    (AiOrchestratorEvent.status == "processing")
                    & (AiOrchestratorEvent.updated_at < stale_before)
                ),
            ),
        )
        .order_by(AiOrchestratorEvent.occurred_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return None

    event.status = "processing"
    event.last_error = None
    event.payload = {
        **(event.payload or {}),
        "attempt_count": int((event.payload or {}).get("attempt_count", 0)) + 1,
        "processing_started_at": datetime.now(UTC).isoformat(),
    }
    db.commit()
    event_id = event.id

    try:
        event = db.get(AiOrchestratorEvent, event_id)
        if event is None or event.entity_type != "lead" or event.entity_id is None:
            raise ValueError("AI operations event is missing its seller lead.")
        lead = db.get(Lead, event.entity_id)
        if lead is None or lead.archived_at is not None:
            raise ValueError("The seller lead is no longer available.")
        assigned_user_id = payload_uuid((event.payload or {}).get("assigned_user_id"))
        assigned_user = db.get(User, assigned_user_id) if assigned_user_id is not None else None
        if assigned_user is None or not assigned_user.is_active:
            fallback_id = lead.assigned_user_id or default_ai_work_owner(db, event.organization_id)
            assigned_user = db.get(User, fallback_id) if fallback_id else None
        if assigned_user is None or not assigned_user.is_active:
            raise ValueError("No active Stonegate user is available to own this AI work.")

        principal = principal_for_user(db, assigned_user)
        capability_key = SUPPORTED_EVENT_CAPABILITIES[event.event_type]
        capability = db.scalar(
            select(AiCapabilityRuntimePolicy).where(
                AiCapabilityRuntimePolicy.organization_id == event.organization_id,
                AiCapabilityRuntimePolicy.capability_key == capability_key,
            )
        )
        if capability is None:
            raise ValueError("The Lead Manager AI capability is not installed.")

        run = execute_runtime(
            db,
            principal,
            AiRuntimeExecuteCreate(
                agent_definition_id=capability.agent_definition_id,
                capability_key=capability_key,
                idempotency_key=f"ai-operations:{event.id}:v1",
                input_payload={
                    "trigger_event": event.event_type,
                    "instruction": (
                        "Prepare a concise seller brief, qualification gaps, and the next "
                        "recommended human action. Do not contact the seller."
                    ),
                },
                lead_id=lead.id,
                orchestrator_event_id=event.id,
            ),
        )
        event = db.get(AiOrchestratorEvent, event_id)
        if event is None:
            return event_id
        event.status = normalize_run_status(run.status)
        event.processed_at = datetime.now(UTC)
        event.last_error = run.error_message
        event.payload = {
            **(event.payload or {}),
            "assigned_user_id": str(assigned_user.id),
            "run_id": str(run.id),
            "processing_completed_at": datetime.now(UTC).isoformat(),
        }
        db.add(
            ActivityEvent(
                organization_id=event.organization_id,
                actor_user_id=None,
                entity_type="lead",
                entity_id=lead.id,
                event_type=f"ai_operations.{event.status}",
                summary=(
                    "AI lead brief is ready for review."
                    if event.status == "needs_review"
                    else f"AI lead preparation finished with status {event.status}."
                ),
            )
        )
        db.commit()
        return event_id
    except Exception as exc:
        db.rollback()
        event = db.get(AiOrchestratorEvent, event_id)
        if event is not None:
            event.status = "failed"
            event.processed_at = datetime.now(UTC)
            event.last_error = str(exc)[:2000]
            event.payload = {
                **(event.payload or {}),
                "processing_failed_at": datetime.now(UTC).isoformat(),
            }
            db.commit()
        return event_id


def review_ai_operation(
    db: Session,
    principal: Principal,
    event_id: UUID,
    payload: AiOperationReviewRequest,
) -> AiOperationReviewRead | None:
    event = db.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.organization_id == principal.organization_id,
            AiOrchestratorEvent.id == event_id,
        )
    )
    if event is None:
        return None
    if event.status != "needs_review":
        raise ValueError("This AI work item is no longer awaiting review.")
    if event.event_type not in SUPPORTED_EVENT_CAPABILITIES or event.entity_id is None:
        raise ValueError("Open the source workspace to review this AI result.")
    lead = db.get(Lead, event.entity_id)
    if lead is None:
        raise ValueError("The source seller lead is unavailable.")
    if not can_review_event(principal, event, lead):
        raise PermissionError("This AI work item is not assigned to you.")
    run = db.scalar(
        select(AiRunLog)
        .where(
            AiRunLog.organization_id == principal.organization_id,
            AiRunLog.orchestrator_event_id == event.id,
        )
        .order_by(AiRunLog.created_at.desc())
    )
    if run is None:
        raise ValueError("The AI result is unavailable.")

    reviewed_at = datetime.now(UTC)
    event.status = "completed"
    event.processed_at = reviewed_at
    event.payload = {
        **(event.payload or {}),
        "review_outcome": payload.decision,
        "review_notes": payload.notes,
        "reviewed_by_user_id": str(principal.user_id),
        "reviewed_at": reviewed_at.isoformat(),
    }
    run.status = payload.decision
    run.trace_status = "reviewed"
    run.trace_reviewed_by_user_id = principal.user_id
    run.trace_reviewed_at = reviewed_at
    run.trace_review_notes = payload.notes or f"AI work {payload.decision}."

    if payload.decision == "accepted":
        record_approved_lead_brief(db, principal, lead, event, run)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=f"ai_operations.{payload.decision}",
            summary=f"AI lead brief {payload.decision} after human review.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="ai_operations.review",
            entity_type="ai_orchestrator_event",
            entity_id=event.id,
            previous_value={"status": "needs_review"},
            new_value={"status": "completed", "outcome": payload.decision},
            reason=payload.notes or "Human review of AI lead preparation",
        )
    )
    db.commit()
    return AiOperationReviewRead(
        event_id=event.id,
        run_id=run.id,
        status=event.status,
        outcome=payload.decision,
        reviewed_at=reviewed_at,
    )


def record_approved_lead_brief(
    db: Session,
    principal: Principal,
    lead: Lead,
    event: AiOrchestratorEvent,
    run: AiRunLog,
) -> None:
    from app.services.inbox import ensure_primary_conversation

    provider_message_id = f"ai-operations:{event.id}"
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == principal.organization_id,
            CommunicationRecord.provider == "openai_reviewed",
            CommunicationRecord.provider_message_id == provider_message_id,
        )
    )
    if existing is not None:
        return
    conversation = ensure_primary_conversation(db, lead)
    db.add(
        CommunicationRecord(
            organization_id=principal.organization_id,
            conversation_id=conversation.id,
            lead_id=lead.id,
            contact_id=lead.contact_id,
            actor_user_id=principal.user_id,
            direction="internal",
            channel="note",
            status="logged",
            provider="openai_reviewed",
            provider_message_id=provider_message_id,
            subject="Approved AI lead brief",
            body=format_ai_output(run.output_summary),
            occurred_at=datetime.now(UTC),
            external_payload=None,
            communication_metadata={
                "ai_run_id": str(run.id),
                "ai_orchestrator_event_id": str(event.id),
                "human_approved": True,
            },
        )
    )


def format_ai_output(raw_output: str | None) -> str:
    output = parse_ai_output(raw_output)
    summary = str(output.get("summary") or "AI lead brief reviewed.")
    lines = [summary]
    priority_explanation = output.get("priority_explanation")
    if isinstance(priority_explanation, str) and priority_explanation.strip():
        lines.append(f"Priority: {priority_explanation.strip()}")
    next_task = output.get("next_task")
    if isinstance(next_task, dict):
        title = str(next_task.get("title") or "").strip()
        reason = str(next_task.get("reason") or "").strip()
        due_timing = str(next_task.get("due_timing") or "").strip()
        if title:
            detail = ": ".join(value for value in (reason, due_timing) if value)
            lines.append(f"Recommended next step: {title}{f' ({detail})' if detail else ''}")
    actions = output.get("recommended_actions")
    if isinstance(actions, list) and actions:
        lines.append("Recommended actions:")
        for item in actions[:8]:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if action:
                lines.append(f"- {action}{f': {reason}' if reason else ''}")
    risks = output.get("risks")
    if isinstance(risks, list) and risks:
        lines.append(f"Risks: {'; '.join(str(item) for item in risks[:8])}")
    qualification_gaps = output.get("qualification_gaps")
    if isinstance(qualification_gaps, list) and qualification_gaps:
        lines.append(
            f"Qualification gaps: {'; '.join(str(item) for item in qualification_gaps[:8])}"
        )
    recommended_questions = output.get("recommended_questions")
    if isinstance(recommended_questions, list) and recommended_questions:
        lines.append(
            f"Suggested questions: {'; '.join(str(item) for item in recommended_questions[:8])}"
        )
    uncertainties = output.get("uncertainties")
    if isinstance(uncertainties, list) and uncertainties:
        lines.append(f"Uncertainties: {'; '.join(str(item) for item in uncertainties[:8])}")
    return "\n".join(lines)[:4000]


def parse_ai_output(raw_output: str | None) -> dict[str, Any]:
    if not raw_output:
        return {}
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        return {"summary": raw_output}
    return parsed if isinstance(parsed, dict) else {"summary": raw_output}


def can_review_event(
    principal: Principal,
    event: AiOrchestratorEvent,
    lead: Lead,
) -> bool:
    if PermissionKeys.EDIT_LEADS not in principal.permission_keys:
        return False
    assigned_user_id = payload_uuid((event.payload or {}).get("assigned_user_id"))
    if assigned_user_id == principal.user_id or lead.assigned_user_id == principal.user_id:
        return True
    return bool(
        {
            PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
            PermissionKeys.VIEW_AUDIT_LOGS,
            PermissionKeys.MANAGE_USERS,
        }
        & principal.permission_keys
    )


def default_ai_work_owner(db: Session, organization_id: UUID) -> UUID | None:
    rows = db.execute(
        select(User, Role.key)
        .join(RoleAssignment, RoleAssignment.user_id == User.id)
        .join(Role, Role.id == RoleAssignment.role_id)
        .where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
            Role.key.in_(OPERATIONS_ROLE_PRIORITY),
        )
        .order_by(User.created_at.asc())
    ).all()
    if not rows:
        return None
    ranked = sorted(
        rows,
        key=lambda row: (
            OPERATIONS_ROLE_PRIORITY.get(row[1], 99),
            row[0].created_at,
        ),
    )
    return cast(UUID, ranked[0][0].id)


def payload_uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def normalize_run_status(status: str) -> str:
    if status == "needs_review":
        return "needs_review"
    if status == "blocked":
        return "blocked"
    if status == "failed":
        return "failed"
    return "completed"
