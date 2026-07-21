import base64
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

GMAIL_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.modify",
)


class GoogleGmailError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GoogleTokenResult:
    access_token: str
    expires_in: int
    refresh_token: str | None


@dataclass(frozen=True)
class GoogleProfile:
    email_address: str
    history_id: str


@dataclass(frozen=True)
class GmailSendResult:
    message_id: str
    thread_id: str
    raw_payload: dict[str, Any]


class GoogleGmailClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=30.0)

    def authorization_url(self, state: str) -> str:
        if not self.settings.google_oauth_client_id:
            raise GoogleGmailError("Google OAuth client ID is not configured.")
        query = urlencode(
            {
                "client_id": self.settings.google_oauth_client_id,
                "redirect_uri": self.settings.google_oauth_redirect_uri,
                "response_type": "code",
                "scope": " ".join(GMAIL_SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    def exchange_code(self, code: str) -> GoogleTokenResult:
        return self._token_request(
            {
                "code": code,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "redirect_uri": self.settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    def refresh_access_token(self, refresh_token: str) -> GoogleTokenResult:
        return self._token_request(
            {
                "refresh_token": refresh_token,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "grant_type": "refresh_token",
            }
        )

    def _token_request(self, payload: dict[str, object]) -> GoogleTokenResult:
        try:
            response = self.client.post("https://oauth2.googleapis.com/token", data=payload)
            response.raise_for_status()
            data = response.json()
            return GoogleTokenResult(
                access_token=str(data["access_token"]),
                expires_in=int(data.get("expires_in", 3600)),
                refresh_token=(str(data["refresh_token"]) if data.get("refresh_token") else None),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise GoogleGmailError("Google could not complete mailbox authentication.") from exc

    def get_profile(self, access_token: str) -> GoogleProfile:
        data = self._get_json(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            access_token,
        )
        try:
            return GoogleProfile(
                email_address=str(data["emailAddress"]).strip().lower(),
                history_id=str(data["historyId"]),
            )
        except KeyError as exc:
            raise GoogleGmailError("Google returned an incomplete mailbox profile.") from exc

    def send_message(
        self,
        access_token: str,
        *,
        sender_name: str,
        sender_email: str,
        recipient: str,
        subject: str,
        body: str,
        attachments: list[tuple[str, str, bytes]],
        thread_id: str | None,
        in_reply_to: str | None,
        references: str | None,
    ) -> GmailSendResult:
        message = EmailMessage()
        message["From"] = formataddr((sender_name, sender_email))
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1])
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references
        message.set_content(body)
        for filename, content_type, content in attachments:
            maintype, _, subtype = content_type.partition("/")
            message.add_attachment(
                content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=filename,
            )

        payload: dict[str, str] = {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        }
        if thread_id:
            payload["threadId"] = thread_id
        try:
            response = self.client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return GmailSendResult(
                message_id=str(data["id"]),
                thread_id=str(data["threadId"]),
                raw_payload={
                    "id": str(data["id"]),
                    "threadId": str(data["threadId"]),
                    "labelIds": list(data.get("labelIds", [])),
                    "rfc_message_id": str(message["Message-ID"]),
                },
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise GoogleGmailError("Google could not send the email.") from exc

    def list_history(
        self,
        access_token: str,
        *,
        start_history_id: str,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int | float | bool | None] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": 100,
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get_json(
            "https://gmail.googleapis.com/gmail/v1/users/me/history",
            access_token,
            params=params,
        )

    def get_message(self, access_token: str, message_id: str) -> dict[str, Any]:
        return self._get_json(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            access_token,
            params={"format": "full"},
        )

    def list_messages(
        self,
        access_token: str,
        *,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str | int | float | bool | None] = {
            "maxResults": 100,
            "q": "newer_than:30d",
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get_json(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            access_token,
            params=params,
        )

    def get_attachment(
        self,
        access_token: str,
        *,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        data = self._get_json(
            (
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
                f"{message_id}/attachments/{attachment_id}"
            ),
            access_token,
        )
        encoded = str(data.get("data", ""))
        try:
            return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except ValueError as exc:
            raise GoogleGmailError("Google returned an invalid attachment.") from exc

    def _get_json(
        self,
        url: str,
        access_token: str,
        *,
        params: dict[str, str | int | float | bool | None] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise TypeError
            return result
        except httpx.HTTPStatusError as exc:
            raise GoogleGmailError(
                "Google Gmail API request failed.",
                status_code=exc.response.status_code,
            ) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise GoogleGmailError("Google Gmail API request failed.") from exc


def get_google_gmail_client(settings: Settings) -> GoogleGmailClient:
    return GoogleGmailClient(settings)
