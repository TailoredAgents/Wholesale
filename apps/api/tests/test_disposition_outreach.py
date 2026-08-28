from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Buyer,
    ConsentRecord,
    DispositionCampaign,
    DispositionCase,
    DispositionOutreachDelivery,
    DispositionOutreachRevision,
    EmailSenderAlias,
    SuppressionRecord,
    User,
    VoiceLine,
)
from tests.test_dispositions import (
    HEADERS,
    OWNER_EMAIL,
    approve_disposition_package,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)

TEST_OUTREACH_POSTAL_ADDRESS = "100 Test Fixture Way, Atlanta, GA 30303"


@pytest.fixture(autouse=True)
def _configure_test_outreach_postal_address(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings().model_copy(
        update={
            "disposition_outreach_physical_postal_address": (
                TEST_OUTREACH_POSTAL_ADDRESS
            )
        }
    )
    monkeypatch.setattr(
        "app.services.disposition_outreach.get_settings",
        lambda: settings,
    )


def prepare_outreach_case(
    db: Session,
    client: TestClient,
    *,
    buyer_phone: str | None = None,
) -> tuple[str, DispositionCampaign, EmailSenderAlias]:
    _, transaction_id, buyer_id = setup_case_foundation(db, client)
    if buyer_phone:
        buyer = db.get(Buyer, UUID(buyer_id))
        assert buyer is not None
        buyer.phone = buyer_phone
        buyer.normalized_phone = buyer_phone
        db.commit()
    created = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert approve_disposition_package(client, case_id).status_code == 200
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    put_verified_buy_box(client, buyer_id)
    assert (
        client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS).status_code
        == 200
    )
    prepared = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert prepared.status_code == 200, prepared.text
    campaign = db.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert campaign is not None and owner is not None
    alias = EmailSenderAlias(
        organization_id=owner.organization_id,
        owner_user_id=None,
        assigned_team_id=None,
        created_by_user_id=owner.id,
        provider="resend",
        provider_identity_id=None,
        email_address="buyers@stonegatehb.com",
        display_name="Stonegate Buyer Relations",
        alias_type="department",
        purpose_key="buyer_outreach",
        status="active",
        inbound_enabled=True,
        outbound_enabled=True,
        is_default=True,
        signature_text="Stonegate Home Buyers\nBuyer Relations",
        routing_metadata={"department_key": "dispositions"},
    )
    db.add(alias)
    db.commit()
    return case_id, campaign, alias


def test_governed_outreach_draft_approval_release_and_cancel(
    db_session: Session,
    api_db_override: None,
    monkeypatch,
) -> None:
    client = TestClient(app)
    case_id, campaign, alias = prepare_outreach_case(db_session, client)

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/outreach",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    assert workspace.headers["cache-control"] == "private, no-store"
    assert workspace.json()["readiness_status"] == "ready"
    recipient = workspace.json()["prepared_recipients"][0]
    assert recipient["available_channels"] == ["email"]
    assert workspace.json()["available_senders"][0]["id"] == str(alias.id)

    drafted = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={
            "campaign_id": str(campaign.id),
            "recipients": [
                {
                    "campaign_recipient_id": recipient["id"],
                    "channels": ["email"],
                }
            ],
            "email_sender_alias_id": str(alias.id),
            "email_subject": "Opportunity at {property_address}",
            "email_body": "Hi {buyer_name}, review package {package_reference}.",
        },
    )
    assert drafted.status_code == 201, drafted.text
    draft = drafted.json()
    assert draft["status"] == "review_required"
    assert draft["approval_hash"]
    assert draft["delivery_counts"] == {"prepared": 1}
    delivery = draft["deliveries"][0]
    assert delivery["conversation_id"] is None
    assert "Stonegate Home Buyers\nBuyer Relations" in delivery["body"]
    assert delivery["body"].endswith(
        "This Stonegate Home Buyers property-opportunity email is a solicitation.\n"
        f"{TEST_OUTREACH_POSTAL_ADDRESS}\n"
        "To stop receiving these emails, reply UNSUBSCRIBE."
    )
    assert delivery["eligibility_status"] == "eligible"
    assert delivery["eligibility_snapshot"]["draft"]["structurally_eligible"] is True

    bad_approval = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/approve",
        headers=HEADERS,
        json={
            "expected_lock_version": draft["lock_version"],
            "expected_approval_hash": "0" * 64,
            "attestation": True,
            "reason": "Reviewed recipient, sender, package, and exact copy.",
        },
    )
    assert bad_approval.status_code == 422

    approved = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/approve",
        headers=HEADERS,
        json={
            "expected_lock_version": draft["lock_version"],
            "expected_approval_hash": draft["approval_hash"],
            "attestation": True,
            "reason": "Reviewed recipient, sender, package, and exact copy.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["delivery_counts"] == {"approved": 1}

    # Test settings intentionally lack live Resend credentials. Release must persist a
    # provider-degraded block instead of sending or silently dropping the delivery.
    released = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/release",
        headers=HEADERS,
        json={
            "expected_lock_version": approved.json()["lock_version"],
            "reason": "Approved supervised release requested.",
        },
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "provider_degraded"
    assert released.json()["delivery_counts"] == {"approved": 1}
    transient = released.json()["deliveries"][0]["eligibility_snapshot"]["latest"][
        "transient_blockers"
    ]
    assert any("Resend" in blocker for blocker in transient)

    simulation_settings = get_settings().model_copy(
        update={
            "communication_provider_mode": "simulate",
            "disposition_outreach_physical_postal_address": (
                TEST_OUTREACH_POSTAL_ADDRESS
            ),
        }
    )
    monkeypatch.setattr(
        "app.services.disposition_outreach.get_settings",
        lambda: simulation_settings,
    )
    resumed = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/resume",
        headers=HEADERS,
        json={
            "expected_lock_version": released.json()["lock_version"],
            "reason": "Provider recovered; resume the approved supervised release.",
        },
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "queued"
    assert resumed.json()["delivery_counts"] == {"queued": 1}
    db_session.refresh(campaign)
    stored_case = db_session.get(DispositionCase, UUID(case_id))
    assert campaign.status == "prepared_not_sent"
    assert campaign.released_at is not None
    assert stored_case is not None and stored_case.status == "marketed"

    cancelled = client.post(
        f"/api/v1/dispositions/campaigns/{campaign.id}/outreach/{draft['id']}/cancel-unsent",
        headers=HEADERS,
        json={
            "expected_lock_version": resumed.json()["lock_version"],
            "reason": "Operator cancelled the unsent provider-blocked release.",
        },
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["delivery_counts"] == {"cancelled": 1}
    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(
                AuditEvent.entity_type == "disposition_outreach_revision"
            )
        ).all()
    )
    assert {
        "disposition.outreach_draft_created",
        "disposition.outreach_approved",
        "disposition.outreach_released",
        "disposition.outreach_unsent_cancelled",
    }.issubset(actions)


def test_outreach_rejects_unapproved_template_fields_and_creates_new_revision(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, campaign, alias = prepare_outreach_case(db_session, client)
    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/outreach",
        headers=HEADERS,
    ).json()
    recipient_id = workspace["prepared_recipients"][0]["id"]
    base = {
        "campaign_id": str(campaign.id),
        "recipients": [{"campaign_recipient_id": recipient_id, "channels": ["email"]}],
        "email_sender_alias_id": str(alias.id),
        "email_subject": "Stonegate property opportunity",
    }
    rejected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={**base, "email_body": "Internal floor: {minimum_acceptable_cents}"},
    )
    assert rejected.status_code == 422
    assert "Unsupported placeholder" in rejected.text

    first = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={**base, "email_body": "First reviewed message for {buyer_name}."},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json={**base, "email_body": "Second reviewed message for {buyer_name}."},
    )
    assert second.status_code == 201, second.text
    assert second.json()["revision_number"] == 2
    prior = db_session.get(DispositionOutreachRevision, UUID(first.json()["id"]))
    assert prior is not None
    assert prior.status == "invalidated"
    assert first.json()["approval_hash"] != second.json()["approval_hash"]


def test_sms_draft_uses_canonical_buyer_contact_consent_and_all_channel_suppression(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    buyer_phone = "+14045550199"
    case_id, campaign, _ = prepare_outreach_case(
        db_session,
        client,
        buyer_phone=buyer_phone,
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    line = VoiceLine(
        organization_id=owner.organization_id,
        assigned_user_id=None,
        fallback_user_id=None,
        assigned_team_id=None,
        provider="twilio",
        provider_phone_number_id=None,
        phone_number="+14045550002",
        label="Stonegate Dispositions",
        department_key="dispositions",
        purpose_key="buyer_relations",
        status="active",
        is_default=True,
        inbound_route="assigned_user",
        ring_strategy="simultaneous",
        coverage_timezone="America/New_York",
        coverage_start_hour=0,
        coverage_end_hour=24,
        missed_call_action="fallback_then_voicemail",
        line_metadata={"source": "test"},
    )
    db_session.add(line)
    db_session.commit()

    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/outreach",
        headers=HEADERS,
    ).json()
    recipient = workspace["prepared_recipients"][0]
    assert recipient["captured_phone"] == buyer_phone
    assert "sms" in recipient["available_channels"]
    assert any(sender["id"] == str(line.id) for sender in workspace["available_senders"])
    payload = {
        "campaign_id": str(campaign.id),
        "recipients": [
            {"campaign_recipient_id": recipient["id"], "channels": ["sms"]}
        ],
        "sms_voice_line_id": str(line.id),
        "sms_body": "Hi {buyer_name}, review {property_address}.",
    }

    missing_consent = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json=payload,
    )
    assert missing_consent.status_code == 201, missing_consent.text
    missing_delivery = missing_consent.json()["deliveries"][0]
    assert missing_delivery["eligibility_status"] == "ineligible"
    assert any(
        "SMS consent" in blocker
        for blocker in missing_delivery["eligibility_snapshot"]["draft"][
            "permanent_blockers"
        ]
    )
    stored_delivery = db_session.get(
        DispositionOutreachDelivery,
        UUID(missing_delivery["id"]),
    )
    assert stored_delivery is not None and stored_delivery.contact_id is not None
    db_session.add(
        ConsentRecord(
            organization_id=owner.organization_id,
            contact_id=stored_delivery.contact_id,
            channel="sms",
            status="granted",
            source="manual_test",
            wording_version="test-v1",
            wording="Buyer granted permission for disposition property alerts.",
            normalized_address=buyer_phone,
            captured_ip=None,
            user_agent=None,
        )
    )
    db_session.commit()

    consented = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json=payload,
    )
    assert consented.status_code == 201, consented.text
    consented_delivery = consented.json()["deliveries"][0]
    assert consented_delivery["eligibility_status"] == "eligible"
    assert consented_delivery["conversation_id"] is not None
    assert consented.json()["sender_snapshot"]["sms"]["voice_line_id"] == str(line.id)

    db_session.add(
        SuppressionRecord(
            organization_id=owner.organization_id,
            contact_id=stored_delivery.contact_id,
            channel="all",
            normalized_address=buyer_phone,
            status="active",
            reason="Buyer requested no further communication.",
            source="manual_test",
            provider=None,
            external_event_id=None,
            suppressed_at=datetime.now(UTC),
            lifted_at=None,
            suppression_metadata={"source": "test"},
        )
    )
    db_session.commit()
    suppressed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
        headers=HEADERS,
        json=payload,
    )
    assert suppressed.status_code == 201, suppressed.text
    suppressed_delivery = suppressed.json()["deliveries"][0]
    assert suppressed_delivery["status"] == "ineligible"
    assert any(
        "all communications" in blocker
        for blocker in suppressed_delivery["eligibility_snapshot"]["draft"][
            "permanent_blockers"
        ]
    )
