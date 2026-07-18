from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from twilio.jwt.access_token import AccessToken  # type: ignore[import-untyped]
from twilio.jwt.access_token.grants import VoiceGrant  # type: ignore[import-untyped]
from twilio.twiml.voice_response import VoiceResponse  # type: ignore[import-untyped]

from app.core.config import Settings


class TwilioVoiceConfigurationError(RuntimeError):
    pass


def voice_identity(user_id: str) -> str:
    return f"stonegate_{user_id.replace('-', '')}"


def create_voice_access_token(
    settings: Settings,
    *,
    identity: str,
) -> tuple[str, datetime]:
    if not settings.twilio_voice_configured:
        raise TwilioVoiceConfigurationError("Twilio Voice is not fully configured.")
    assert settings.twilio_account_sid is not None
    assert settings.twilio_api_key_sid is not None
    assert settings.twilio_api_key_secret is not None
    assert settings.twilio_twiml_app_sid is not None
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.twilio_voice_token_ttl_seconds)
    token = AccessToken(
        settings.twilio_account_sid,
        settings.twilio_api_key_sid,
        settings.twilio_api_key_secret,
        identity=identity,
        ttl=settings.twilio_voice_token_ttl_seconds,
    )
    token.add_grant(
        VoiceGrant(
            outgoing_application_sid=settings.twilio_twiml_app_sid,
            incoming_allow=True,
        )
    )
    jwt_value = token.to_jwt()
    return (
        jwt_value.decode("utf-8") if isinstance(jwt_value, bytes) else str(jwt_value),
        expires_at,
    )


def callback_url(settings: Settings, path: str, **query: str) -> str:
    if not settings.twilio_webhook_base_url:
        raise TwilioVoiceConfigurationError("Twilio webhook base URL is not configured.")
    url = f"{settings.twilio_webhook_base_url.rstrip('/')}{path}"
    return f"{url}?{urlencode(query)}" if query else url


def outbound_call_twiml(
    settings: Settings,
    *,
    recipient: str,
    from_number: str,
    intent_id: str,
    recording_enabled: bool,
) -> str:
    response = VoiceResponse()
    recording_callback = callback_url(
        settings,
        "/api/v1/webhooks/twilio/voice/recording",
        intent_id=intent_id,
    )
    dial_options: dict[str, object] = {
        "caller_id": from_number,
        "answer_on_bridge": True,
        "timeout": settings.twilio_voice_ring_timeout_seconds,
        "action": callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/dial-result",
            intent_id=intent_id,
        ),
        "method": "POST",
    }
    number_options: dict[str, object] = {
        "status_callback": callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/status",
            intent_id=intent_id,
        ),
        "status_callback_event": "initiated ringing answered completed",
        "status_callback_method": "POST",
    }
    if recording_enabled:
        dial_options.update(
            {
                "record": "record-from-answer-dual",
                "recording_status_callback": recording_callback,
                "recording_status_callback_event": "completed absent",
                "recording_status_callback_method": "POST",
            }
        )
        number_options.update(
            {
                "url": callback_url(
                    settings,
                    "/api/v1/webhooks/twilio/voice/disclosure",
                    intent_id=intent_id,
                ),
                "method": "POST",
            }
        )
    dial = response.dial(**dial_options)
    dial.number(recipient, **number_options)
    return str(response)


def inbound_call_twiml(
    settings: Settings,
    *,
    identity: str,
    call_id: str,
    recording_enabled: bool,
) -> str:
    response = VoiceResponse()
    if recording_enabled and settings.twilio_voice_recording_disclosure:
        response.say(settings.twilio_voice_recording_disclosure)
    dial_options: dict[str, object] = {
        "answer_on_bridge": True,
        "timeout": settings.twilio_voice_ring_timeout_seconds,
        "action": callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/dial-result",
            call_id=call_id,
        ),
        "method": "POST",
    }
    if recording_enabled:
        dial_options.update(
            {
                "record": "record-from-answer-dual",
                "recording_status_callback": callback_url(
                    settings,
                    "/api/v1/webhooks/twilio/voice/recording",
                    call_id=call_id,
                ),
                "recording_status_callback_event": "completed absent",
                "recording_status_callback_method": "POST",
            }
        )
    dial = response.dial(**dial_options)
    dial.client(
        identity,
        status_callback=callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/status",
            call_id=call_id,
        ),
        status_callback_event="initiated ringing answered completed",
        status_callback_method="POST",
    )
    return str(response)


def disclosure_twiml(settings: Settings) -> str:
    response = VoiceResponse()
    if settings.twilio_voice_recording_disclosure:
        response.say(settings.twilio_voice_recording_disclosure)
    return str(response)


def hangup_twiml(message: str | None = None) -> str:
    response = VoiceResponse()
    if message:
        response.say(message)
    response.hangup()
    return str(response)
