from collections.abc import Sequence
from typing import Any

from twilio.base.exceptions import TwilioRestException  # type: ignore[import-untyped]
from twilio.rest import Client  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings
from app.integrations.voice_call_provider import (
    VoiceCallProviderError,
    VoiceCallResult,
)


class TwilioVoiceCallError(VoiceCallProviderError):
    pass


TwilioVoiceCallResult = VoiceCallResult


TWILIO_STATUS_CALLBACK_EVENTS = frozenset({"initiated", "ringing", "answered", "completed"})


class TwilioVoiceCallProvider:
    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        self.settings = settings
        self.client = client or self._build_client()

    def _build_client(self) -> Client:
        if not self.settings.twilio_account_sid or not self.settings.twilio_auth_token:
            raise TwilioVoiceCallError("Twilio Voice credentials are not configured.")
        return Client(self.settings.twilio_account_sid, self.settings.twilio_auth_token)

    def start(
        self,
        *,
        to: str,
        from_number: str,
        twiml: str,
        status_callback: str,
        status_callback_events: Sequence[str] = ("completed",),
    ) -> TwilioVoiceCallResult:
        callback_events = normalize_status_callback_events(status_callback_events)
        try:
            call: Any = self.client.calls.create(
                to=to,
                from_=from_number,
                twiml=twiml,
                status_callback=status_callback,
                status_callback_event=callback_events,
                status_callback_method="POST",
            )
        except TwilioRestException as exc:
            raise TwilioVoiceCallError(
                f"Twilio rejected the forwarded call ({exc.code or exc.status})."
            ) from exc
        except Exception as exc:
            raise TwilioVoiceCallError("Twilio could not start the forwarded call.") from exc
        return TwilioVoiceCallResult(sid=str(call.sid), status=str(call.status or "queued"))

    def fetch(self, call_id: str) -> TwilioVoiceCallResult:
        return self._control(call_id, operation="fetch")

    def cancel(self, call_id: str) -> TwilioVoiceCallResult:
        return self._control(call_id, operation="cancel", status="canceled")

    def hangup(self, call_id: str) -> TwilioVoiceCallResult:
        return self._control(call_id, operation="hangup", status="completed")

    def _control(
        self,
        call_id: str,
        *,
        operation: str,
        status: str | None = None,
    ) -> TwilioVoiceCallResult:
        normalized_call_id = call_id.strip()
        if not normalized_call_id:
            raise TwilioVoiceCallError("A provider call ID is required.")
        try:
            call_resource: Any = self.client.calls(normalized_call_id)
            call: Any = (
                call_resource.fetch() if status is None else call_resource.update(status=status)
            )
        except TwilioRestException as exc:
            raise TwilioVoiceCallError(
                f"Twilio rejected the {operation} request ({exc.code or exc.status})."
            ) from exc
        except Exception as exc:
            raise TwilioVoiceCallError(f"Twilio could not {operation} the call.") from exc
        return TwilioVoiceCallResult(
            sid=str(getattr(call, "sid", None) or normalized_call_id),
            status=str(getattr(call, "status", None) or status or "unknown"),
        )


def normalize_status_callback_events(events: Sequence[str]) -> list[str]:
    normalized = list(dict.fromkeys(event.strip().lower() for event in events if event.strip()))
    if not normalized:
        normalized = ["completed"]
    unsupported = [event for event in normalized if event not in TWILIO_STATUS_CALLBACK_EVENTS]
    if unsupported:
        raise TwilioVoiceCallError(
            f"Unsupported Twilio Voice status callback event: {unsupported[0]}."
        )
    return normalized


def get_twilio_voice_call_provider() -> TwilioVoiceCallProvider:
    return TwilioVoiceCallProvider(get_settings())
