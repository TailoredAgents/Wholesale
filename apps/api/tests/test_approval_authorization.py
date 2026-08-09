from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    ApprovalRequest,
    AuditEvent,
    Role,
    RoleAssignment,
    User,
)
from app.services.approvals import approval_decision_lock_statement, list_approval_requests
from app.services.bootstrap import bootstrap_foundation
from app.services.tasks import list_task_workspace

OWNER_EMAIL = "owner@example.com"
ADMIN_EMAIL = "administrator@example.com"


def seed_users(db: Session) -> tuple[User, User]:
    foundation = bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = foundation.admin_user
    assert owner is not None
    administrator_role = db.scalar(
        select(Role).where(
            Role.organization_id == foundation.organization.id,
            Role.key == "administrator",
        )
    )
    assert administrator_role is not None
    administrator = User(
        organization_id=foundation.organization.id,
        email=ADMIN_EMAIL,
        display_name="Administrator",
        is_active=True,
    )
    db.add(administrator)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=foundation.organization.id,
            user_id=administrator.id,
            role_id=administrator_role.id,
        )
    )
    db.commit()
    return owner, administrator


def create_approval(db: Session, owner: User, request_type: str) -> ApprovalRequest:
    approval = ApprovalRequest(
        organization_id=owner.organization_id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type=request_type,
        entity_type="security_test",
        entity_id=None,
        status="pending",
        title=f"Review {request_type}",
        summary="Security authorization test.",
        decision_notes=None,
        due_at=None,
        decided_at=None,
        approval_metadata={},
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def test_approval_decision_locks_the_scoped_request_in_postgresql() -> None:
    owner_id = uuid4()
    approval_id = uuid4()

    statement = approval_decision_lock_statement(owner_id, approval_id)
    compiled = str(
        statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    )

    assert "approval_requests.organization_id =" in compiled
    assert "approval_requests.id =" in compiled
    assert "FOR UPDATE OF approval_requests" in compiled


@pytest.mark.parametrize("request_type", ["ai_capability_promotion", "ai_tool_call"])
def test_administrator_cannot_decide_ai_approval(
    db_session: Session,
    api_db_override: None,
    request_type: str,
) -> None:
    owner, _administrator = seed_users(db_session)
    approval = create_approval(db_session, owner, request_type)

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": ADMIN_EMAIL},
        json={"status": "approved", "decision_notes": "Should not be authorized."},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing permission: ai:change_prompts"
    db_session.refresh(approval)
    assert approval.status == "pending"
    assert approval.decided_by_user_id is None


def test_owner_can_decide_ai_tool_call_approval(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _administrator = seed_users(db_session)
    approval = create_approval(db_session, owner, "ai_tool_call")

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "approved", "decision_notes": "Owner reviewed the tool call."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_competing_decision_rechecks_status_before_any_second_side_effect(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _administrator = seed_users(db_session)
    approval = create_approval(db_session, owner, "ai_tool_call")
    client = TestClient(app)

    first = client.patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "approved", "decision_notes": "First reviewer approved it."},
    )
    assert first.status_code == 200

    activity_count = int(
        db_session.scalar(
            select(func.count())
            .select_from(ActivityEvent)
            .where(
                ActivityEvent.entity_type == "approval_request",
                ActivityEvent.entity_id == approval.id,
                ActivityEvent.event_type == "approval.decided",
            )
        )
        or 0
    )
    audit_count = int(
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_type == "approval_request",
                AuditEvent.entity_id == approval.id,
                AuditEvent.action == "approval.decide",
            )
        )
        or 0
    )

    second = client.patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "rejected", "decision_notes": "A stale competing decision."},
    )

    assert second.status_code == 422
    assert second.json()["detail"] == "This approval request has already been decided."
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ActivityEvent)
                .where(
                    ActivityEvent.entity_type == "approval_request",
                    ActivityEvent.entity_id == approval.id,
                    ActivityEvent.event_type == "approval.decided",
                )
            )
            or 0
        )
        == activity_count
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.entity_type == "approval_request",
                    AuditEvent.entity_id == approval.id,
                    AuditEvent.action == "approval.decide",
                )
            )
            or 0
        )
        == audit_count
    )
    db_session.refresh(approval)
    assert approval.status == "approved"
    assert approval.decision_notes == "First reviewer approved it."


@pytest.mark.parametrize("request_type", ["follow_up_sms", "follow_up_email"])
def test_operations_manager_can_decide_supported_follow_up_approval(
    db_session: Session,
    api_db_override: None,
    request_type: str,
) -> None:
    owner, _administrator = seed_users(db_session)
    approval = create_approval(db_session, owner, request_type)

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": ADMIN_EMAIL},
        json={"status": "approved", "decision_notes": "Operations review complete."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_unknown_approval_type_fails_closed(
    db_session: Session,
    api_db_override: None,
) -> None:
    owner, _administrator = seed_users(db_session)
    approval = create_approval(db_session, owner, "future_sensitive_action")

    response = TestClient(app).patch(
        f"/api/v1/approvals/{approval.id}/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"status": "approved", "decision_notes": "Unknown types must not mutate."},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Unsupported approval request type: future_sensitive_action"
    )
    db_session.refresh(approval)
    assert approval.status == "pending"
    assert approval.decided_by_user_id is None


def test_approval_list_is_scoped_to_the_principals_decision_authority(
    db_session: Session,
) -> None:
    owner, _administrator = seed_users(db_session)
    create_approval(db_session, owner, "offer_ceiling")
    create_approval(db_session, owner, "ai_tool_call")
    ai_principal = Principal(
        user_id=owner.id,
        organization_id=owner.organization_id,
        email=owner.email,
        permission_keys=frozenset({PermissionKeys.CHANGE_AI_PROMPTS}),
    )

    visible = list_approval_requests(db_session, ai_principal)
    task_workspace = list_task_workspace(db_session, ai_principal)

    assert [item.request_type for item in visible] == ["ai_tool_call"]
    visible_task_approvals = [
        item.task_type for item in task_workspace.items if item.item_type == "approval"
    ]
    assert visible_task_approvals == ["ai_tool_call"]
