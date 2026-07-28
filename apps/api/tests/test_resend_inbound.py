import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from svix.webhooks import Webhook

from app.core.config import Settings, get_settings
from app.integrations.resend_email import ResendEmailDeliveryProvider
from app.main import app
from app.models.foundation import (
    CommunicationProviderEvent,
    CommunicationRecord,
    Conversation,
    EmailAttachment,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.resend_email_events import (
    process_next_resend_event,
    recover_next_received_email,
)

OWNER_EMAIL = "owner@example.com"
OWNER_HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}
WEBHOOK_SECRET = "whsec_dGVzdC1yZXNlbmQtd2ViaG9vay1zZWNyZXQ="


@pytest.fixture
def resend_inbound_settings(monkeypatch: MonkeyPatch) -> Iterator[Settings]:
    values = {
        "APP_ENV": "local",
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
    return client.post(
        "/api/v1/webhooks/resend",
        content=body,
        headers={
            "content-type": "application/json",
            "svix-id": event_id,
            "svix-timestamp": str(int(occurred_at.timestamp())),
            "svix-signature": signature,
        },
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
                    "download_url": (
                        "https://inbound-cdn.resend.com/inbound-1/attachment-1"
                    ),
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
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "inbound-1"
        )
    )
    assert inbound is not None
    assert inbound.conversation_id == conversation.id
    assert inbound.body == "Tuesday works for me."
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
        select(CommunicationRecord).where(
            CommunicationRecord.provider_message_id == "recovery-1"
        )
    )
    assert recovered is not None
    assert recovered.direction == "inbound"
    assert recover_next_received_email(
        db_session,
        resend_inbound_settings,
        client=provider,
    ) is None


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
