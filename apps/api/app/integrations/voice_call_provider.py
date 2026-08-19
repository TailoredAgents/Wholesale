from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class VoiceCallProviderError(RuntimeError):
    """Safe provider-boundary error for outbound Voice call operations."""


@dataclass(frozen=True)
class VoiceCallResult:
    """Provider-neutral identity and current state for one Voice call."""

    sid: str
    status: str


@runtime_checkable
class VoiceCallProvider(Protocol):
    """Lifecycle controls required by Stonegate's warm and prospecting call flows."""

    def start(
        self,
        *,
        to: str,
        from_number: str,
        twiml: str,
        status_callback: str,
        status_callback_events: Sequence[str] = ("completed",),
    ) -> VoiceCallResult: ...

    def fetch(self, call_id: str) -> VoiceCallResult: ...

    def cancel(self, call_id: str) -> VoiceCallResult: ...

    def hangup(self, call_id: str) -> VoiceCallResult: ...
