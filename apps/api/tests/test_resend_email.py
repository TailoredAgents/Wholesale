import base64
import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.resend_email import ResendEmailDeliveryProvider
from app.main import app
from app.models.foundation import CommunicationDispatch, CommunicationRecord, Conversation
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
OWNER_HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


@pytest.fixture
def resend_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "APP_ENV": "local",
        "COMMUNICATION_PROVIDER_MODE": "live",
        "EMAIL_ENABLED": "true",
        "EMAIL_PROVIDER": "resend",
        "EMAIL_SYNC_ENABLED": "false",
        "RESEND_API_KEY": "re_test",
        "RESEND_WEBHOOK_SECRET": "whsec_test",
        "RESEND_SENDING_DOMAIN": "stonegatehb.com",
        "RESEND_RECEIVING_DOMAIN": "stonegatehb.com",
        "RESEND_DEFAULT_FROM_EMAIL": "offers@stonegatehb.com",
        "RESEND_WEBHOOK_BASE_URL": "https://api.stonegate.test",
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


def create_alias_and_conversation(
    db_session: Session,
    client: TestClient,
) -> tuple[str, Conversation]:
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
            "signature_text": "Austin\nStonegate Home Buyers",
        },
    )
    assert alias_response.status_code == 201, alias_response.text
    lead_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert lead_response.status_code == 201, lead_response.text
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    return str(alias_response.json()["id"]), conversation


def test_resend_sends_alias_email_with_attachment_threading_and_idempotency(
    db_session: Session,
    api_db_override: None,
    resend_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer re_test"
        if request.method == "POST":
            payload = json.loads(request.content)
            requests.append(
                {
                    "idempotency_key": request.headers["idempotency-key"],
                    "payload": payload,
                }
            )
            return httpx.Response(
                200,
                json={"id": f"resend-email-{len(requests)}"},
                request=request,
            )
        provider_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "id": provider_id,
                "message_id": f"<{provider_id}@resend.test>",
                "last_event": "sent",
            },
            request=request,
        )

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(
        "app.services.email.ResendEmailDeliveryProvider",
        lambda **_kwargs: provider,
    )

    client = TestClient(app)
    alias_id, conversation = create_alias_and_conversation(db_session, client)
    first_payload = {
        "email_sender_alias_id": alias_id,
        "subject": "Your Stonegate appointment",
        "body": "Can we meet Tuesday?",
        "html_body": "<p>Can we meet Tuesday?</p>",
        "cc": ["Conner@stonegatehb.com"],
        "bcc": ["audit@stonegatehb.com"],
        "idempotency_key": "resend-request-1",
        "attachments": [
            {
                "filename": "offer-summary.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(b"offer summary").decode(),
            }
        ],
    }
    first = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers=OWNER_HEADERS,
        json=first_payload,
    )
    assert first.status_code == 201, first.text
    assert first.json()["provider_message_id"] == "resend-email-1"

    duplicate = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers=OWNER_HEADERS,
        json=first_payload,
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["communication_id"] == first.json()["communication_id"]
    assert len(requests) == 1

    second = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers=OWNER_HEADERS,
        json={
            "email_sender_alias_id": alias_id,
            "subject": "Re: Your Stonegate appointment",
            "body": "Following up for Tuesday.",
            "idempotency_key": "resend-request-2",
        },
    )
    assert second.status_code == 201, second.text
    assert len(requests) == 2

    first_request = requests[0]
    assert first_request["idempotency_key"] == "resend-request-1"
    assert first_request["payload"]["from"] == (
        "Stonegate Home Buyers <offers@stonegatehb.com>"
    )
    assert first_request["payload"]["to"] == ["seller@example.com"]
    assert first_request["payload"]["cc"] == ["conner@stonegatehb.com"]
    assert first_request["payload"]["bcc"] == ["audit@stonegatehb.com"]
    assert first_request["payload"]["html"] == (
        "<p>Can we meet Tuesday?</p><br><br>--<br>"
        "Austin<br>Stonegate Home Buyers"
    )
    assert first_request["payload"]["text"].endswith(
        "Austin\nStonegate Home Buyers"
    )
    assert first_request["payload"]["attachments"] == [
        {
            "filename": "offer-summary.pdf",
            "content": base64.b64encode(b"offer summary").decode(),
        }
    ]
    assert requests[1]["payload"]["headers"] == {
        "In-Reply-To": "<resend-email-1@resend.test>",
        "References": "<resend-email-1@resend.test>",
    }

    communications = db_session.scalars(
        select(CommunicationRecord).order_by(CommunicationRecord.occurred_at.asc())
    ).all()
    assert len(communications) == 2
    assert communications[0].provider == "resend"
    assert communications[0].communication_metadata is not None
    assert (
        communications[0].communication_metadata["email_sender_alias_id"]
        == alias_id
    )


def test_resend_failure_returns_gateway_error_and_marks_dispatch_failed(
    db_session: Session,
    api_db_override: None,
    resend_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"message": "The sending domain is not verified."},
            request=request,
        )

    provider = ResendEmailDeliveryProvider(
        api_key="re_test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(
        "app.services.email.ResendEmailDeliveryProvider",
        lambda **_kwargs: provider,
    )

    client = TestClient(app)
    alias_id, conversation = create_alias_and_conversation(db_session, client)
    response = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers=OWNER_HEADERS,
        json={
            "email_sender_alias_id": alias_id,
            "subject": "Stonegate follow-up",
            "body": "Checking in.",
            "idempotency_key": "resend-failure-1",
        },
    )
    assert response.status_code == 502, response.text
    assert "sending domain is not verified" in response.text
    dispatch = db_session.scalar(select(CommunicationDispatch))
    assert dispatch is not None
    assert dispatch.status == "failed"
    assert dispatch.provider == "resend"


def test_assigned_user_cannot_send_from_an_ungranted_alias(
    db_session: Session,
    api_db_override: None,
    resend_settings: None,
) -> None:
    client = TestClient(app)
    alias_id, conversation = create_alias_and_conversation(db_session, client)
    user_response = client.post(
        "/api/v1/operations/users",
        headers=OWNER_HEADERS,
        json={
            "email": "devon.login@example.com",
            "display_name": "Devon",
            "role_key": "acquisition_rep",
        },
    )
    assert user_response.status_code == 201, user_response.text
    conversation.assigned_user_id = UUID(user_response.json()["id"])
    db_session.commit()

    response = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers={"X-Dev-User-Email": "devon.login@example.com"},
        json={
            "email_sender_alias_id": alias_id,
            "subject": "Stonegate follow-up",
            "body": "Checking in.",
            "idempotency_key": "resend-permission-1",
        },
    )
    assert response.status_code == 403, response.text
    assert "not authorized to send" in response.text
