from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerBuyBox,
    BuyerBuyBoxVersion,
    BuyerEngagement,
    BuyerProofDocument,
    CallRecord,
    CommunicationRecord,
    Conversation,
    ConversationContextLink,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def create_buyer(
    client: TestClient,
    *,
    name: str = "Structured Buyer",
    email: str = "structured-buyer@example.com",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": name,
            "email": email,
            "criteria": {"markets": "Atlanta", "property_types": "single_family"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def house_payload(*, expected_version: int, max_price_cents: int) -> dict[str, object]:
    return {
        "expected_version": expected_version,
        "source": "buyer_interview",
        "change_reason": "Confirmed directly with buyer",
        "verification_status": "verified",
        "criteria": {
            "asset_class": "house",
            "geographies": [
                {"jurisdiction": "city", "value": "Atlanta", "state": "GA"}
            ],
            "strategies": ["fix_and_flip"],
            "min_price_cents": 10000000,
            "max_price_cents": max_price_cents,
            "funding_methods": ["cash"],
            "capacity": {
                "available_capital_cents": 100000000,
                "max_concurrent_purchases": 3,
                "target_purchases_per_month": 2,
            },
            "property_types": ["single_family"],
            "rehab_tolerance": ["medium", "heavy"],
            "occupancy_preferences": ["vacant"],
        },
    }


def land_payload(*, expected_version: int) -> dict[str, object]:
    return {
        "expected_version": expected_version,
        "source": "buyer_interview",
        "change_reason": "Buyer confirmed a land buy box",
        "criteria": {
            "asset_class": "land",
            "min_acres": 1,
            "max_acres": 20,
            "intended_uses": ["residential", "hold"],
            "access_preferences": ["legal_access"],
        },
    }


def test_independent_buy_boxes_version_without_noop_or_cross_asset_updates(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    buyer = create_buyer(client)
    buyer_id = buyer["id"]

    first = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json=house_payload(expected_version=0, max_price_cents=40000000),
    )
    assert first.status_code == 200, first.text
    assert first.json()["version_number"] == 1
    assert first.json()["criteria"]["asset_class"] == "house"

    noop = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json=house_payload(expected_version=1, max_price_cents=40000000),
    )
    assert noop.status_code == 200, noop.text
    assert noop.json()["version_number"] == 1
    assert int(db_session.scalar(select(func.count()).select_from(BuyerBuyBoxVersion)) or 0) == 1

    second = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json=house_payload(expected_version=1, max_price_cents=45000000),
    )
    assert second.status_code == 200, second.text
    assert second.json()["version_number"] == 2

    stale = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json=house_payload(expected_version=1, max_price_cents=50000000),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "buyer_buy_box_version_conflict"
    assert stale.json()["detail"]["current_version"] == 2

    wrong_lane = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json={
            "expected_version": 2,
            "source": "buyer_interview",
            "change_reason": "Wrong lane must be rejected",
            "criteria": {"asset_class": "land", "min_acres": 1, "max_acres": 5},
        },
    )
    assert wrong_lane.status_code == 422

    land = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/land",
        headers=HEADERS,
        json=land_payload(expected_version=0),
    )
    assert land.status_code == 200, land.text

    detail = client.get(f"/api/v1/buyers/{buyer_id}", headers=HEADERS)
    assert detail.status_code == 200
    assert detail.json()["asset_focus"] == "both"
    assert {item["asset_class"] for item in detail.json()["buy_boxes"]} == {
        "house",
        "land",
    }

    filtered = client.get("/api/v1/buyers?asset_class=land", headers=HEADERS)
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [buyer_id]


def test_buyer_asset_filter_requires_current_structured_boxes(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    house_only = create_buyer(
        client,
        name="House Only Buyer",
        email="house-only@example.com",
    )
    land_only = create_buyer(
        client,
        name="Land Only Buyer",
        email="land-only@example.com",
    )
    both = create_buyer(
        client,
        name="Both Asset Buyer",
        email="both-assets@example.com",
    )
    legacy_only = create_buyer(
        client,
        name="Legacy Criteria Buyer",
        email="legacy-only@example.com",
    )

    for buyer in (house_only, both):
        response = client.put(
            f"/api/v1/buyers/{buyer['id']}/buy-boxes/house",
            headers=HEADERS,
            json=house_payload(expected_version=0, max_price_cents=40000000),
        )
        assert response.status_code == 200, response.text
    for buyer in (land_only, both):
        response = client.put(
            f"/api/v1/buyers/{buyer['id']}/buy-boxes/land",
            headers=HEADERS,
            json=land_payload(expected_version=0),
        )
        assert response.status_code == 200, response.text

    # A structured header without a current version is not a usable buy box.
    legacy_buyer = db_session.get(Buyer, UUID(str(legacy_only["id"])))
    assert legacy_buyer is not None
    db_session.add(
        BuyerBuyBox(
            organization_id=legacy_buyer.organization_id,
            buyer_id=UUID(str(legacy_only["id"])),
            asset_class="house",
        )
    )
    db_session.commit()

    def filtered_ids(asset_class: str) -> set[str]:
        response = client.get(
            f"/api/v1/buyers?asset_class={asset_class}",
            headers=HEADERS,
        )
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    assert filtered_ids("house") == {house_only["id"], both["id"]}
    assert filtered_ids("land") == {land_only["id"], both["id"]}
    assert filtered_ids("both") == {both["id"]}

    invalid = client.get("/api/v1/buyers?asset_class=warehouse", headers=HEADERS)
    assert invalid.status_code == 422


def test_buyer_read_derives_proof_status_from_current_reviewed_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    buyer = create_buyer(client)
    buyer_id = buyer["id"]
    future_expiry = datetime.now(UTC) + timedelta(days=30)

    upload = client.post(
        f"/api/v1/dispositions/buyers/{buyer_id}/proof",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "buyer-proof.pdf",
            "content_type": "application/pdf",
            "institution_name": "Example Bank",
            "verified_amount_cents": 50000000,
            "expires_at": future_expiry.isoformat(),
        },
        content=b"%PDF reviewed buyer proof",
    )
    assert upload.status_code == 201, upload.text
    proof_id = upload.json()["id"]
    review = client.post(
        f"/api/v1/dispositions/proof-documents/{proof_id}/verification",
        headers=HEADERS,
        json={
            "decision": "verified",
            "verification_source": "manual document review",
            "institution_name": "Example Bank",
            "verified_amount_cents": 50000000,
            "expires_at": future_expiry.isoformat(),
            "notes": "Amount, institution, and expiration were reviewed.",
        },
    )
    assert review.status_code == 200, review.text

    current = client.get(f"/api/v1/buyers/{buyer_id}", headers=HEADERS)
    assert current.status_code == 200, current.text
    assert current.json()["proof_of_funds_status"] == "verified"

    proof = db_session.get(BuyerProofDocument, UUID(proof_id))
    stored_buyer = db_session.get(Buyer, UUID(str(buyer_id)))
    assert proof is not None and stored_buyer is not None
    proof.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    assert stored_buyer.proof_of_funds_status == "verified"

    expired = client.get(f"/api/v1/buyers/{buyer_id}", headers=HEADERS)
    assert expired.status_code == 200, expired.text
    assert expired.json()["proof_of_funds_status"] == "expired"
    assert expired.json()["proof_of_funds_expires_at"] is None


def test_buyer_last_contact_excludes_voicemail(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    buyer = create_buyer(client)
    buyer_id = UUID(str(buyer["id"]))
    link = db_session.scalar(
        select(ConversationContextLink).where(
            ConversationContextLink.buyer_id == buyer_id,
            ConversationContextLink.context_type == "buyer",
        )
    )
    assert link is not None
    conversation = db_session.get(Conversation, link.conversation_id)
    assert conversation is not None

    sms_at = datetime.now(UTC) - timedelta(minutes=5)
    voicemail_at = datetime.now(UTC)
    sms = CommunicationRecord(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=conversation.contact_id,
        actor_user_id=None,
        direction="inbound",
        channel="sms",
        status="received",
        provider="twilio",
        provider_message_id="buyer-last-contact-sms",
        subject=None,
        body="I am still buying in Atlanta.",
        occurred_at=sms_at,
        external_payload=None,
        communication_metadata={"source": "test"},
    )
    voicemail = CommunicationRecord(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        lead_id=None,
        contact_id=conversation.contact_id,
        actor_user_id=None,
        direction="inbound",
        channel="call",
        status="completed",
        provider="twilio",
        provider_message_id="buyer-last-contact-voicemail",
        subject=None,
        body="Voicemail from buyer",
        occurred_at=voicemail_at,
        external_payload={"voicemail": True},
        communication_metadata={"source": "test"},
    )
    db_session.add_all([sms, voicemail])
    db_session.flush()
    db_session.add(
        CallRecord(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            lead_id=None,
            contact_id=conversation.contact_id,
            actor_user_id=None,
            communication_record_id=voicemail.id,
            provider="twilio",
            provider_call_id="buyer-last-contact-voicemail-call",
            direction="inbound",
            status="completed",
            from_number="+14045550101",
            to_number="+14045550102",
            started_at=voicemail_at,
            answered_at=voicemail_at,
            ended_at=voicemail_at + timedelta(seconds=20),
            duration_seconds=20,
            disposition="voicemail",
            recording_consent_status="not_requested",
            call_metadata={"voicemail": True},
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/buyers/{buyer_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    last_contact_at = datetime.fromisoformat(
        response.json()["last_contact_at"].replace("Z", "+00:00")
    )
    if last_contact_at.tzinfo is None:
        last_contact_at = last_contact_at.replace(tzinfo=UTC)
    assert last_contact_at == sms_at


def test_profile_relationship_follow_up_timeline_and_verification(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    buyer = create_buyer(client)
    buyer_id = buyer["id"]
    due_at = datetime.now(UTC) + timedelta(days=2)

    follow_up = client.post(
        f"/api/v1/buyers/{buyer_id}/relationship-activities",
        headers=HEADERS,
        json={
            "engagement_type": "follow_up",
            "scheduled_at": due_at.isoformat(),
            "notes": "Call after the buyer reviews the parcel package.",
        },
    )
    assert follow_up.status_code == 201, follow_up.text
    assert follow_up.json()["status"] == "open"
    buyer_row = db_session.get(Buyer, UUID(str(buyer_id)))
    assert buyer_row is not None
    assert buyer_row.next_follow_up_at is not None

    note = client.post(
        f"/api/v1/buyers/{buyer_id}/relationship-activities",
        headers=HEADERS,
        json={"engagement_type": "note", "notes": "Prefers text before a phone call."},
    )
    assert note.status_code == 201, note.text
    assert note.json()["status"] == "completed"

    completed = client.patch(
        f"/api/v1/buyers/{buyer_id}/relationship-activities/{follow_up.json()['id']}",
        headers=HEADERS,
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text
    db_session.refresh(buyer_row)
    assert buyer_row.next_follow_up_at is None
    engagement = db_session.get(BuyerEngagement, UUID(follow_up.json()["id"]))
    assert engagement is not None and engagement.completed_at is not None

    verified = client.post(
        f"/api/v1/buyers/{buyer_id}/verification",
        headers=HEADERS,
        json={
            "verification_status": "verified",
            "reason": "Identity and buying criteria confirmed by phone.",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_status"] == "verified"
    assert verified.json()["verified_by_user_id"] is not None
    assert verified.json()["verified_at"] is not None

    profile = client.get(f"/api/v1/buyers/{buyer_id}/profile", headers=HEADERS)
    assert profile.status_code == 200, profile.text
    payload = profile.json()
    assert payload["legacy_criteria"]["verification_status"] == "unverified"
    assert payload["timeline"]["total"] >= 4
    assert any(
        item["event_type"] == "follow_up" for item in payload["timeline"]["items"]
    )
    compact_profile = client.get(
        f"/api/v1/buyers/{buyer_id}/profile?timeline_limit=1",
        headers=HEADERS,
    )
    assert compact_profile.status_code == 200, compact_profile.text
    compact_timeline = compact_profile.json()["timeline"]
    assert len(compact_timeline["items"]) == 1
    assert compact_timeline["total"] == payload["timeline"]["total"]
    assert compact_timeline["has_more"] is True
