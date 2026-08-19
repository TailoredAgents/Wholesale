from typing import Any

import pytest

from app.core.config import Settings
from app.integrations.twilio_voice_calls import (
    TwilioVoiceCallError,
    TwilioVoiceCallProvider,
)
from app.integrations.voice_call_provider import VoiceCallProvider


class FakeCall:
    def __init__(self, sid: str, status: str) -> None:
        self.sid = sid
        self.status = status
        self.fetch_count = 0
        self.updated_statuses: list[str] = []

    def fetch(self) -> "FakeCall":
        self.fetch_count += 1
        return self

    def update(self, *, status: str) -> "FakeCall":
        self.updated_statuses.append(status)
        self.status = status
        return self


class FakeCalls:
    def __init__(self) -> None:
        self.created_kwargs: dict[str, Any] | None = None
        self.call = FakeCall("CA-provider-control", "ringing")
        self.raise_on_control = False

    def create(self, **kwargs: Any) -> FakeCall:
        self.created_kwargs = kwargs
        return FakeCall("CA-provider-start", "queued")

    def __call__(self, call_id: str) -> FakeCall:
        if self.raise_on_control:
            raise RuntimeError("provider unavailable")
        assert call_id == self.call.sid
        return self.call


class FakeClient:
    def __init__(self) -> None:
        self.calls = FakeCalls()


def provider(client: FakeClient) -> TwilioVoiceCallProvider:
    return TwilioVoiceCallProvider(
        Settings(
            APP_ENV="test",
            TWILIO_ACCOUNT_SID="AC-test",
            TWILIO_AUTH_TOKEN="auth-test",
        ),
        client=client,  # type: ignore[arg-type]
    )


def start_call(
    call_provider: TwilioVoiceCallProvider,
    **overrides: Any,
) -> None:
    arguments: dict[str, Any] = {
        "to": "+16785550101",
        "from_number": "+16785550102",
        "twiml": "<Response><Hangup/></Response>",
        "status_callback": "https://api.example.test/voice/status",
    }
    arguments.update(overrides)
    call_provider.start(**arguments)


def test_twilio_provider_implements_neutral_voice_call_contract() -> None:
    call_provider = provider(FakeClient())

    assert isinstance(call_provider, VoiceCallProvider)


def test_warm_call_start_keeps_completed_only_callback_default() -> None:
    client = FakeClient()

    start_call(provider(client))

    assert client.calls.created_kwargs is not None
    assert client.calls.created_kwargs["status_callback_event"] == ["completed"]
    assert client.calls.created_kwargs["status_callback_method"] == "POST"


def test_start_can_request_full_prospecting_lifecycle_callbacks() -> None:
    client = FakeClient()

    start_call(
        provider(client),
        status_callback_events=("initiated", "ringing", "answered", "completed"),
    )

    assert client.calls.created_kwargs is not None
    assert client.calls.created_kwargs["status_callback_event"] == [
        "initiated",
        "ringing",
        "answered",
        "completed",
    ]


def test_callback_events_are_normalized_deduplicated_and_validated() -> None:
    client = FakeClient()
    call_provider = provider(client)

    start_call(
        call_provider,
        status_callback_events=("RINGING", "ringing", "completed"),
    )
    assert client.calls.created_kwargs is not None
    assert client.calls.created_kwargs["status_callback_event"] == ["ringing", "completed"]

    with pytest.raises(TwilioVoiceCallError, match="Unsupported Twilio Voice"):
        start_call(call_provider, status_callback_events=("queued",))


def test_fetch_cancel_and_hangup_return_normalized_provider_results() -> None:
    client = FakeClient()
    call_provider = provider(client)

    fetched = call_provider.fetch(client.calls.call.sid)
    cancelled = call_provider.cancel(client.calls.call.sid)
    hung_up = call_provider.hangup(client.calls.call.sid)

    assert fetched.sid == client.calls.call.sid
    assert fetched.status == "ringing"
    assert client.calls.call.fetch_count == 1
    assert cancelled.status == "canceled"
    assert hung_up.status == "completed"
    assert client.calls.call.updated_statuses == ["canceled", "completed"]


def test_control_errors_are_safe_and_blank_call_ids_are_rejected() -> None:
    client = FakeClient()
    call_provider = provider(client)

    with pytest.raises(TwilioVoiceCallError, match="provider call ID"):
        call_provider.fetch("  ")

    client.calls.raise_on_control = True
    with pytest.raises(TwilioVoiceCallError, match="Twilio could not cancel the call"):
        call_provider.cancel(client.calls.call.sid)
