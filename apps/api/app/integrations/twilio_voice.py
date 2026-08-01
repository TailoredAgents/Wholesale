from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from twilio.jwt.access_token import AccessToken  # type: ignore[import-untyped]
from twilio.jwt.access_token.grants import VoiceGrant  # type: ignore[import-untyped]
from twilio.twiml.voice_response import VoiceResponse  # type: ignore[import-untyped]

from app.core.config import Settings


class TwilioVoiceConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class InboundVoiceTarget:
    identity: str
    user_id: str
    forwarding_number: str | None = None


def voice_identity(user_id: str) -> str:
    return f"stonegate_{user_id.replace('-', '')}"


def create_voice_access_token(
    settings: Settings,
    *,
    identity: str,
) -> tuple[str, datetime]:
    if not settings.twilio_browser_voice_configured:
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
        if settings.twilio_voice_recording_disclosure:
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


def forwarded_outbound_screen_twiml(settings: Settings, *, intent_id: str) -> str:
    response = VoiceResponse()
    gather = response.gather(
        action=callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/forwarded-connect",
            intent_id=intent_id,
        ),
        method="POST",
        input="dtmf",
        num_digits=1,
        timeout=8,
        action_on_empty_result=True,
    )
    gather.say("Stonegate outbound call. Press 1 to connect to the contact.")
    response.hangup()
    return str(response)


def inbound_call_twiml(
    settings: Settings,
    *,
    targets: list[InboundVoiceTarget],
    call_id: str,
    recording_enabled: bool,
    ring_strategy: str,
) -> str:
    if not targets:
        raise TwilioVoiceConfigurationError("Inbound call has no active routing targets.")
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
        "sequential": ring_strategy == "sequential",
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
    endpoint_count = 0
    for target in targets:
        if endpoint_count >= 10:
            break
        if target.forwarding_number is None:
            continue
        dial.number(
            target.forwarding_number,
            url=callback_url(
                settings,
                "/api/v1/webhooks/twilio/voice/screen",
                call_id=call_id,
                answered_user_id=target.user_id,
                mobile="true",
            ),
            method="POST",
            status_callback=callback_url(
                settings,
                "/api/v1/webhooks/twilio/voice/status",
                call_id=call_id,
            ),
            status_callback_event="initiated ringing answered completed",
            status_callback_method="POST",
        )
        endpoint_count += 1
    return str(response)


def call_screen_twiml(
    settings: Settings,
    *,
    call_id: str,
    answered_user_id: str,
    announcement: str,
    require_acceptance: bool,
) -> str:
    response = VoiceResponse()
    if not require_acceptance:
        response.say(announcement)
        return str(response)
    gather = response.gather(
        action=callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/screen-result",
            call_id=call_id,
            answered_user_id=answered_user_id,
        ),
        method="POST",
        input="dtmf",
        num_digits=1,
        timeout=6,
        action_on_empty_result=True,
    )
    gather.say(f"{announcement} Press 1 to accept.")
    response.hangup()
    return str(response)


def call_screen_result_twiml(*, accepted: bool) -> str:
    response = VoiceResponse()
    if not accepted:
        response.say("Call declined.")
        response.hangup()
    return str(response)


def voicemail_twiml(settings: Settings, *, call_id: str) -> str:
    response = VoiceResponse()
    response.say(
        "Thank you for calling Stonegate Home Buyers. Please leave your name, phone number, "
        "property address, and a short message after the tone."
    )
    response.record(
        action=callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/voicemail-complete",
            call_id=call_id,
        ),
        method="POST",
        max_length=180,
        play_beep=True,
        recording_status_callback=callback_url(
            settings,
            "/api/v1/webhooks/twilio/voice/recording",
            call_id=call_id,
        ),
        recording_status_callback_event="completed absent",
        recording_status_callback_method="POST",
        trim="trim-silence",
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
