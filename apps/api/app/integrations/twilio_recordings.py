from dataclasses import dataclass

import httpx

from app.core.config import Settings


class TwilioRecordingError(RuntimeError):
    pass


@dataclass(frozen=True)
class TwilioRecordingMedia:
    content: bytes
    media_type: str


def download_twilio_recording(
    settings: Settings,
    provider_recording_id: str,
) -> TwilioRecordingMedia:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise TwilioRecordingError("Twilio recording access is not configured.")
    media_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Recordings/{provider_recording_id}.mp3"
    )
    try:
        response = httpx.get(
            media_url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TwilioRecordingError("Twilio recording media could not be retrieved.") from exc
    return TwilioRecordingMedia(
        content=response.content,
        media_type=response.headers.get("content-type", "audio/mpeg"),
    )
