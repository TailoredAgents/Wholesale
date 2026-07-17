from typing import Any

from twilio.base.exceptions import TwilioRestException  # type: ignore[import-untyped]
from twilio.request_validator import RequestValidator  # type: ignore[import-untyped]
from twilio.rest import Client  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings
from app.integrations.communications import (
    OutboundMessageRequest,
    OutboundMessageResult,
)


class TwilioMessagingError(RuntimeError):
    pass


class TwilioMessagingProvider:
    provider_name = "twilio"

    def __init__(self, settings: Settings, client: Client | None = None) -> None:
        self.settings = settings
        self.client = client or self._build_client()

    def _build_client(self) -> Client:
        if not self.settings.twilio_account_sid:
            raise TwilioMessagingError("Twilio account SID is not configured.")
        if self.settings.twilio_api_key_sid and self.settings.twilio_api_key_secret:
            return Client(
                self.settings.twilio_api_key_sid,
                self.settings.twilio_api_key_secret,
                self.settings.twilio_account_sid,
            )
        if self.settings.twilio_auth_token:
            return Client(
                self.settings.twilio_account_sid,
                self.settings.twilio_auth_token,
            )
        raise TwilioMessagingError("Twilio sending credentials are not configured.")

    def send(
        self,
        request: OutboundMessageRequest,
        *,
        dry_run: bool = True,
    ) -> OutboundMessageResult:
        if dry_run:
            return OutboundMessageResult(
                provider=self.provider_name,
                provider_message_id=f"dry-run-{request.idempotency_key or 'message'}",
                status="queued",
                raw_payload={"dry_run": True, "to": request.recipient},
            )
        if not self.settings.twilio_sms_configured:
            raise TwilioMessagingError("Live Twilio SMS is not fully configured.")
        assert self.settings.twilio_messaging_service_sid is not None
        assert self.settings.twilio_webhook_base_url is not None
        status_callback = (
            f"{self.settings.twilio_webhook_base_url.rstrip('/')}"
            "/api/v1/webhooks/twilio/messaging/status"
        )
        try:
            message = self.client.messages.create(
                to=request.recipient,
                messaging_service_sid=self.settings.twilio_messaging_service_sid,
                body=request.body,
                status_callback=status_callback,
            )
        except TwilioRestException as exc:
            raise TwilioMessagingError(
                f"Twilio rejected the message ({exc.code or exc.status})."
            ) from exc
        except Exception as exc:
            raise TwilioMessagingError("Twilio could not accept the message.") from exc

        provider_message_id = str(message.sid)
        status = str(message.status or "queued")
        return OutboundMessageResult(
            provider=self.provider_name,
            provider_message_id=provider_message_id,
            status=status,
            raw_payload=twilio_message_payload(message),
        )


def get_twilio_messaging_provider() -> TwilioMessagingProvider:
    return TwilioMessagingProvider(get_settings())


def validate_twilio_signature(
    *,
    url: str,
    form_values: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    return bool(RequestValidator(auth_token).validate(url, form_values, signature))


def twilio_message_payload(message: Any) -> dict[str, object]:
    return {
        "sid": str(message.sid),
        "status": str(message.status or "queued"),
        "to": str(message.to or ""),
        "messaging_service_sid": str(message.messaging_service_sid or ""),
        "error_code": message.error_code,
        "error_message": message.error_message,
        "num_segments": str(message.num_segments or ""),
    }
