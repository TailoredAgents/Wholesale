from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import Organization, Role, RoleAssignment, User
from app.services.bootstrap import bootstrap_foundation


def _headers_for_role(db: Session, *, role_key: str, email: str) -> dict[str, str]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email="buyer-pool-owner@example.com",
        admin_name="Buyer Pool Owner",
    )
    organization = db.scalar(select(Organization))
    assert organization is not None
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=email,
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return {"X-Dev-User-Email": email}


def test_read_only_human_role_can_enter_buyer_pool_and_run_history(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_role(
        db_session,
        role_key="read_only_partner",
        email="deal-only-viewer@example.com",
    )
    case_id = uuid4()

    pool = client.get(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool",
        headers=headers,
    )
    history = client.get(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=headers,
    )

    assert pool.status_code == 404
    assert pool.json()["detail"] == "Disposition case not found."
    assert history.status_code == 404
    assert history.json()["detail"] == pool.json()["detail"]


def test_deal_editor_cannot_refresh_or_decide_without_buyer_permissions(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_role(
        db_session,
        role_key="transaction_coordinator",
        email="deal-only-editor@example.com",
    )
    case_id = uuid4()
    candidate_id = uuid4()

    refresh = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=headers,
    )
    decision = client.patch(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{candidate_id}"
        ),
        headers=headers,
        json={
            "expected_version": 1,
            "decision_status": "shortlisted",
        },
    )

    assert refresh.status_code == 403
    assert refresh.json()["detail"] == "Missing permission: buyers:view"
    assert decision.status_code == 403
    assert decision.json()["detail"] == "Missing permission: buyers:edit"
