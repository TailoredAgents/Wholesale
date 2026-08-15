import httpx
import pytest

from app.core.config import Settings
from app.integrations.twilio_recordings import (
    TwilioRecordingError,
    download_twilio_recording,
)


def recording_settings() -> Settings:
    return Settings.model_construct(
        twilio_account_sid="AC00000000000000000000000000000000",
        twilio_auth_token="test-auth-token",
    )


def test_download_twilio_recording_follows_redirects_and_normalizes_mp3(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_arguments: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        request_arguments.update(kwargs)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=b"ID3-playable-audio",
            headers={"Content-Type": "application/octet-stream"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    media = download_twilio_recording(
        recording_settings(),
        "RE00000000000000000000000000000001",
    )

    assert media.content == b"ID3-playable-audio"
    assert media.media_type == "audio/mpeg"
    assert request_arguments["follow_redirects"] is True
    assert request_arguments["headers"] == {"Accept": "audio/mpeg"}


@pytest.mark.parametrize(
    ("content", "content_type", "expected_message"),
    [
        (b"", "audio/mpeg", "empty recording"),
        (b"<html>not audio</html>", "text/html", "invalid recording response"),
        (b"opaque", "application/octet-stream", "invalid recording response"),
    ],
)
def test_download_twilio_recording_rejects_empty_or_non_audio_responses(
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
    content_type: str,
    expected_message: str,
) -> None:
    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            content=content,
            headers={"Content-Type": content_type},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(TwilioRecordingError, match=expected_message):
        download_twilio_recording(
            recording_settings(),
            "RE00000000000000000000000000000002",
        )


def test_download_twilio_recording_uses_safe_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **_kwargs: object) -> httpx.Response:
        return httpx.Response(
            401,
            request=httpx.Request("GET", url),
            json={"message": "private provider detail"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(TwilioRecordingError) as exc_info:
        download_twilio_recording(
            recording_settings(),
            "RE00000000000000000000000000000003",
        )

    assert str(exc_info.value) == "Twilio recording access was rejected."
    assert "private provider detail" not in str(exc_info.value)
