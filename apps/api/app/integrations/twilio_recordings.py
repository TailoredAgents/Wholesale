from dataclasses import dataclass

import httpx

from app.core.config import Settings

TWILIO_MP3_MEDIA_TYPE = "audio/mpeg"


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
            headers={"Accept": TWILIO_MP3_MEDIA_TYPE},
            timeout=60,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            message = "Twilio recording media is no longer available."
        elif exc.response.status_code in {401, 403}:
            message = "Twilio recording access was rejected."
        else:
            message = "Twilio recording media could not be retrieved."
        raise TwilioRecordingError(message) from exc
    except httpx.RequestError as exc:
        raise TwilioRecordingError("Twilio recording media could not be retrieved.") from exc
    if not response.content:
        raise TwilioRecordingError("Twilio returned an empty recording.")
    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not media_type.startswith("audio/") and not (
        media_type == "application/octet-stream" and looks_like_mp3(response.content)
    ):
        raise TwilioRecordingError("Twilio returned an invalid recording response.")
    return TwilioRecordingMedia(
        content=response.content,
        media_type=TWILIO_MP3_MEDIA_TYPE,
    )


def looks_like_mp3(content: bytes) -> bool:
    return content.startswith(b"ID3") or (
        len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
    )


def delete_twilio_recording(
    settings: Settings,
    provider_recording_id: str,
) -> None:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise TwilioRecordingError("Twilio recording deletion is not configured.")
    recording_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Recordings/{provider_recording_id}.json"
    )
    try:
        response = httpx.delete(
            recording_url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=30,
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TwilioRecordingError("Twilio recording could not be deleted.") from exc
