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
