from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import ApprovalRequest, Organization, Task, User
from tests.test_leads import OWNER_EMAIL, lead_payload, seed_owner


def test_primary_action_requires_successor_and_updates_shared_truth(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    assert create_response.status_code == 201, create_response.text
    lead = create_response.json()
    first_action = lead["primary_next_action"]
    assert first_action is not None
    assert first_action["title"] == "Review seller lead and set the next action"

    workspace_response = client.get(
        "/api/v1/tasks/workspace",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert workspace_response.status_code == 200, workspace_response.text
    workspace = workspace_response.json()
    first_item = next(
        item for item in workspace["items"] if item["id"] == f"task:{first_action['task_id']}"
    )
    assert first_item["work_kind"] == "primary_next_action"
    assert first_item["source_record_id"] == lead["id"]
    assert first_item["can_complete"] is True

    stranded_response = client.patch(
        f"/api/v1/tasks/{first_action['task_id']}/complete",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"outcome": "reviewed"},
    )
    assert stranded_response.status_code == 422
    assert "still active" in stranded_response.json()["detail"]

    successor_due = datetime.now(UTC) + timedelta(days=1)
    completed_response = client.patch(
        f"/api/v1/tasks/{first_action['task_id']}/complete",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "outcome": "seller_reached",
            "completion_notes": "Seller is ready for qualification.",
            "successor": {
                "title": "Complete seller qualification",
                "task_type": "qualification",
                "due_at": successor_due.isoformat(),
                "priority": "high",
            },
        },
    )
    assert completed_response.status_code == 200, completed_response.text
    completed = completed_response.json()
    assert completed["outcome"] == "seller_reached"
    assert completed["successor_task_id"] is not None

    detail_response = client.get(
        f"/api/v1/leads/{lead['id']}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert detail_response.status_code == 200
    replacement = detail_response.json()["primary_next_action"]
    assert replacement["task_id"] == completed["successor_task_id"]
    assert replacement["title"] == "Complete seller qualification"
    assert replacement["responsible_user_email"] == OWNER_EMAIL

    open_primary = db_session.scalars(
        select(Task).where(
            Task.lead_id == UUID(lead["id"]),
            Task.work_kind == "primary_next_action",
            Task.status.in_(("open", "in_progress")),
        )
    ).all()
    assert len(open_primary) == 1


def test_task_workspace_aggregates_approval_without_changing_authority(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    organization = db_session.scalar(select(Organization))
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert organization is not None and owner is not None
    approval = ApprovalRequest(
        organization_id=organization.id,
        requested_by_user_id=owner.id,
        assigned_to_user_id=owner.id,
        decided_by_user_id=None,
        request_type="ai_capability_promotion",
        entity_type="ai_capability",
        entity_id=None,
        status="pending",
        title="Promote tested capability",
        summary="Evaluation passed and requires owner review.",
        decision_notes=None,
        due_at=datetime.now(UTC) + timedelta(hours=2),
        decided_at=None,
        approval_metadata={"capability_key": "lead.next_action"},
    )
    db_session.add(approval)
    db_session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/v1/tasks/workspace",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert response.status_code == 200, response.text
    item = next(entry for entry in response.json()["items"] if entry["item_type"] == "approval")
    assert item["id"] == f"approval:{approval.id}"
    assert item["work_kind"] == "approval"
    assert item["can_decide"] is True


def test_individual_contributor_workspace_excludes_other_owners_work(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    users = []
    for index in (1, 2):
        response = client.post(
            "/api/v1/operations/users",
            headers={"X-Dev-User-Email": OWNER_EMAIL},
            json={
                "email": f"acquisitions-{index}@example.com",
                "display_name": f"Acquisitions {index}",
                "role_key": "acquisition_rep",
            },
        )
        assert response.status_code == 201, response.text
        users.append(response.json())

    for index, user in enumerate(users, start=1):
        payload = lead_payload()
        payload["contact"] = {
            "legal_name": f"Seller {index}",
            "preferred_name": f"Seller {index}",
            "contact_type": "seller",
        }
        payload["property"] = {
            "street_address": f"{index} Assigned Way",
            "city": "Atlanta",
            "state": "GA",
            "postal_code": f"3030{index}",
            "property_type": "single_family",
        }
        payload["assigned_user_id"] = user["id"]
        response = client.post(
            "/api/v1/leads",
            headers={"X-Dev-User-Email": OWNER_EMAIL},
            json=payload,
        )
        assert response.status_code == 201, response.text

    response = client.get(
        "/api/v1/tasks/workspace",
        headers={"X-Dev-User-Email": users[0]["email"]},
    )
    assert response.status_code == 200, response.text
    workspace = response.json()
    assert workspace["can_manage_team"] is False
    task_items = [item for item in workspace["items"] if item["item_type"] == "task"]
    assert len(task_items) == 1
    assert task_items[0]["assigned_user_email"] == users[0]["email"]
