import base64
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import principal_for_user
from app.core.config import get_settings
from app.integrations.google_gmail import (
    GmailSendResult,
    GoogleProfile,
    GoogleTokenResult,
)
from app.main import app
from app.models.foundation import (
    CommunicationRecord,
    Conversation,
    EmailAccount,
    EmailAttachment,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.email import (
    complete_google_authorization,
    create_google_authorization,
    sync_email_account,
)

OWNER_EMAIL = "owner@example.com"


class FakeGoogleGmailClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.inbound_enabled = False

    def authorization_url(self, state: str) -> str:
        return f"https://accounts.google.test/auth?state={state}"

    def exchange_code(self, code: str) -> GoogleTokenResult:
        assert code == "google-code"
        return GoogleTokenResult(
            access_token="google-access-token",
            expires_in=3600,
            refresh_token="google-refresh-token",
        )

    def refresh_access_token(self, refresh_token: str) -> GoogleTokenResult:
        assert refresh_token == "google-refresh-token"
        return GoogleTokenResult(
            access_token="refreshed-google-access-token",
            expires_in=3600,
            refresh_token=None,
        )

    def get_profile(self, access_token: str) -> GoogleProfile:
        assert access_token
        return GoogleProfile(email_address="offers@stonegate.test", history_id="100")

    def send_message(self, access_token: str, **payload: object) -> GmailSendResult:
        assert access_token
        self.sent.append(payload)
        return GmailSendResult(
            message_id="gmail-sent-1",
            thread_id="gmail-thread-1",
            raw_payload={
                "id": "gmail-sent-1",
                "threadId": "gmail-thread-1",
                "rfc_message_id": "<sent-1@stonegate.test>",
            },
        )

    def list_history(
        self,
        access_token: str,
        *,
        start_history_id: str,
        page_token: str | None = None,
    ) -> dict[str, object]:
        assert access_token
        assert start_history_id in {"100", "102"}
        assert page_token is None
        if start_history_id == "102":
            return {"historyId": "102"}
        if not self.inbound_enabled:
            return {"historyId": "100"}
        return {
            "historyId": "102",
            "history": [{"messagesAdded": [{"message": {"id": "gmail-inbound-1"}}]}],
        }

    def get_message(self, access_token: str, message_id: str) -> dict[str, object]:
        assert access_token
        if message_id == "gmail-sent-1":
            return gmail_message(
                message_id=message_id,
                thread_id="gmail-thread-1",
                sender="offers@stonegate.test",
                recipient="seller@example.com",
                subject="Your Stonegate appointment",
                body="Outbound body",
                attachment_id="attachment-sent-1",
            )
        assert message_id == "gmail-inbound-1"
        return gmail_message(
            message_id=message_id,
            thread_id="gmail-thread-1",
            sender="seller@example.com",
            recipient="offers@stonegate.test",
            subject="Re: Your Stonegate appointment",
            body="Tuesday works for me.",
            attachment_id="attachment-inbound-1",
        )

    def list_messages(
        self,
        access_token: str,
        *,
        page_token: str | None = None,
    ) -> dict[str, object]:
        assert access_token
        assert page_token is None
        return {"messages": []}

    def get_attachment(
        self,
        access_token: str,
        *,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        assert access_token
        assert message_id in {"gmail-sent-1", "gmail-inbound-1"}
        assert attachment_id.startswith("attachment-")
        return b"test document"


def gmail_message(
    *,
    message_id: str,
    thread_id: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    attachment_id: str,
) -> dict[str, object]:
    encoded_body = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": message_id,
        "threadId": thread_id,
        "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
        "labelIds": ["INBOX"] if sender == "seller@example.com" else ["SENT"],
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": recipient},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{message_id}@example.test>"},
                {"name": "References", "value": "<sent-1@stonegate.test>"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "body": {"data": encoded_body, "size": len(body)},
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "seller-document.pdf",
                    "headers": [
                        {"name": "Content-Disposition", "value": "attachment"},
                    ],
                    "body": {"attachmentId": attachment_id, "size": 13},
                },
            ],
        },
    }


@pytest.fixture
def email_settings(monkeypatch: MonkeyPatch) -> Iterator[None]:
    values = {
        "EMAIL_ENABLED": "true",
        "EMAIL_SYNC_ENABLED": "true",
        "EMAIL_TOKEN_ENCRYPTION_KEY": "test-encryption-key-with-sufficient-entropy",
        "EMAIL_OAUTH_STATE_SECRET": "test-oauth-state-secret-with-sufficient-entropy",
        "GOOGLE_OAUTH_CLIENT_ID": "google-client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "google-client-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "https://api.stonegate.test/api/v1/email/oauth/google/callback",
        "EMAIL_WEB_APP_BASE_URL": "https://stonegate.test",
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


def test_google_email_send_sync_and_attachments_share_the_inbox_timeline(
    db_session: Session,
    api_db_override: None,
    email_settings: None,
    monkeypatch: MonkeyPatch,
) -> None:
    bootstrap = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert bootstrap.admin_user is not None
    principal = principal_for_user(db_session, bootstrap.admin_user)
    fake = FakeGoogleGmailClient()
    authorization = create_google_authorization(principal, client=fake)
    state = parse_qs(urlparse(authorization.authorization_url).query)["state"][0]
    account = complete_google_authorization(
        db_session,
        code="google-code",
        state=state,
        client=fake,
    )
    assert account.email_address == "offers@stonegate.test"
    assert "google-access-token" not in (account.encrypted_access_token or "")
    assert "google-refresh-token" not in account.encrypted_refresh_token
    account.signature_text = "Owner\nStonegate Home Buyers"
    db_session.commit()

    monkeypatch.setattr("app.services.email.get_google_gmail_client", lambda _settings: fake)
    client = TestClient(app)
    lead_response = client.post("/api/v1/public/seller-leads", json=public_payload())
    assert lead_response.status_code == 201
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None

    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    accounts_response = client.get("/api/v1/email/accounts", headers=headers)
    assert accounts_response.status_code == 200
    assert accounts_response.json()["items"][0]["email_address"] == "offers@stonegate.test"

    send_response = client.post(
        f"/api/v1/email/conversations/{conversation.id}/messages",
        headers=headers,
        json={
            "email_account_id": str(account.id),
            "subject": "Your Stonegate appointment",
            "body": "Can we meet Tuesday?",
            "idempotency_key": "email-send-request-1",
            "attachments": [
                {
                    "filename": "offer-summary.pdf",
                    "content_type": "application/pdf",
                    "content_base64": base64.b64encode(b"offer summary").decode(),
                }
            ],
        },
    )
    assert send_response.status_code == 201
    assert send_response.json()["provider_thread_id"] == "gmail-thread-1"
    assert fake.sent[0]["recipient"] == "seller@example.com"
    assert fake.sent[0]["body"] == ("Can we meet Tuesday?\n\n--\nOwner\nStonegate Home Buyers")

    fake.inbound_enabled = True
    sync_result = sync_email_account(db_session, account, client=fake)
    assert sync_result.imported_messages == 1
    assert sync_result.history_cursor == "102"
    second_sync = sync_email_account(db_session, account, client=fake)
    assert second_sync.imported_messages == 0
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CommunicationRecord)
            .where(CommunicationRecord.channel == "email")
        )
        == 2
    )
    assert db_session.scalar(select(func.count()).select_from(EmailAttachment)) == 2

    inbox_response = client.get(
        f"/api/v1/inbox/conversations/{conversation.id}",
        headers=headers,
    )
    assert inbox_response.status_code == 200
    email_items = [item for item in inbox_response.json()["timeline"] if item["channel"] == "email"]
    assert [item["direction"] for item in email_items] == ["outbound", "inbound"]
    assert email_items[1]["body"] == "Tuesday works for me."
    attachment_id = email_items[1]["attachments"][0]["id"]
    attachment_response = client.get(
        f"/api/v1/email/attachments/{attachment_id}",
        headers=headers,
    )
    assert attachment_response.status_code == 200
    assert attachment_response.content == b"test document"


def test_email_is_disabled_until_all_configuration_is_present(
    db_session: Session,
) -> None:
    bootstrap = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    assert bootstrap.admin_user is not None
    principal = principal_for_user(db_session, bootstrap.admin_user)
    settings = get_settings()
    assert settings.email_enabled is False
    with pytest.raises(RuntimeError, match="Email is not configured"):
        create_google_authorization(principal, settings=settings)
    assert db_session.scalar(select(func.count()).select_from(EmailAccount)) == 0
