from dataclasses import dataclass, field
from typing import Any, Protocol

from app.integrations.communications import (
    OutboundMessageRequest,
    SimulatedCommunicationProvider,
)
from app.integrations.google_gmail import GoogleGmailClient

EmailAttachmentPayload = tuple[str, str, bytes]


class EmailProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmailDeliveryRequest:
    lead_id: str | None
    contact_id: str
    sender_name: str
    sender_email: str
    recipient: str
    subject: str
    body: str
    idempotency_key: str
    to: list[str] = field(default_factory=list)
    html_body: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    attachments: list[EmailAttachmentPayload] = field(default_factory=list)
    provider_thread_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None


@dataclass(frozen=True)
class EmailDeliveryResult:
    provider: str
    provider_message_id: str
    provider_thread_id: str
    rfc_message_id: str
    raw_payload: dict[str, Any]


class EmailDeliveryProvider(Protocol):
    provider_name: str

    def send(self, request: EmailDeliveryRequest) -> EmailDeliveryResult: ...

    def retrieve_sent_message(self, provider_message_id: str) -> dict[str, Any] | None: ...


class SimulatedEmailDeliveryProvider:
    provider_name = "simulated"

    def __init__(self, *, thread_id: str) -> None:
        self.thread_id = thread_id

    def send(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        recipients = request.to or [request.recipient]
        metadata = {
            "attachment_count": str(len(request.attachments)),
            "recipient_count": str(len(recipients)),
        }
        if request.cc:
            metadata["cc_count"] = str(len(request.cc))
        if request.bcc:
            metadata["bcc_count"] = str(len(request.bcc))
        result = SimulatedCommunicationProvider().send(
            OutboundMessageRequest(
                lead_id=request.lead_id,
                contact_id=request.contact_id,
                channel="email",
                recipient=recipients[0],
                subject=request.subject,
                body=request.body,
                idempotency_key=request.idempotency_key,
                metadata=metadata,
            )
        )
        provider_message_id = result.provider_message_id or (f"sim-email-{request.idempotency_key}")
        return EmailDeliveryResult(
            provider=result.provider,
            provider_message_id=provider_message_id,
            provider_thread_id=request.provider_thread_id or self.thread_id,
            rfc_message_id=f"<{provider_message_id}@example.test>",
            raw_payload=result.raw_payload,
        )

    def retrieve_sent_message(self, provider_message_id: str) -> dict[str, Any] | None:
        return None


class GoogleEmailDeliveryProvider:
    provider_name = "google"

    def __init__(self, client: GoogleGmailClient, access_token: str) -> None:
        self.client = client
        self.access_token = access_token

    def send(self, request: EmailDeliveryRequest) -> EmailDeliveryResult:
        recipients = request.to or [request.recipient]
        result = self.client.send_message(
            self.access_token,
            sender_name=request.sender_name,
            sender_email=request.sender_email,
            recipient=recipients[0],
            subject=request.subject,
            body=request.body,
            attachments=request.attachments,
            thread_id=request.provider_thread_id,
            in_reply_to=request.in_reply_to,
            references=request.references,
        )
        return EmailDeliveryResult(
            provider=self.provider_name,
            provider_message_id=result.message_id,
            provider_thread_id=result.thread_id,
            rfc_message_id=str(result.raw_payload.get("rfc_message_id", "")),
            raw_payload=result.raw_payload,
        )

    def retrieve_sent_message(self, provider_message_id: str) -> dict[str, Any] | None:
        return self.client.get_message(self.access_token, provider_message_id)
