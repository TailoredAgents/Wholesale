from dataclasses import dataclass
from typing import Any

from twilio.base.exceptions import TwilioRestException  # type: ignore[import-untyped]
from twilio.rest import Client  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings


class TwilioVoiceCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class TwilioVoiceCallResult:
    sid: str
    status: str


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
    ) -> TwilioVoiceCallResult:
        try:
            call: Any = self.client.calls.create(
                to=to,
                from_=from_number,
                twiml=twiml,
                status_callback=status_callback,
                status_callback_event=["completed"],
                status_callback_method="POST",
            )
        except TwilioRestException as exc:
            raise TwilioVoiceCallError(
                f"Twilio rejected the forwarded call ({exc.code or exc.status})."
            ) from exc
        except Exception as exc:
            raise TwilioVoiceCallError("Twilio could not start the forwarded call.") from exc
        return TwilioVoiceCallResult(sid=str(call.sid), status=str(call.status or "queued"))


def get_twilio_voice_call_provider() -> TwilioVoiceCallProvider:
    return TwilioVoiceCallProvider(get_settings())
