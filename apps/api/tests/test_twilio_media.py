import base64

import httpx
import pytest

from app.core.config import Settings
from app.integrations.twilio_media import (
    TwilioInboundMedia,
    TwilioMediaClient,
    TwilioMediaRejectedError,
    validate_twilio_media_redirect,
    validate_twilio_media_url,
)

ACCOUNT_SID = "AC00000000000000000000000000000000"
MESSAGE_SID = "SM00000000000000000000000000000001"
MEDIA_SID = "ME00000000000000000000000000000001"
MEDIA_URL = (
    f"https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}"
    f"/Messages/{MESSAGE_SID}/Media/{MEDIA_SID}"
)


def test_twilio_media_download_uses_basic_auth_and_validates_the_image() -> None:
    api_key = "SK00000000000000000000000000000000"
    api_secret = "mms-test-secret"
    image = b"\xff\xd8\xff\xe0seller-photo"

    def handle(request: httpx.Request) -> httpx.Response:
        expected_auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        assert request.url == httpx.URL(MEDIA_URL)
        assert request.headers["Authorization"] == f"Basic {expected_auth}"
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, content=image)

    settings = Settings.model_construct(
        twilio_account_sid=ACCOUNT_SID,
        twilio_api_key_sid=api_key,
        twilio_api_key_secret=api_secret,
    )
    media_client = TwilioMediaClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False),
    )

    result = media_client.download(
        TwilioInboundMedia(
            index=0,
            url=MEDIA_URL,
            content_type="image/jpeg",
            media_sid=MEDIA_SID,
        )
    )

    assert result.content == image
    assert result.content_type == "image/jpeg"
    assert result.filename == "seller-photo-1.jpg"


@pytest.mark.parametrize(
    "url",
    [
        MEDIA_URL.replace("api.twilio.com", "attacker.example"),
        MEDIA_URL.replace(ACCOUNT_SID, "AC11111111111111111111111111111111"),
        MEDIA_URL.replace(MESSAGE_SID, "SM11111111111111111111111111111111"),
        MEDIA_URL.replace("api.twilio.com", "api.twilio.com:invalid"),
        f"{MEDIA_URL}?redirect=https://attacker.example",
    ],
)
def test_twilio_media_url_rejects_untrusted_or_mismatched_urls(url: str) -> None:
    with pytest.raises(TwilioMediaRejectedError):
        validate_twilio_media_url(
            url,
            account_sid=ACCOUNT_SID,
            message_sid=MESSAGE_SID,
        )


def test_twilio_media_redirect_rejects_an_untrusted_host() -> None:
    with pytest.raises(TwilioMediaRejectedError):
        validate_twilio_media_redirect("https://attacker.example/customer-photo.jpg")


def test_twilio_media_download_rejects_content_that_is_not_an_image() -> None:
    settings = Settings.model_construct(
        twilio_account_sid=ACCOUNT_SID,
        twilio_auth_token="test-auth-token",
    )
    media_client = TwilioMediaClient(
        settings,
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={"Content-Type": "image/jpeg"},
                    content=b"<script>not a photo</script>",
                )
            ),
            follow_redirects=False,
        ),
    )

    with pytest.raises(TwilioMediaRejectedError, match="valid image"):
        media_client.download(
            TwilioInboundMedia(
                index=0,
                url=MEDIA_URL,
                content_type="image/jpeg",
                media_sid=MEDIA_SID,
            )
        )
