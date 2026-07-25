from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ConsentRecord,
    Contact,
    Prospect,
    ProspectSuppressionCheck,
    SuppressionRecord,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import evaluate_email_eligibility
from app.services.compliance import (
    prospect_call_blockers,
    recording_enabled_for_organization,
)

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "caller@example.com"
OWNER_HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}
VA_HEADERS = {"X-Dev-User-Email": VA_EMAIL}


def bootstrap_workspace(db: Session, client: TestClient) -> dict[str, Any]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = client.post(
        "/api/v1/operations/users",
        headers=OWNER_HEADERS,
        json={
            "email": VA_EMAIL,
            "display_name": "VA Caller",
            "role_key": "prospecting_caller",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def legally_review_and_approve_policies(
    client: TestClient,
) -> list[dict[str, Any]]:
    overview = client.get("/api/v1/compliance", headers=OWNER_HEADERS).json()
    policies = cast(list[dict[str, Any]], overview["policies"])
    for policy in policies:
        legal_response = client.patch(
            f"/api/v1/compliance/policies/{policy['id']}/legal-review",
            headers=OWNER_HEADERS,
            json={
                "legal_reviewer_name": "Test Counsel",
                "legal_reviewer_company": "Test Legal",
                "legal_evidence_reference": "test://legal-review",
                "legal_reviewed_at": "2026-07-24T12:00:00Z",
                "review_due_at": "2027-07-24T12:00:00Z",
                "notes": "Test evidence only.",
            },
        )
        assert legal_response.status_code == 200, legal_response.text
        approve_response = client.post(
            f"/api/v1/compliance/policies/{policy['id']}/decision",
            headers=OWNER_HEADERS,
            json={
                "decision": "approve",
                "reason": "Owner approved test policy.",
            },
        )
        assert approve_response.status_code == 200, approve_response.text
    return policies


def test_policy_dnc_training_incident_and_control_workflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    va = bootstrap_workspace(db_session, client)

    install = client.post("/api/v1/compliance/install", headers=OWNER_HEADERS)
    assert install.status_code == 200, install.text
    assert install.json()["created_policy_count"] == 6
    second_install = client.post("/api/v1/compliance/install", headers=OWNER_HEADERS)
    assert second_install.status_code == 200
    assert second_install.json()["created_policy_count"] == 0

    policy_id = install.json()["overview"]["policies"][0]["id"]
    blocked_approval = client.post(
        f"/api/v1/compliance/policies/{policy_id}/decision",
        headers=OWNER_HEADERS,
        json={"decision": "approve", "reason": "Approve before legal review."},
    )
    assert blocked_approval.status_code == 422
    assert "Legal review evidence" in blocked_approval.text
    legally_review_and_approve_policies(client)

    source = client.post(
        "/api/v1/compliance/dnc-sources",
        headers=OWNER_HEADERS,
        json={
            "name": "FTC National Registry",
            "provider_type": "ftc_registry",
            "account_reference": "test-account",
            "coverage_area_codes": ["404", "470", "678", "770"],
            "refresh_interval_days": 31,
        },
    )
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    approve_source = client.post(
        f"/api/v1/compliance/dnc-sources/{source_id}/decision",
        headers=OWNER_HEADERS,
        json={"decision": "approve", "reason": "Owner approved screening source."},
    )
    assert approve_source.status_code == 200
    refresh = client.post(
        f"/api/v1/compliance/dnc-sources/{source_id}/refresh",
        headers=OWNER_HEADERS,
        json={
            "refreshed_at": datetime.now(UTC).isoformat(),
            "evidence_reference": "test://dnc-export",
        },
    )
    assert refresh.status_code == 200, refresh.text
    assert refresh.json()["is_current"] is True

    assignment = client.post(
        "/api/v1/compliance/training",
        headers=OWNER_HEADERS,
        json={
            "user_id": va["id"],
            "training_key": "outbound_contact",
            "training_version": "1.0",
        },
    )
    assert assignment.status_code == 201, assignment.text
    training_id = assignment.json()["id"]
    my_training = client.get("/api/v1/compliance/my-training", headers=VA_HEADERS)
    assert my_training.status_code == 200
    assert my_training.json()[0]["status"] == "assigned"
    submission = client.post(
        f"/api/v1/compliance/my-training/{training_id}/submit",
        headers=VA_HEADERS,
        json={
            "completion_evidence": "Reviewed approved outbound contact scenarios.",
            "employee_attestation": "I understand and will follow the approved policy.",
        },
    )
    assert submission.status_code == 200, submission.text
    decision = client.post(
        f"/api/v1/compliance/training/{training_id}/decision",
        headers=OWNER_HEADERS,
        json={
            "decision": "approve",
            "manager_notes": "Evidence reviewed and approved.",
            "score_basis_points": 10000,
        },
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    incident = client.post(
        "/api/v1/compliance/incidents",
        headers=OWNER_HEADERS,
        json={
            "incident_type": "wrong_number",
            "channel": "phone",
            "severity": "medium",
            "summary": "Prospect reported a wrong number.",
        },
    )
    assert incident.status_code == 201
    resolution = client.post(
        f"/api/v1/compliance/incidents/{incident.json()['id']}/resolve",
        headers=OWNER_HEADERS,
        json={"resolution": "Number suppressed and record reviewed."},
    )
    assert resolution.status_code == 200
    assert resolution.json()["status"] == "resolved"

    control_run = client.post(
        "/api/v1/compliance/control-runs",
        headers=OWNER_HEADERS,
    )
    assert control_run.status_code == 201, control_run.text
    assert len(control_run.json()["results"]) == 6


def test_email_suppression_and_recording_policy_gates(
    db_session: Session,
    api_db_override: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    bootstrap_workspace(db_session, client)
    response = client.post(
        "/api/v1/public/seller-leads",
        json={
            "property_address": "55 Auburn Ave",
            "property_city": "Atlanta",
            "property_state": "GA",
            "property_postal_code": "30303",
            "name": "Sam Seller",
            "phone": "4045551212",
            "email": "sam@example.com",
            "preferred_contact_method": "email",
            "reason_for_selling": "Inherited property",
            "desired_timeline": "30 days",
            "consent_to_contact": True,
        },
    )
    assert response.status_code == 201
    contact = db_session.scalar(select(Contact))
    assert contact is not None
    assert evaluate_email_eligibility(db_session, contact).can_send is True
    assert db_session.scalar(
        select(ConsentRecord).where(
            ConsentRecord.contact_id == contact.id,
            ConsentRecord.channel == "email",
        )
    )

    db_session.add(
        SuppressionRecord(
            organization_id=contact.organization_id,
            contact_id=contact.id,
            channel="email",
            normalized_address="sam@example.com",
            status="active",
            reason="seller_opt_out",
            source="test",
            suppressed_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    eligibility = evaluate_email_eligibility(db_session, contact)
    assert eligibility.can_send is False
    assert eligibility.is_suppressed is True

    monkeypatch.setenv("TWILIO_VOICE_ENABLED", "true")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC00000000000000000000000000000000")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-auth-token")
    monkeypatch.setenv("TWILIO_API_KEY_SID", "SK00000000000000000000000000000000")
    monkeypatch.setenv("TWILIO_API_KEY_SECRET", "test-api-key-secret-with-32-bytes")
    monkeypatch.setenv("TWILIO_TWIML_APP_SID", "AP00000000000000000000000000000000")
    monkeypatch.setenv("TWILIO_VOICE_FROM_NUMBER", "+16785417725")
    monkeypatch.setenv("TWILIO_WEBHOOK_BASE_URL", "https://api.stonegate.test")
    monkeypatch.setenv("TWILIO_VOICE_RECORDING_ENABLED", "true")
    monkeypatch.setenv(
        "TWILIO_VOICE_RECORDING_DISCLOSURE",
        "This call may be recorded with your permission.",
    )
    get_settings.cache_clear()
    try:
        assert (
            recording_enabled_for_organization(
                db_session,
                contact.organization_id,
                settings=get_settings(),
            )
            is False
        )
        client.post("/api/v1/compliance/install", headers=OWNER_HEADERS)
        legally_review_and_approve_policies(client)
        assert (
            recording_enabled_for_organization(
                db_session,
                contact.organization_id,
                settings=get_settings(),
            )
            is True
        )
    finally:
        get_settings.cache_clear()


def test_prospect_call_gate_rejects_missing_and_stale_dnc_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    bootstrap_workspace(db_session, client)
    owner = db_session.scalar(select(Contact))
    assert owner is None
    organization_id = UUID(
        client.get("/api/v1/me", headers=OWNER_HEADERS).json()["organization_id"]
    )
    owner_user_id = client.get("/api/v1/me", headers=OWNER_HEADERS).json()["user_id"]
    market = client.post(
        "/api/v1/operations/markets",
        headers=OWNER_HEADERS,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-test",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market.status_code == 201, market.text
    campaign = client.post(
        "/api/v1/operations/campaigns",
        headers=OWNER_HEADERS,
        json={
            "market_id": market.json()["id"],
            "owner_user_id": owner_user_id,
            "name": "Compliance Test Campaign",
            "code": "compliance-test",
            "channel": "cold_call",
        },
    )
    assert campaign.status_code == 201, campaign.text
    prospect = Prospect(
        organization_id=organization_id,
        campaign_id=UUID(campaign.json()["id"]),
        territory_id=None,
        assigned_user_id=None,
        converted_lead_id=None,
        import_batch_id=None,
        source_record_key="test-prospect",
        status="new",
        legal_name="Test Prospect",
        phone="4045550199",
        normalized_phone="14045550199",
        email=None,
        normalized_email=None,
        street_address=None,
        city=None,
        state_code="GA",
        postal_code=None,
        normalized_address_key=None,
        suppression_status="clear",
        suppression_checked_at=datetime.now(UTC),
        phone_validation_status="valid",
        address_validation_status="unverified",
        call_eligibility="eligible",
        last_contacted_at=None,
        source_payload={},
    )
    db_session.add(prospect)
    db_session.flush()
    assert "National Do Not Call screening" in " ".join(
        prospect_call_blockers(db_session, prospect)
    )

    check = ProspectSuppressionCheck(
        organization_id=organization_id,
        import_row_id=None,
        prospect_id=prospect.id,
        check_type="national_dnc",
        channel="phone",
        normalized_value=prospect.normalized_phone,
        status="clear",
        source="test",
        evidence={"reference": "test"},
        checked_at=datetime.now(UTC),
    )
    db_session.add(check)
    db_session.commit()
    assert prospect_call_blockers(db_session, prospect) == ()

    check.checked_at = datetime.now(UTC) - timedelta(days=32)
    db_session.commit()
    assert "more than 31 days old" in " ".join(
        prospect_call_blockers(db_session, prospect)
    )
