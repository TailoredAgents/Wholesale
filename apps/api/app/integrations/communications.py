import hashlib
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OutboundMessageRequest:
    lead_id: str
    contact_id: str
    channel: str
    recipient: str
    body: str
    subject: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OutboundMessageResult:
    provider: str
    provider_message_id: str | None
    status: str
    raw_payload: dict[str, object]


class CommunicationProvider(Protocol):
    provider_name: str

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        """Send or simulate one outbound message after deterministic compliance checks."""


class SimulatedCommunicationProvider:
    """Deterministic local provider used to test communication workflows without delivery."""

    provider_name = "simulated"

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        fingerprint = hashlib.sha256(
            "|".join(
                [
                    request.channel,
                    request.idempotency_key or "",
                    request.recipient,
                    request.subject or "",
                    request.body,
                ]
            ).encode("utf-8")
        ).hexdigest()[:24]
        return OutboundMessageResult(
            provider=self.provider_name,
            provider_message_id=f"sim-{request.channel}-{fingerprint}",
            status="sent",
            raw_payload={
                "simulated": True,
                "dry_run": dry_run,
                "channel": request.channel,
                "recipient": request.recipient,
                "metadata": request.metadata,
            },
        )
