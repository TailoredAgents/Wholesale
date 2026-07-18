from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import ActivityEvent, ApprovalRequest, AuditEvent
from app.schemas.approvals import ApprovalDecision, ApprovalRequestRead

APPROVAL_STATUSES = {"pending", "approved", "rejected", "cancelled"}
DECISION_STATUSES = {"approved", "rejected", "cancelled"}


def list_approval_requests(db: Session, principal: Principal) -> list[ApprovalRequestRead]:
    requests = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.organization_id == principal.organization_id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    ).all()
    return [approval_to_read(request) for request in requests]


def decide_approval_request(
    db: Session,
    principal: Principal,
    approval_id: UUID,
    payload: ApprovalDecision,
) -> ApprovalRequestRead | None:
    if payload.status not in DECISION_STATUSES:
        raise ValueError(f"Unsupported approval decision: {payload.status}")
    request = db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == principal.organization_id,
            ApprovalRequest.id == approval_id,
        )
    )
    if request is None:
        return None
    if request.request_type == "call_notes_review":
        raise ValueError("Call notes must be reviewed with the recording in the shared inbox.")
    previous_status = request.status
    request.status = payload.status
    request.decision_notes = payload.decision_notes
    request.decided_at = datetime.now(UTC)
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="approval_request",
            entity_id=request.id,
            event_type="approval.decided",
            summary=f"Approval request {payload.status}: {request.title}.",
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="approval.decide",
            entity_type="approval_request",
            entity_id=request.id,
            previous_value={"status": previous_status},
            new_value={"status": request.status, "decision_notes": request.decision_notes},
            reason="Manual approval decision",
        )
    )
    db.commit()
    db.refresh(request)
    return approval_to_read(request)


def approval_to_read(request: ApprovalRequest) -> ApprovalRequestRead:
    return ApprovalRequestRead(
        id=request.id,
        request_type=request.request_type,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        status=request.status,
        title=request.title,
        summary=request.summary,
        decision_notes=request.decision_notes,
        due_at=request.due_at,
        decided_at=request.decided_at,
        created_at=request.created_at,
        review_url="/os/inbox" if request.request_type == "call_notes_review" else None,
    )
