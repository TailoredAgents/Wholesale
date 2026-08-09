import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from svix.webhooks import Webhook

from app.core.config import Settings, get_settings
from app.integrations.resend_email import (
    ResendAttachmentTooLargeError,
    ResendEmailDeliveryProvider,
)
from app.main import app
from app.models.foundation import (
    AuditEvent,
    CommunicationParticipant,
    CommunicationProviderEvent,
    CommunicationRecord,
    ContactMethod,
    Conversation,
    EmailAttachment,
    User,
)
from app.routers import resend_webhooks as resend_webhooks_router
from app.services.bootstrap import bootstrap_foundation
from app.services.resend_email_events import (
    ResendLeaseLostError,
    ResendLifecycleNotReadyError,
    claim_next_resend_event,
    complete_resend_event,
    finalize_resend_event_claim,
    process_next_resend_event,
    received_email_is_known,
    record_resend_event_failure,
    recover_next_received_email,
)

OWNER_EMAIL = "owner@example.com"
OWNER_HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}
WEBHOOK_SECRET = "whsec_dGVzdC1yZXNlbmQtd2ViaG9vay1zZWNyZXQ="


@pytest.fixture
def resend_inbound_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "APP_ENV": "local",
        "DEV_AUTH_ENABLED": "true",
        "COMMUNICATION_PROVIDER_MODE": "live",
        "EMAIL_ENABLED": "true",
        "EMAIL_PROVIDER": "resend",
        "EMAIL_SYNC_ENABLED": "true",
        "RESEND_API_KEY": "re_test",
        "RESEND_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "RESEND_SENDING_DOMAIN": "stonegatehb.com",
        "RESEND_RECEIVING_DOMAIN": "stonegatehb.com",
        "RESEND_DEFAULT_FROM_EMAIL": "offers@stonegatehb.com",
        "RESEND_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        "DOCUMENT_STORAGE_PROVIDER": "database",
        "DOCUMENT_MALWARE_SCANNER": "disabled",
        "DOCUMENT_MALWARE_SCAN_REQUIRED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    try:
        yield settings
    finally:
        get_settings.cache_clear()


def public_payload() -> dict[str, object]:
    return {
        "property_address": "88 Peachtree Street",
        "property_city": "Atlanta",
        "property_state": "GA",
        "property_postal_code": "30303",
        "name": "Sam Seller",
        "phone": "4045551212",
        "email": "seller@example.com",
        "preferred_contact_method": "email",
        "reason_for_selling": "Inherited property",
        "desired_timeline": "30 days",
        "consent_to_contact": True,
        "sms_consent": False,
    }


def prepare_conversation(
    db_session: Session,
    client: TestClient,
) -> tuple[str, Conversation, CommunicationRecord]:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Austin",
    )
    alias_response = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "offers@stonegatehb.com",
            "display_name": "Stonegate Home Buyers",
            "alias_type": "department",
            "purpose_key": "seller_intake",
            "is_default": True,
        },
    )
    assert alias_response.status_code == 201, alias_response.text
    lead_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert lead_response.status_code == 201, lead_response.text
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    outbound = CommunicationRecord(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        lead_id=conversation.lead_id,
        contact_id=conversation.contact_id,
        actor_user_id=None,
        direction="outbound",
        channel="email",
        status="sent",
        provider="resend",
        provider_message_id="outbound-1",
        subject="Your Stonegate appointment",
        body="Can we meet Tuesday?",
        occurred_at=datetime.now(UTC) - timedelta(minutes=5),
        external_payload={"id": "outbound-1"},
        communication_metadata={
            "email_sender_alias_id": alias_response.json()["id"],
            "provider_thread_id": "outbound-1",
            "rfc_message_id": "<outbound-1@resend.test>",
            "from": "offers@stonegatehb.com",
            "to": "seller@example.com",
        },
    )
    db_session.add(outbound)
    db_session.commit()
    return str(alias_response.json()["id"]), conversation, outbound


def signed_webhook(
    client: TestClient,
    *,
    event_id: str,
    payload: dict[str, Any],
    timestamp: datetime | None = None,
) -> httpx.Response:
    occurred_at = timestamp or datetime.now(UTC)
    body = json.dumps(payload, separators=(",", ":"))
    signature = Webhook(WEBHOOK_SECRET).sign(event_id, occurred_at, body)
    return cast(
        httpx.Response,
        client.post(
            "/api/v1/webhooks/resend",
            content=body,
            headers={
                "content-type": "application/json",
                "svix-id": event_id,
                "svix-timestamp": str(int(occurred_at.timestamp())),
                "svix-signature": signature,
            },
        ),
    )


def inbound_message(
    provider_message_id: str,
    *,
    with_attachment: bool = False,
) -> dict[str, Any]:
    attachments = (
        [
            {
                "id": "attachment-1",
                "filename": "seller-document.pdf",
                "content_type": "application/pdf",
                "content_disposition": "attachment",
                "content_id": None,
                "size": 17,
            }
        ]
        if with_attachment
        else []
    )
    return {
        "id": provider_message_id,
        "to": ["offers@stonegatehb.com"],
        "from": "Sam Seller <seller@example.com>",
        "created_at": datetime.now(UTC).isoformat(),
        "subject": "Re: Your Stonegate appointment",
        "text": "Tuesday works for me.",
        "html": "<p>Tuesday works for me.</p>",
        "headers": {
            "in-reply-to": "<outbound-1@resend.test>",
            "references": "<outbound-1@resend.test>",
        },
        "message_id": f"<{provider_message_id}@seller.test>",
        "cc": [],
        "bcc": [],
        "received_for": [],
        "attachments": attachments,
    }


def provider_for_messages(messages: dict[str, dict[str, Any]]) -> ResendEmailDeliveryProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/attachments/attachment-1"):
            return httpx.Response(
                200,
                json={
                    "id": "attachment-1",
                    "filename": "seller-document.pdf",
                    "size": 17,
                    "content_type": "application/pdf",
                    "download_url": ("https://inbound-cdn.resend.com/inbound-1/attachment-1"),
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                },
                request=request,
            )
        if request.url.host == "inbound-cdn.resend.com":
            return httpx.Response(
                200,
                content=b"%PDF seller file",
                request=request,
            )
        provider_message_id = path.rsplit("/", 1)[-1]
        message = messages.get(provider_message_id)
        assert message is not None, path
        return httpx.Response(200, json=message, request=request)

    return ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_resend_webhook_rejects_an_oversized_body_before_verification(
    api_db_override: None,
    resend_inbound_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(resend_webhooks_router, "MAX_WEBHOOK_BYTES", 8)

    response = TestClient(app).post(
        "/api/v1/webhooks/resend",
        content=b"123456789",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Resend webhook payload is too large."


def test_signed_inbound_reply_is_durable_threaded_and_replay_safe(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    payload = {
        "type": "email.received",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {
            "email_id": "inbound-1",
            "from": "seller@example.com",
            "to": ["offers@stonegatehb.com"],
            "subject": "Re: Your Stonegate appointment",
        },
    }
    accepted = signed_webhook(client, event_id="evt-inbound-1", payload=payload)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["created"] is True
    assert (
        db_session.scalar(
            select(CommunicationProviderEvent.processing_status).where(
                CommunicationProviderEvent.external_event_id == "evt-inbound-1"
            )
        )
        == "received"
    )

    provider = provider_for_messages(
        {"inbound-1": inbound_message("inbound-1", with_attachment=True)}
    )
    processed = process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    assert processed is not None
    inbound = db_session.scalar(
        select(CommunicationRecord).where(CommunicationRecord.provider_message_id == "inbound-1")
    )
    assert inbound is not None
    assert inbound.conversation_id == conversation.id
    assert inbound.body == "Tuesday works for me."
    participants = db_session.scalars(
        select(CommunicationParticipant).where(
            CommunicationParticipant.communication_record_id == inbound.id
        )
    ).all()
    assert {
        (participant.participant_role, participant.normalized_email) for participant in participants
    } == {
        ("from", "seller@example.com"),
        ("to", "offers@stonegatehb.com"),
    }
    assert (
        next(
            participant for participant in participants if participant.participant_role == "from"
        ).contact_id
        == conversation.contact_id
    )
    db_session.refresh(conversation)
    assert conversation.unread_count == 1

    attachment = db_session.scalar(select(EmailAttachment))
    assert attachment is not None
    assert attachment.storage_provider == "database"
    assert attachment.content_data == b"%PDF seller file"
    download = client.get(
        f"/api/v1/email/attachments/{attachment.id}",
        headers=OWNER_HEADERS,
    )
    assert download.status_code == 200
    assert download.content == b"%PDF seller file"

    replay = signed_webhook(client, event_id="evt-inbound-1", payload=payload)
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CommunicationRecord)
            .where(CommunicationRecord.provider_message_id == "inbound-1")
        )
        == 1
    )


def test_inbound_email_uses_retained_provider_thread_when_rfc_headers_are_missing(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    message = inbound_message("provider-thread-1")
    message["headers"] = {}
    message["provider_thread_id"] = "outbound-1"
    accepted = signed_webhook(
        client,
        event_id="evt-provider-thread",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "provider-thread-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"provider-thread-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-provider-thread"
        )
    )
    assert event is not None
    assert event.processing_status == "processed"
    assert event.payload["_routing"]["rule"] == "provider_thread"
    inbound = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "provider-thread-1"
        )
    )
    assert inbound is not None
    assert inbound.conversation_id == conversation.id


def test_inbound_email_matches_unique_sender_and_recipient_alias(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    message = inbound_message("sender-alias-1")
    message["headers"] = {}
    accepted = signed_webhook(
        client,
        event_id="evt-sender-alias",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "sender-alias-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"sender-alias-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-sender-alias"
        )
    )
    assert event is not None
    assert event.payload["_routing"]["rule"] == "sender_and_alias"
    inbound = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "sender-alias-1"
        )
    )
    assert inbound is not None
    assert inbound.conversation_id == conversation.id


def test_new_correspondent_routes_to_alias_owner_as_general_conversation(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Austin",
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    alias_response = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "austin@stonegatehb.com",
            "display_name": "Austin at Stonegate",
            "alias_type": "named",
            "purpose_key": "owner",
            "owner_user_id": str(owner.id),
        },
    )
    assert alias_response.status_code == 201, alias_response.text
    message = inbound_message("new-correspondent-1")
    message["to"] = ["austin@stonegatehb.com"]
    message["from"] = "New Partner <partner@example.net>"
    message["headers"] = {}
    accepted = signed_webhook(
        client,
        event_id="evt-new-correspondent",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "new-correspondent-1",
                "from": "partner@example.net",
                "to": ["austin@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"new-correspondent-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-new-correspondent"
        )
    )
    assert event is not None
    assert event.processing_status == "processed"
    assert event.payload["_routing"]["rule"] == "alias_owner_or_team"
    assert event.payload["_routing"]["created_general_conversation"] is True
    conversation = db_session.get(Conversation, event.conversation_id)
    assert conversation is not None
    assert conversation.conversation_type == "general"
    assert conversation.lead_id is None
    assert conversation.assigned_user_id == owner.id
    assert str(conversation.source_alias_id) == alias_response.json()["id"]
    contact_method = db_session.scalar(
        select(ContactMethod).where(
            ContactMethod.contact_id == conversation.contact_id,
            ContactMethod.normalized_value == "partner@example.net",
        )
    )
    assert contact_method is not None
    communication = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "new-correspondent-1"
        )
    )
    assert communication is not None
    assert communication.conversation_id == conversation.id


def test_restricted_alias_never_falls_back_to_unrelated_standard_thread(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _standard_alias_id, seller_conversation, _outbound = prepare_conversation(
        db_session,
        client,
    )
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    restricted_alias = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "closing@stonegatehb.com",
            "display_name": "Stonegate Closing",
            "alias_type": "department",
            "purpose_key": "closing",
            "owner_user_id": str(owner.id),
        },
    )
    assert restricted_alias.status_code == 201, restricted_alias.text
    message = inbound_message("restricted-alias-1")
    message["to"] = ["offers@stonegatehb.com", "closing@stonegatehb.com"]
    accepted = signed_webhook(
        client,
        event_id="evt-restricted-alias",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "restricted-alias-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com", "closing@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"restricted-alias-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-restricted-alias"
        )
    )
    assert event is not None
    assert event.payload["_routing"]["rule"] == "alias_owner_or_team"
    assert event.conversation_id != seller_conversation.id
    restricted_conversation = db_session.get(Conversation, event.conversation_id)
    assert restricted_conversation is not None
    assert restricted_conversation.visibility_scope == "restricted"
    assert str(restricted_conversation.source_alias_id) == restricted_alias.json()["id"]


def test_inbound_email_from_stonegate_identity_is_ignored_as_a_loop(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    message = inbound_message("internal-loop-1")
    message["from"] = "Stonegate <offers@stonegatehb.com>"
    message["headers"] = {}
    accepted = signed_webhook(
        client,
        event_id="evt-internal-loop",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "internal-loop-1",
                "from": "offers@stonegatehb.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"internal-loop-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-internal-loop"
        )
    )
    assert event is not None
    assert event.processing_status == "ignored"
    assert event.payload["_routing"]["rule"] == "internal_loop_protection"
    assert (
        db_session.scalar(
            select(CommunicationRecord).where(
                CommunicationRecord.provider_message_id == "internal-loop-1"
            )
        )
        is None
    )


def test_delivery_events_are_idempotent_and_cannot_regress_status(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, _conversation, outbound = prepare_conversation(db_session, client)
    delivered_at = datetime.now(UTC)
    delivered = signed_webhook(
        client,
        event_id="evt-delivered",
        payload={
            "type": "email.delivered",
            "created_at": delivered_at.isoformat(),
            "data": {"email_id": "outbound-1"},
        },
    )
    assert delivered.status_code == 200
    assert process_next_resend_event(db_session, resend_inbound_settings) is not None
    db_session.refresh(outbound)
    assert outbound.status == "delivered"

    delayed = signed_webhook(
        client,
        event_id="evt-delayed",
        payload={
            "type": "email.delivery_delayed",
            "created_at": (delivered_at - timedelta(minutes=1)).isoformat(),
            "data": {"email_id": "outbound-1"},
        },
    )
    assert delayed.status_code == 200
    assert process_next_resend_event(db_session, resend_inbound_settings) is not None
    db_session.refresh(outbound)
    assert outbound.status == "delivered"

    invalid = client.post(
        "/api/v1/webhooks/resend",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "svix-id": "evt-invalid",
            "svix-timestamp": str(int(datetime.now(UTC).timestamp())),
            "svix-signature": "v1,invalid",
        },
    )
    assert invalid.status_code == 401


def test_recovery_scan_enqueues_and_imports_a_missed_received_email(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    message = inbound_message("recovery-1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/emails/receiving":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "has_more": False,
                    "data": [
                        {
                            "id": "recovery-1",
                            "to": ["offers@stonegatehb.com"],
                            "from": "seller@example.com",
                            "created_at": message["created_at"],
                            "subject": message["subject"],
                            "message_id": message["message_id"],
                            "attachments": [],
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(200, json=message, request=request)

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    recovered_event_id = recover_next_received_email(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    assert recovered_event_id is not None
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    recovered = db_session.scalar(
        select(CommunicationRecord).where(CommunicationRecord.provider_message_id == "recovery-1")
    )
    assert recovered is not None
    assert recovered.direction == "inbound"
    assert (
        recover_next_received_email(
            db_session,
            resend_inbound_settings,
            client=provider,
        )
        is None
    )


def test_unmatched_inbound_email_stays_in_the_review_queue(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    message = inbound_message("unmatched-1")
    message["from"] = "Unknown Person <unknown@example.net>"
    message["headers"] = {}
    accepted = signed_webhook(
        client,
        event_id="evt-unmatched",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "unmatched-1",
                "from": "unknown@example.net",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    provider = provider_for_messages({"unmatched-1": message})
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-unmatched"
        )
    )
    assert event is not None
    assert event.processing_status == "unmatched"
    assert event.payload["_routing"]["candidate_conversation_ids"] == []
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CommunicationRecord)
            .where(CommunicationRecord.provider_message_id == "unmatched-1")
        )
        == 0
    )

    exceptions = client.get(
        "/api/v1/email/routing-exceptions",
        headers=OWNER_HEADERS,
    )
    assert exceptions.status_code == 200, exceptions.text
    assert exceptions.json()["items"][0]["id"] == str(event.id)
    resolved = client.post(
        f"/api/v1/email/routing-exceptions/{event.id}/resolve",
        headers=OWNER_HEADERS,
        json={"conversation_id": str(db_session.scalar(select(Conversation.id)))},
    )
    assert resolved.status_code == 200, resolved.text
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    routed = db_session.scalar(
        select(CommunicationRecord).where(CommunicationRecord.provider_message_id == "unmatched-1")
    )
    assert routed is not None
    assert routed.conversation_id == db_session.scalar(select(Conversation.id))
    assert (
        client.get(
            "/api/v1/email/routing-exceptions",
            headers=OWNER_HEADERS,
        ).json()["items"]
        == []
    )


def test_poison_event_backoff_does_not_block_a_later_received_email(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    for event_id, provider_message_id in (
        ("evt-poison", "poison-1"),
        ("evt-after-poison", "after-poison-1"),
    ):
        accepted = signed_webhook(
            client,
            event_id=event_id,
            payload={
                "type": "email.received",
                "created_at": datetime.now(UTC).isoformat(),
                "data": {
                    "email_id": provider_message_id,
                    "from": "seller@example.com",
                    "to": ["offers@stonegatehb.com"],
                },
            },
        )
        assert accepted.status_code == 200

    good_message = inbound_message("after-poison-1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/poison-1"):
            return httpx.Response(
                503,
                json={"message": "temporary provider failure"},
                request=request,
            )
        return httpx.Response(200, json=good_message, request=request)

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RuntimeError, match="temporary provider failure"):
        process_next_resend_event(
            db_session,
            resend_inbound_settings,
            client=provider,
        )
    poison = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-poison"
        )
    )
    assert poison is not None
    assert poison.processing_status == "retry"
    assert poison.attempt_count == 1
    assert poison.next_attempt_at is not None

    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    ) is not None
    good = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-after-poison"
        )
    )
    assert good is not None
    assert good.processing_status == "processed"
    assert db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "after-poison-1"
        )
    ) is not None


def test_stale_processing_event_is_reclaimed_after_its_lease(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-stale-claim",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "stale-claim-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-stale-claim"
        )
    )
    assert event is not None
    event.processing_status = "processing"
    event.processing_started_at = datetime.now(UTC) - timedelta(seconds=31)
    event.attempt_count = 1
    db_session.commit()

    settings = resend_inbound_settings.model_copy(
        update={"resend_event_processing_lease_seconds": 30}
    )
    provider = provider_for_messages({"stale-claim-1": inbound_message("stale-claim-1")})
    assert process_next_resend_event(db_session, settings, client=provider) == event.id
    db_session.refresh(event)
    assert event.processing_status == "processed"
    assert event.processing_started_at is None
    assert event.attempt_count == 2


def test_resend_retry_backoff_caps_and_terminally_dead_letters(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-exhausted",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "exhausted-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            503,
            json={"message": "still unavailable"},
            request=request,
        )

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    settings = resend_inbound_settings.model_copy(
        update={
            "resend_event_max_attempts": 3,
            "resend_event_retry_base_seconds": 2,
            "resend_event_retry_max_seconds": 3,
        }
    )
    retry_delays: list[float] = []
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-exhausted"
        )
    )
    assert event is not None
    for attempt in range(1, 4):
        with pytest.raises(RuntimeError, match="still unavailable"):
            process_next_resend_event(db_session, settings, client=provider)
        after_failure = datetime.now(UTC)
        db_session.refresh(event)
        assert event.attempt_count == attempt
        if attempt < 3:
            assert event.processing_status == "retry"
            assert event.next_attempt_at is not None
            next_attempt_at = event.next_attempt_at
            if next_attempt_at.tzinfo is None:
                next_attempt_at = next_attempt_at.replace(tzinfo=UTC)
            retry_delays.append((next_attempt_at - after_failure).total_seconds())
            event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            db_session.commit()

    assert 1.5 <= retry_delays[0] <= 2.5
    assert 2.5 <= retry_delays[1] <= 3.5
    assert event.processing_status == "dead_letter"
    assert event.next_attempt_at is None
    assert event.processing_started_at is None
    assert event.processed_at is not None
    assert request_count == 3
    assert process_next_resend_event(db_session, settings, client=provider) is None


def test_oversize_attachment_is_rejected_but_email_body_is_retained(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-oversize",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "oversize-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    message = inbound_message("oversize-1", with_attachment=True)
    message["attachments"][0]["size"] = (
        resend_inbound_settings.email_max_attachment_bytes + 1
    )
    provider = provider_for_messages({"oversize-1": message})

    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider,
    ) is not None
    communication = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "oversize-1"
        )
    )
    assert communication is not None
    assert communication.body == "Tuesday works for me."
    attachment = db_session.scalar(
        select(EmailAttachment).where(
            EmailAttachment.communication_record_id == communication.id
        )
    )
    assert attachment is not None
    assert attachment.content_data is None
    assert attachment.attachment_metadata is not None
    assert attachment.attachment_metadata["storage_status"] == "rejected"
    assert "size limit" in attachment.attachment_metadata["error"]
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-oversize"
        )
    )
    assert event is not None
    assert event.processing_status == "processed"


@pytest.mark.parametrize(
    ("headers", "stream"),
    [
        ({"content-length": "5"}, httpx.ByteStream(b"x")),
        ({}, httpx.ByteStream(b"12345")),
    ],
)
def test_resend_attachment_download_enforces_declared_and_actual_byte_caps(
    headers: dict[str, str],
    stream: httpx.ByteStream,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "inbound-cdn.resend.com":
            return httpx.Response(
                200,
                headers=headers,
                stream=stream,
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "attachment-1",
                "size": 0,
                "download_url": "https://inbound-cdn.resend.com/message/attachment-1",
            },
            request=request,
        )

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ResendAttachmentTooLargeError, match="size limit"):
        provider.download_received_attachment(
            "message-1",
            "attachment-1",
            max_bytes=4,
        )


def test_recovery_requeues_stale_processing_and_does_not_hide_dead_letters(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    now = datetime.now(UTC)
    stale = CommunicationProviderEvent(
        organization_id=conversation.organization_id,
        conversation_id=None,
        provider="resend",
        event_type="email.received",
        external_event_id="recovery:stale-recovery-1",
        processing_status="processing",
        payload={"type": "email.received", "data": {"email_id": "stale-recovery-1"}},
        received_at=now - timedelta(minutes=10),
        processed_at=None,
        attempt_count=1,
        next_attempt_at=None,
        processing_started_at=now - timedelta(minutes=10),
        error_message=None,
    )
    exhausted = CommunicationProviderEvent(
        organization_id=conversation.organization_id,
        conversation_id=None,
        provider="resend",
        event_type="email.received",
        external_event_id="recovery:exhausted-recovery-1",
        processing_status="dead_letter",
        payload={"type": "email.received", "data": {"email_id": "exhausted-recovery-1"}},
        received_at=now - timedelta(minutes=9),
        processed_at=now,
        attempt_count=resend_inbound_settings.resend_event_max_attempts,
        next_attempt_at=None,
        processing_started_at=None,
        error_message="exhausted",
    )
    db_session.add_all([stale, exhausted])
    db_session.commit()
    stale_before = now - timedelta(
        seconds=resend_inbound_settings.resend_event_processing_lease_seconds
    )
    assert not received_email_is_known(
        db_session,
        "stale-recovery-1",
        processing_stale_before=stale_before,
    )
    assert not received_email_is_known(
        db_session,
        "exhausted-recovery-1",
        processing_stale_before=stale_before,
    )

    listed_items = [
        {"id": "stale-recovery-1", "created_at": now.isoformat()},
        {"id": "exhausted-recovery-1", "created_at": now.isoformat()},
        {"id": "new-recovery-1", "created_at": now.isoformat()},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"object": "list", "has_more": False, "data": listed_items},
            request=request,
        )

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert recover_next_received_email(
        db_session,
        resend_inbound_settings,
        client=provider,
    ) == stale.id
    db_session.refresh(stale)
    assert stale.processing_status == "retry"
    assert stale.processing_started_at is None

    new_event_id = recover_next_received_email(
        db_session,
        resend_inbound_settings,
        client=provider,
    )
    assert new_event_id is not None
    new_event = db_session.get(CommunicationProviderEvent, new_event_id)
    assert new_event is not None
    assert new_event.external_event_id == "recovery:new-recovery-1"


def test_reclaimed_resend_lease_fences_stale_completion_and_failure(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-lease-fence",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "lease-fence-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    settings = resend_inbound_settings.model_copy(
        update={"resend_event_processing_lease_seconds": 30}
    )
    first_claim = claim_next_resend_event(db_session, settings)
    assert first_claim is not None
    first_token = first_claim.processing_token
    first_claim.event.processing_started_at = datetime.now(UTC) - timedelta(seconds=31)
    db_session.commit()

    second_claim = claim_next_resend_event(db_session, settings)
    assert second_claim is not None
    assert second_claim.event.id == first_claim.event.id
    assert second_claim.processing_token != first_token
    complete_resend_event(second_claim.event, "processed")
    with pytest.raises(ResendLeaseLostError, match="reclaimed"):
        finalize_resend_event_claim(db_session, second_claim.event, first_token)
    db_session.rollback()

    event = db_session.get(CommunicationProviderEvent, second_claim.event.id)
    assert event is not None
    assert event.processing_status == "processing"
    assert event.processing_token == second_claim.processing_token
    assert not record_resend_event_failure(
        db_session,
        event.id,
        RuntimeError("stale worker failed"),
        settings,
        processing_token=first_token,
    )
    db_session.refresh(event)
    assert event.processing_status == "processing"
    assert event.processing_token == second_claim.processing_token
    assert event.error_message is None


def test_lifecycle_event_retries_until_outbound_record_is_committed(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, _conversation, outbound = prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-early-delivered",
        payload={
            "type": "email.delivered",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "early-lifecycle-1",
                "to": ["seller@example.com"],
            },
        },
    )
    assert accepted.status_code == 200
    with pytest.raises(ResendLifecycleNotReadyError, match="before its outbound"):
        process_next_resend_event(db_session, resend_inbound_settings)

    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-early-delivered"
        )
    )
    assert event is not None
    assert event.processing_status == "retry"
    assert event.attempt_count == 1
    assert event.next_attempt_at is not None

    outbound.provider_message_id = "early-lifecycle-1"
    event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert process_next_resend_event(db_session, resend_inbound_settings) == event.id
    db_session.refresh(event)
    db_session.refresh(outbound)
    assert event.processing_status == "processed"
    assert event.attempt_count == 2
    assert outbound.status == "delivered"


def test_matched_route_is_checkpointed_before_attachment_retry(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
    monkeypatch: MonkeyPatch,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    accepted = signed_webhook(
        client,
        event_id="evt-route-checkpoint",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "route-checkpoint-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    message = inbound_message("route-checkpoint-1", with_attachment=True)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/attachments/attachment-1"):
            return httpx.Response(
                503,
                json={"message": "attachment service unavailable"},
                request=request,
            )
        return httpx.Response(200, json=message, request=request)

    failing_provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(failing_handler)),
    )
    with pytest.raises(RuntimeError, match="attachment service unavailable"):
        process_next_resend_event(
            db_session,
            resend_inbound_settings,
            client=failing_provider,
        )
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-route-checkpoint"
        )
    )
    assert event is not None
    assert event.processing_status == "retry"
    assert event.payload["_routing"]["status"] == "matched"
    assert event.payload["_routing"]["conversation_id"] == str(conversation.id)
    assert db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "route-checkpoint-1"
        )
    ) is None

    def routing_must_not_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("the checkpointed route should be reused")

    monkeypatch.setattr(
        "app.services.resend_email_events.resolve_inbound_route",
        routing_must_not_run,
    )
    event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider_for_messages({"route-checkpoint-1": message}),
    ) == event.id
    routed = db_session.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "route-checkpoint-1"
        )
    )
    assert routed is not None
    assert routed.conversation_id == conversation.id


def test_email_manager_can_review_and_audited_requeue_dead_letter(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, conversation, _outbound = prepare_conversation(db_session, client)
    user_response = client.post(
        "/api/v1/operations/users",
        headers=OWNER_HEADERS,
        json={
            "email": "rep@example.com",
            "display_name": "Acquisition Rep",
            "role_key": "acquisition_rep",
        },
    )
    assert user_response.status_code == 201, user_response.text
    event = CommunicationProviderEvent(
        organization_id=conversation.organization_id,
        conversation_id=None,
        provider="resend",
        event_type="email.received",
        external_event_id="evt-dead-letter-admin",
        processing_status="dead_letter",
        payload={
            "type": "email.received",
            "data": {
                "email_id": "dead-letter-admin-1",
                "from": "seller@example.com",
                "to": ["offers@stonegatehb.com"],
                "subject": "Offer follow-up",
            },
        },
        received_at=datetime.now(UTC) - timedelta(minutes=10),
        processed_at=datetime.now(UTC),
        attempt_count=resend_inbound_settings.resend_event_max_attempts,
        next_attempt_at=None,
        processing_started_at=None,
        processing_token=None,
        error_message="Resend remained unavailable.",
    )
    db_session.add(event)
    db_session.commit()
    rep_headers = {"X-Dev-User-Email": "rep@example.com"}
    assert client.get("/api/v1/email/dead-letters", headers=rep_headers).status_code == 403
    assert (
        client.post(
            f"/api/v1/email/dead-letters/{event.id}/requeue",
            headers=rep_headers,
            json={"reason": "Provider recovered; retry the inbound email."},
        ).status_code
        == 403
    )

    listed = client.get("/api/v1/email/dead-letters", headers=OWNER_HEADERS)
    assert listed.status_code == 200, listed.text
    assert event.processed_at is not None
    assert listed.json()["items"] == [
        {
            "id": str(event.id),
            "event_type": "email.received",
            "provider_message_id": "dead-letter-admin-1",
            "sender": "seller@example.com",
            "recipients": ["offers@stonegatehb.com"],
            "subject": "Offer follow-up",
            "received_at": event.received_at.isoformat().replace("+00:00", "Z"),
            "processed_at": event.processed_at.isoformat().replace("+00:00", "Z"),
            "attempt_count": resend_inbound_settings.resend_event_max_attempts,
            "error_message": "Resend remained unavailable.",
            "processing_status": "dead_letter",
        }
    ]
    reason = "Provider recovered; retry the inbound email."
    requeued = client.post(
        f"/api/v1/email/dead-letters/{event.id}/requeue",
        headers=OWNER_HEADERS,
        json={"reason": reason},
    )
    assert requeued.status_code == 200, requeued.text
    assert requeued.json()["processing_status"] == "retry"
    assert requeued.json()["attempt_count"] == 0
    db_session.refresh(event)
    assert event.processing_status == "retry"
    assert event.next_attempt_at is not None
    assert event.error_message is None
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "email.dead_letter_requeued",
            AuditEvent.entity_id == event.id,
        )
    )
    assert audit is not None
    assert audit.actor_type == "user"
    assert audit.reason == reason


def test_restricted_inbound_cannot_auto_or_manually_route_to_standard_conversation(
    db_session: Session,
    api_db_override: None,
    resend_inbound_settings: Settings,
) -> None:
    client = TestClient(app)
    _alias_id, standard_conversation, _outbound = prepare_conversation(db_session, client)
    restricted_alias = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "closing@stonegatehb.com",
            "display_name": "Stonegate Closing",
            "alias_type": "department",
            "purpose_key": "closing",
        },
    )
    assert restricted_alias.status_code == 201, restricted_alias.text
    message = inbound_message("restricted-standard-1")
    message["to"] = ["closing@stonegatehb.com"]
    accepted = signed_webhook(
        client,
        event_id="evt-restricted-standard",
        payload={
            "type": "email.received",
            "created_at": datetime.now(UTC).isoformat(),
            "data": {
                "email_id": "restricted-standard-1",
                "from": "seller@example.com",
                "to": ["closing@stonegatehb.com"],
            },
        },
    )
    assert accepted.status_code == 200
    assert process_next_resend_event(
        db_session,
        resend_inbound_settings,
        client=provider_for_messages({"restricted-standard-1": message}),
    ) is not None
    event = db_session.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.external_event_id == "evt-restricted-standard"
        )
    )
    assert event is not None
    assert event.processing_status == "unmatched"
    assert event.conversation_id is None
    assert event.payload["_routing"]["email_sender_alias_ids"] == [
        restricted_alias.json()["id"]
    ]

    resolved = client.post(
        f"/api/v1/email/routing-exceptions/{event.id}/resolve",
        headers=OWNER_HEADERS,
        json={"conversation_id": str(standard_conversation.id)},
    )
    assert resolved.status_code == 422, resolved.text
    assert "Restricted mailbox email" in resolved.json()["detail"]
    db_session.refresh(event)
    assert event.processing_status == "unmatched"
    assert event.conversation_id is None
