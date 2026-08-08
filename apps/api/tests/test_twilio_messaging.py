from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.integrations.communications import (
    OutboundMessageRequest,
    OutboundMessageResult,
)
from app.integrations.twilio_messaging import TwilioMessagingProvider
from app.main import app
from app.models.foundation import (
    CommunicationDispatch,
    CommunicationProviderEvent,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    Conversation,
    SuppressionRecord,
    User,
    VoiceLine,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
AUTH_TOKEN = "test-auth-token"
MESSAGING_SERVICE_SID = "MG00000000000000000000000000000000"
STONEGATE_FROM_NUMBER = "+16785417725"
WEBHOOK_BASE_URL = "https://api.stonegate.test"


class FakeTwilioProvider:
    provider_name = "twilio"

    def __init__(self) -> None:
        self.requests: list[OutboundMessageRequest] = []

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        assert dry_run is False
        self.requests.append(request)
        return OutboundMessageResult(
            provider="twilio",
            provider_message_id="SM00000000000000000000000000000001",
            status="queued",
            raw_payload={
                "sid": "SM00000000000000000000000000000001",
                "status": "queued",
                "to": request.recipient,
            },
        )


class FakeMessagesResource:
    def __init__(self) -> None:
        self.create_payload: dict[str, object] | None = None

    def create(self, **payload: object) -> SimpleNamespace:
        self.create_payload = payload
        return SimpleNamespace(
            sid="SM00000000000000000000000000000009",
            status="accepted",
            to=payload["to"],
            from_=payload["from_"],
            messaging_service_sid=payload.get("messaging_service_sid"),
            error_code=None,
            error_message=None,
            num_segments="1",
        )


class FakeTwilioClient:
    def __init__(self) -> None:
        self.messages = FakeMessagesResource()


@pytest.fixture
def twilio_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "TWILIO_SMS_ENABLED": "true",
        "TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000000",
        "TWILIO_AUTH_TOKEN": AUTH_TOKEN,
        "TWILIO_SMS_FROM_NUMBER": STONEGATE_FROM_NUMBER,
        "TWILIO_WEBHOOK_BASE_URL": WEBHOOK_BASE_URL,
        "TWILIO_VALIDATE_WEBHOOK_SIGNATURES": "true",
        "TWILIO_SMS_ALLOWED_START_HOUR": "0",
        "TWILIO_SMS_ALLOWED_END_HOUR": "24",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def public_payload() -> dict[str, object]:
    return {
        "property_address": "55 Auburn Ave",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "sam@example.com",
        "preferred_contact_method": "phone",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "consent_to_contact": True,
        "sms_consent": True,
    }


def seed_consent_lead(db: Session, client: TestClient) -> Conversation:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert response.status_code == 201
    conversation = db.scalar(select(Conversation))
    assert conversation is not None
    return conversation


def signed_twilio_headers(path: str, payload: dict[str, str]) -> dict[str, str]:
    url = f"{WEBHOOK_BASE_URL}{path}"
    signature = RequestValidator(AUTH_TOKEN).compute_signature(url, payload)
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Twilio-Signature": signature,
    }


def post_signed_twilio(
    client: TestClient,
    path: str,
    payload: dict[str, str],
) -> Response:
    return cast(
        Response,
        client.post(
            path,
            content=urlencode(payload),
            headers=signed_twilio_headers(path, payload),
        ),
    )


def test_twilio_provider_uses_configured_stonegate_sender(
    twilio_settings: None,
) -> None:
    client = FakeTwilioClient()
    provider = TwilioMessagingProvider(
        get_settings(),
        client=client,
    )

    result = provider.send(
        OutboundMessageRequest(
            lead_id="lead-1",
            contact_id="contact-1",
            channel="sms",
            recipient="+14045551212",
            body="Stonegate sender selection test.",
            idempotency_key="sender-test-1",
        ),
        dry_run=False,
    )

    assert client.messages.create_payload is not None
    assert client.messages.create_payload["from_"] == STONEGATE_FROM_NUMBER
    assert "messaging_service_sid" not in client.messages.create_payload
    assert result.raw_payload["from"] == STONEGATE_FROM_NUMBER


def test_twilio_provider_uses_line_specific_sender(
    twilio_settings: None,
) -> None:
    client = FakeTwilioClient()
    provider = TwilioMessagingProvider(get_settings(), client=client)
    acquisitions_number = "+14045550001"

    provider.send(
        OutboundMessageRequest(
            lead_id="lead-1",
            contact_id="contact-1",
            channel="sms",
            recipient="+14045551212",
            body="Stonegate line-specific sender test.",
            idempotency_key="sender-test-2",
            metadata={"sender_number": acquisitions_number},
        ),
        dry_run=False,
    )

    assert client.messages.create_payload is not None
    assert client.messages.create_payload["from_"] == acquisitions_number
    assert "messaging_service_sid" not in client.messages.create_payload


def test_twilio_provider_supports_optional_messaging_service(
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", MESSAGING_SERVICE_SID)
    get_settings.cache_clear()
    client = FakeTwilioClient()
    provider = TwilioMessagingProvider(get_settings(), client=client)

    provider.send(
        OutboundMessageRequest(
            lead_id="lead-1",
            contact_id="contact-1",
            channel="sms",
            recipient="+14045551212",
            body="Optional Messaging Service test.",
            idempotency_key="sender-test-3",
        ),
        dry_run=False,
    )

    assert client.messages.create_payload is not None
    assert client.messages.create_payload["messaging_service_sid"] == MESSAGING_SERVICE_SID


def test_outbound_sms_is_compliance_gated_idempotent_and_status_tracked(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)
    acquisitions_line = VoiceLine(
        organization_id=conversation.organization_id,
        assigned_user_id=None,
        fallback_user_id=None,
        provider="twilio",
        provider_phone_number_id=None,
        phone_number="+14045550001",
        label="Stonegate Acquisitions",
        department_key="acquisitions",
        purpose_key="seller_conversations",
        status="active",
        is_default=True,
        inbound_route="conversation_owner",
        coverage_timezone="America/New_York",
        coverage_start_hour=9,
        coverage_end_hour=20,
        missed_call_action="fallback_then_voicemail",
        line_metadata={"source": "test"},
    )
    db_session.add(acquisitions_line)
    db_session.commit()
    fake_provider = FakeTwilioProvider()
    monkeypatch.setattr(
        "app.services.messaging.get_twilio_messaging_provider",
        lambda: fake_provider,
    )
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    request_payload = {
        "body": "Hi Sam, this is Stonegate following up about 55 Auburn Ave.",
        "idempotency_key": "sms-request-0001",
    }

    first = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/messages/sms",
        headers=headers,
        json=request_payload,
    )
    second = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/messages/sms",
        headers=headers,
        json=request_payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["recipient"] == "+14045551212"
    assert len(fake_provider.requests) == 1
    assert fake_provider.requests[0].metadata["sender_number"] == "+14045550001"
    communication = db_session.scalar(
        select(CommunicationRecord).where(CommunicationRecord.provider == "twilio")
    )
    dispatch = db_session.scalar(select(CommunicationDispatch))
    assert communication is not None
    assert dispatch is not None
    assert communication.status == "queued"
    assert communication.provider_message_id == "SM00000000000000000000000000000001"
    assert dispatch.communication_record_id == communication.id

    status_payload = {
        "MessageSid": communication.provider_message_id,
        "MessageStatus": "delivered",
        "ErrorCode": "",
        "MessagingServiceSid": MESSAGING_SERVICE_SID,
    }
    status_path = "/api/v1/webhooks/twilio/messaging/status"
    status_response = post_signed_twilio(client, status_path, status_payload)
    duplicate_status_response = post_signed_twilio(client, status_path, status_payload)

    assert status_response.status_code == 204
    assert duplicate_status_response.status_code == 204
    db_session.expire_all()
    updated_communication = db_session.get(CommunicationRecord, communication.id)
    assert updated_communication is not None
    assert updated_communication.status == "delivered"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(CommunicationProviderEvent)
                .where(CommunicationProviderEvent.event_type == "messaging.status")
            )
            or 0
        )
        == 1
    )


def test_outbound_sms_requires_consent_and_respects_suppression(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)
    fake_provider = FakeTwilioProvider()
    monkeypatch.setattr(
        "app.services.messaging.get_twilio_messaging_provider",
        lambda: fake_provider,
    )
    contact = db_session.get(Contact, conversation.contact_id)
    assert contact is not None
    db_session.add(
        SuppressionRecord(
            organization_id=conversation.organization_id,
            contact_id=contact.id,
            channel="sms",
            normalized_address="+14045551212",
            status="active",
            reason="Seller texted STOP",
            source="test",
            provider="twilio",
            external_event_id="SM-stop",
            suppressed_at=conversation.created_at,
            lifted_at=None,
            suppression_metadata=None,
        )
    )
    db_session.commit()

    suppressed_response = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/messages/sms",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"body": "This must not send.", "idempotency_key": "sms-suppressed-1"},
    )

    assert suppressed_response.status_code == 422
    assert "suppressed" in suppressed_response.json()["detail"].lower()
    assert fake_provider.requests == []

    db_session.query(SuppressionRecord).delete()
    db_session.query(ConsentRecord).delete()
    db_session.commit()
    missing_consent_response = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/messages/sms",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"body": "This also must not send.", "idempotency_key": "sms-no-consent-1"},
    )
    assert missing_consent_response.status_code == 422
    assert "consent" in missing_consent_response.json()["detail"].lower()
    assert fake_provider.requests == []


def test_inbound_sms_is_validated_idempotent_and_updates_opt_out_state(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)
    inbound_path = "/api/v1/webhooks/twilio/messaging/incoming"
    base_payload = {
        "From": "+14045551212",
        "To": "+14045550000",
        "MessagingServiceSid": MESSAGING_SERVICE_SID,
        "Body": "I can talk tomorrow.",
        "MessageSid": "SM00000000000000000000000000000002",
    }

    response = post_signed_twilio(client, inbound_path, base_payload)
    duplicate_response = post_signed_twilio(client, inbound_path, base_payload)

    assert response.status_code == 200
    assert duplicate_response.status_code == 200
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(CommunicationRecord)
                .where(CommunicationRecord.direction == "inbound")
            )
            or 0
        )
        == 1
    )
    db_session.expire_all()
    updated_conversation = db_session.get(Conversation, conversation.id)
    assert updated_conversation is not None
    assert updated_conversation.unread_count == 1

    stop_payload = {
        **base_payload,
        "Body": "STOP",
        "OptOutType": "STOP",
        "MessageSid": "SM00000000000000000000000000000003",
    }
    stop_response = post_signed_twilio(client, inbound_path, stop_payload)
    assert stop_response.status_code == 200
    suppression = db_session.scalar(select(SuppressionRecord))
    assert suppression is not None
    assert suppression.status == "active"
    latest_consent = db_session.scalar(
        select(ConsentRecord).order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
    )
    assert latest_consent is not None
    assert latest_consent.status == "revoked"

    start_payload = {
        **base_payload,
        "Body": "START",
        "OptOutType": "START",
        "MessageSid": "SM00000000000000000000000000000004",
    }
    start_response = post_signed_twilio(client, inbound_path, start_payload)
    assert start_response.status_code == 200
    db_session.expire_all()
    suppression = db_session.scalar(select(SuppressionRecord))
    assert suppression is not None
    assert suppression.status == "lifted"
    latest_consent = db_session.scalar(
        select(ConsentRecord).order_by(ConsentRecord.created_at.desc(), ConsentRecord.id.desc())
    )
    assert latest_consent is not None
    assert latest_consent.status == "granted"


def test_dispositions_number_does_not_attach_buyer_sms_to_seller_conversation(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)
    dispositions_number = "+14045550002"
    db_session.add(
        VoiceLine(
            organization_id=conversation.organization_id,
            assigned_user_id=None,
            fallback_user_id=None,
            provider="twilio",
            provider_phone_number_id=None,
            phone_number=dispositions_number,
            label="Stonegate Dispositions",
            department_key="dispositions",
            purpose_key="buyer_relations",
            status="active",
            is_default=False,
            inbound_route="assigned_user",
            coverage_timezone="America/New_York",
            coverage_start_hour=9,
            coverage_end_hour=20,
            missed_call_action="fallback_then_voicemail",
            line_metadata={"source": "test"},
        )
    )
    db_session.commit()

    response = post_signed_twilio(
        client,
        "/api/v1/webhooks/twilio/messaging/incoming",
        {
            "From": "+14045551212",
            "To": dispositions_number,
            "MessagingServiceSid": MESSAGING_SERVICE_SID,
            "Body": "I am interested in buying this property.",
            "MessageSid": "SM00000000000000000000000000000012",
        },
    )

    assert response.status_code == 200
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id
            == "inbound:SM00000000000000000000000000000012"
        )
    )
    assert event is not None
    assert event.processing_status == "unmatched"
    assert (
        db_session.scalar(
            select(CommunicationRecord).where(
                CommunicationRecord.provider_message_id == "SM00000000000000000000000000000012"
            )
        )
        is None
    )


def test_twilio_webhooks_reject_invalid_signatures_and_services(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    seed_consent_lead(db_session, client)
    path = "/api/v1/webhooks/twilio/messaging/incoming"
    payload = {
        "From": "+14045551212",
        "To": "+14045550000",
        "MessagingServiceSid": MESSAGING_SERVICE_SID,
        "Body": "Hello",
        "MessageSid": "SM00000000000000000000000000000005",
    }
    invalid_signature_response = client.post(
        path,
        content=urlencode(payload),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": "invalid",
        },
    )
    assert invalid_signature_response.status_code == 403

    monkeypatch.setenv("TWILIO_MESSAGING_SERVICE_SID", MESSAGING_SERVICE_SID)
    get_settings.cache_clear()
    unexpected_service_payload = {
        **payload,
        "MessagingServiceSid": "MG11111111111111111111111111111111",
    }
    unexpected_service_response = post_signed_twilio(
        client,
        path,
        unexpected_service_payload,
    )
    assert unexpected_service_response.status_code == 403
    assert int(db_session.scalar(select(func.count()).select_from(CommunicationRecord)) or 0) == 0


def test_inbox_detail_reports_sms_eligibility(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
) -> None:
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)

    response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    eligibility = response.json()["sms_eligibility"]
    assert eligibility["can_send"] is True
    assert eligibility["recipient"] == "+14045551212"
    assert eligibility["consent_status"] == "granted"


def test_sms_eligibility_identifies_missing_render_setting(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWILIO_SMS_FROM_NUMBER")
    get_settings.cache_clear()
    client = TestClient(app)
    conversation = seed_consent_lead(db_session, client)

    response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    blockers = response.json()["sms_eligibility"]["blockers"]
    assert any("TWILIO_SMS_FROM_NUMBER" in blocker for blocker in blockers)


def test_buyer_sms_uses_dispositions_line_and_routes_reply_to_buyer_thread(
    db_session: Session,
    api_db_override: None,
    twilio_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    dispositions_number = "+14708887952"
    db_session.add(
        VoiceLine(
            organization_id=owner.organization_id,
            assigned_user_id=owner.id,
            fallback_user_id=None,
            assigned_team_id=None,
            provider="twilio",
            provider_phone_number_id=None,
            phone_number=dispositions_number,
            label="Stonegate Dispositions",
            department_key="dispositions",
            purpose_key="buyer_relations",
            status="active",
            is_default=False,
            inbound_route="assigned_user",
            ring_strategy="sequential",
            coverage_timezone="America/New_York",
            coverage_start_hour=0,
            coverage_end_hour=24,
            missed_call_action="fallback_then_voicemail",
            line_metadata={"source": "test"},
        )
    )
    db_session.commit()
    seller_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert seller_response.status_code == 201, seller_response.text
    buyer_response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Alex Investor",
            "phone": "+14045551212",
            "buyer_type": "cash_buyer",
            "phone_contact_permission": True,
            "sms_consent": True,
        },
    )
    assert buyer_response.status_code == 201, buyer_response.text
    conversation = db_session.scalar(
        select(Conversation).where(Conversation.conversation_type == "buyer")
    )
    seller_conversation = db_session.scalar(
        select(Conversation).where(Conversation.conversation_type == "lead")
    )
    assert conversation is not None
    assert seller_conversation is not None
    assert seller_conversation.id != conversation.id
    fake_provider = FakeTwilioProvider()
    monkeypatch.setattr(
        "app.services.messaging.get_twilio_messaging_provider",
        lambda: fake_provider,
    )

    outbound = client.post(
        f"/api/v1/inbox/conversations/{conversation.id}/messages/sms",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"body": "Is this deal in your buy box?", "idempotency_key": "buyer-sms-0001"},
    )
    assert outbound.status_code == 201, outbound.text
    assert fake_provider.requests[0].metadata["sender_number"] == dispositions_number

    inbound_payload = {
        "MessageSid": "SM00000000000000000000000000000077",
        "From": "+14045551212",
        "To": dispositions_number,
        "Body": "Yes, send me the details.",
    }
    inbound = post_signed_twilio(
        client,
        "/api/v1/webhooks/twilio/messaging/incoming",
        inbound_payload,
    )
    assert inbound.status_code == 200, inbound.text
    received = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == inbound_payload["MessageSid"]
        )
    )
    assert received is not None
    assert received.conversation_id == conversation.id
    assert received.conversation_id != seller_conversation.id
    assert received.lead_id is None
