import base64
from email.headerregistry import Address
from typing import Any
from urllib.parse import urlparse

import httpx

from app.integrations.email_delivery import (
    EmailDeliveryProvider,
    EmailDeliveryRequest,
    EmailDeliveryResult,
    EmailProviderError,
)


class ResendEmailError(EmailProviderError):
    pass


class ResendEmailDeliveryProvider(EmailDeliveryProvider):
    provider_name = "resend"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.resend.com",
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def send(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        recipients = request.to or [request.recipient]
        payload: dict[str, Any] = {
            "from": format_sender(request.sender_name, request.sender_email),
            "to": recipients,
            "subject": request.subject,
            "text": request.body,
        }
        if request.html_body:
            payload["html"] = request.html_body
        if request.cc:
            payload["cc"] = request.cc
        if request.bcc:
            payload["bcc"] = request.bcc
        thread_headers = thread_headers_for(request)
        if thread_headers:
            payload["headers"] = thread_headers
        if request.attachments:
            payload["attachments"] = [
                {
                    "filename": filename,
                    "content": base64.b64encode(content).decode("ascii"),
                }
                for filename, _content_type, content in request.attachments
            ]

        response = self._request(
            "POST",
            "/emails",
            json=payload,
            headers={"Idempotency-Key": request.idempotency_key},
        )
        provider_message_id = required_string(response, "id")
        retrieved = self.retrieve_sent_message(provider_message_id)
        rfc_message_id = (
            str(retrieved.get("message_id", "")).strip() if retrieved else ""
        )
        return EmailDeliveryResult(
            provider=self.provider_name,
            provider_message_id=provider_message_id,
            provider_thread_id=request.provider_thread_id or provider_message_id,
            rfc_message_id=rfc_message_id,
            raw_payload={
                "send": response,
                "retrieved": retrieved,
            },
        )

    def retrieve_sent_message(self, provider_message_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/emails/{provider_message_id}")
        except ResendEmailError:
            # Delivery succeeded even if metadata is not immediately available.
            return None

    def retrieve_received_email(self, provider_message_id: str) -> dict[str, Any]:
        return self._request("GET", f"/emails/receiving/{provider_message_id}")

    def list_received_emails(
        self,
        *,
        limit: int = 100,
        after: str | None = None,
    ) -> dict[str, Any]:
        params = {"limit": str(limit)}
        if after:
            params["after"] = after
        return self._request("GET", "/emails/receiving", params=params)

    def retrieve_received_attachment(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            (
                f"/emails/receiving/{provider_message_id}"
                f"/attachments/{provider_attachment_id}"
            ),
        )

    def download_received_attachment(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
        *,
        max_bytes: int,
    ) -> tuple[dict[str, Any], bytes]:
        metadata = self.retrieve_received_attachment(
            provider_message_id,
            provider_attachment_id,
        )
        download_url = str(metadata.get("download_url", "")).strip()
        parsed = urlparse(download_url)
        if parsed.scheme != "https" or parsed.hostname != "inbound-cdn.resend.com":
            raise ResendEmailError("Resend returned an invalid attachment download URL.")
        content = self._download(download_url)
        if len(content) > max_bytes:
            raise ResendEmailError("The received attachment exceeds Stonegate's size limit.")
        return metadata, content

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if json is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        try:
            if self.client is not None:
                response = self.client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    headers=request_headers,
                    params=params,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        json=json,
                        headers=request_headers,
                        params=params,
                    )
        except httpx.RequestError as exc:
            raise ResendEmailError("Resend could not be reached.") from exc
        if response.status_code >= 400:
            raise ResendEmailError(resend_error_message(response))
        try:
            data = response.json()
        except ValueError as exc:
            raise ResendEmailError("Resend returned an invalid response.") from exc
        if not isinstance(data, dict):
            raise ResendEmailError("Resend returned an invalid response.")
        return data

    def _download(self, url: str) -> bytes:
        try:
            if self.client is not None:
                response = self.client.get(url)
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url)
        except httpx.RequestError as exc:
            raise ResendEmailError("Resend attachment content could not be reached.") from exc
        if response.status_code >= 400:
            raise ResendEmailError(
                f"Resend attachment download failed with status {response.status_code}."
            )
        return bytes(response.content)


def format_sender(display_name: str, email_address: str) -> str:
    local_part, separator, domain = email_address.strip().rpartition("@")
    if not separator or not local_part or not domain:
        raise ResendEmailError("The selected sender email address is invalid.")
    if "\r" in display_name or "\n" in display_name:
        raise ResendEmailError("The selected sender display name is invalid.")
    return str(
        Address(
            display_name=display_name.strip(),
            username=local_part,
            domain=domain,
        )
    )


def thread_headers_for(request: EmailDeliveryRequest) -> dict[str, str]:
    headers: dict[str, str] = {}
    if request.in_reply_to:
        headers["In-Reply-To"] = safe_header_value(request.in_reply_to)
    if request.references:
        headers["References"] = safe_header_value(request.references)
    return headers


def safe_header_value(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ResendEmailError("Email thread metadata is invalid.")
    return value.strip()


def required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResendEmailError("Resend did not return an email ID.")
    return value.strip()


def resend_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(message, str) and message.strip():
        return f"Resend rejected the email: {message.strip()[:500]}"
    return f"Resend rejected the email with status {response.status_code}."
