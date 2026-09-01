from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Lead,
    Role,
    RoleAssignment,
    User,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "outside-offer-owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Outside Offer Test Workspace",
        admin_email=OWNER_EMAIL,
        admin_name="Outside Offer Owner",
    )


def lead_payload() -> dict[str, object]:
    return {
        "contact": {
            "legal_name": "Jamie Seller",
            "preferred_name": "Jamie",
            "contact_type": "seller",
        },
        "property": {
            "street_address": "123 Peachtree St",
            "city": "Atlanta",
            "state": "GA",
            "postal_code": "30303",
            "county": "Fulton",
            "property_type": "single_family",
        },
        "source": "phone",
        "stage_key": "new",
    }


def create_lead(client: TestClient) -> str:
    response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=lead_payload(),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def outside_offer_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "amount_cents": 157_500_00,
        "occurred_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        "method": "phone",
        "outcome": "presented",
        "seller_response": "Seller asked for time to review the offer with family.",
        "notes": "Offer was presented during a call completed outside Stonegate.",
        "expected_stage_key": "new",
    }
    payload.update(overrides)
    return payload


def test_record_outside_offer_sets_stage_and_appends_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)

    response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(),
    )

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["lead_id"] == lead_id
    assert result["previous_stage_key"] == "new"
    assert result["stage_key"] == "offer_presented"
    assert result["amount_cents"] == 157_500_00
    assert result["method"] == "phone"
    assert result["outcome"] == "presented"

    db_session.expire_all()
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    assert lead.stage_key == "offer_presented"
    audit = db_session.get(AuditEvent, UUID(result["event_id"]))
    assert audit is not None
    assert audit.action == "lead.outside_offer.record"
    assert audit.entity_type == "lead"
    assert audit.entity_id == lead.id
    assert audit.previous_value == {"stage_key": "new"}
    assert audit.new_value is not None
    assert audit.new_value | {"occurred_at": result["occurred_at"]} == {
        "source": "outside_offer_catch_up",
        "stage_key": "offer_presented",
        "amount_cents": 157_500_00,
        "occurred_at": result["occurred_at"],
        "method": "phone",
        "outcome": "presented",
        "seller_response": "Seller asked for time to review the offer with family.",
        "notes": "Offer was presented during a call completed outside Stonegate.",
    }
    assert datetime.fromisoformat(str(audit.new_value["occurred_at"])) == datetime.fromisoformat(
        result["occurred_at"].replace("Z", "+00:00")
    )
    activity = db_session.scalar(
        select(ActivityEvent).where(
            ActivityEvent.entity_id == lead.id,
            ActivityEvent.event_type == "lead.outside_offer_recorded",
        )
    )
    assert activity is not None
    assert "$157,500.00" in activity.summary


@pytest.mark.parametrize("outcome", ["countered", "negotiating"])
def test_countered_or_active_outside_offer_sets_negotiating_stage(
    db_session: Session,
    api_db_override: None,
    outcome: str,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)

    response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(
            outcome=outcome,
            seller_response="Seller countered and the parties are still discussing price.",
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["stage_key"] == "negotiating"
    db_session.expire_all()
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    assert lead.stage_key == "negotiating"


def test_later_offer_does_not_regress_an_already_negotiating_lead(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    lead.stage_key = "negotiating"
    db_session.commit()

    response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(
            expected_stage_key="negotiating",
            outcome="presented",
            seller_response="A revised offer was presented during active negotiations.",
        ),
    )

    assert response.status_code == 201, response.text
    assert response.json()["previous_stage_key"] == "negotiating"
    assert response.json()["stage_key"] == "negotiating"


def test_outside_offer_rejects_stale_stage_without_writing_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    lead.stage_key = "qualified"
    db_session.commit()

    response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(expected_stage_key="new"),
    )

    assert response.status_code == 409
    assert "moved after the pipeline loaded" in response.json()["detail"]
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "lead.outside_offer.record")
            )
            or 0
        )
        == 0
    )
    db_session.expire_all()
    refreshed_lead = db_session.get(Lead, UUID(lead_id))
    assert refreshed_lead is not None
    assert refreshed_lead.stage_key == "qualified"


def test_outside_offer_rejects_future_time_and_direct_stage_bypass(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)

    future = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(
            occurred_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat()
        ),
    )
    direct = client.patch(
        f"/api/v1/leads/{lead_id}/stage",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "stage_key": "offer_presented",
            "expected_stage_key": "new",
            "reason": "Attempted bare stage mutation without offer evidence.",
        },
    )

    assert future.status_code == 422
    assert future.json()["detail"] == "The outside offer time cannot be in the future."
    assert direct.status_code == 422
    assert "require recorded offer evidence" in direct.json()["detail"]
    db_session.expire_all()
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    assert lead.stage_key == "new"


def test_acquisition_rep_can_record_fact_without_offer_approval_permission(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)
    created_user = client.post(
        "/api/v1/operations/users",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "email": "outside-offer-acquisition@example.com",
            "display_name": "Outside Offer Acquisition",
            "role_key": "acquisition_rep",
        },
    )
    assert created_user.status_code == 201, created_user.text
    acquisition_user = db_session.get(User, UUID(created_user.json()["id"]))
    assert acquisition_user is not None
    acquisition_principal = principal_for_user(db_session, acquisition_user)
    assert PermissionKeys.EDIT_LEADS in acquisition_principal.permission_keys
    assert PermissionKeys.APPROVE_OFFERS not in acquisition_principal.permission_keys

    response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": acquisition_user.email},
        json=outside_offer_payload(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["stage_key"] == "offer_presented"


def test_outside_offer_requires_edit_permission_and_tenant_scope(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    read_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == "ai_service",
        )
    )
    assert read_role is not None
    read_only_user = User(
        organization_id=owner.organization_id,
        email="outside-offer-reader@example.com",
        display_name="Outside Offer Reader",
        is_active=True,
    )
    db_session.add(read_only_user)
    db_session.flush()
    db_session.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=read_only_user.id,
            role_id=read_role.id,
        )
    )
    db_session.commit()

    forbidden = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": read_only_user.email},
        json=outside_offer_payload(),
    )

    assert forbidden.status_code == 403

    second_owner_email = "outside-offer-other-owner@example.com"
    bootstrap_foundation(
        db_session,
        organization_name="Outside Offer Other Workspace",
        admin_email=second_owner_email,
        admin_name="Other Owner",
    )
    outside_tenant = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": second_owner_email},
        json=outside_offer_payload(),
    )

    assert outside_tenant.status_code == 404
    db_session.expire_all()
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    assert lead.stage_key == "new"


def test_outside_offer_is_unavailable_for_land_and_under_contract_leads(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    lead_id = create_lead(client)
    lead = db_session.get(Lead, UUID(lead_id))
    assert lead is not None
    lead.asset_class = "land"
    db_session.commit()

    land_response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(),
    )
    assert land_response.status_code == 409
    assert "not available for Land" in land_response.json()["detail"]

    lead.asset_class = "house"
    lead.stage_key = "under_contract"
    db_session.commit()
    contract_response = client.post(
        f"/api/v1/leads/{lead_id}/outside-offers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json=outside_offer_payload(expected_stage_key="under_contract"),
    )

    assert contract_response.status_code == 422
    assert "already under contract" in contract_response.json()["detail"]
