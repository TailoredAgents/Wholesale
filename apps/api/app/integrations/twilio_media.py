import re
from dataclasses import dataclass
from urllib.parse import ParseResult, urljoin, urlparse

import httpx

from app.core.config import Settings

MAX_TWILIO_MEDIA_COUNT = 10
ALLOWED_TWILIO_IMAGE_TYPES = {
    "image/gif": "gif",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/tiff": "tiff",
    "image/webp": "webp",
}
TWILIO_MEDIA_SID_PATTERN = re.compile(r"^ME[A-Za-z0-9]{32}$")
TWILIO_MESSAGE_SID_PATTERN = re.compile(r"^(?:MM|SM)[A-Za-z0-9]{32}$")


class TwilioMediaError(RuntimeError):
    pass


class TwilioMediaRejectedError(TwilioMediaError):
    pass


@dataclass(frozen=True)
class TwilioInboundMedia:
    index: int
    url: str
    content_type: str
    media_sid: str


@dataclass(frozen=True)
class TwilioDownloadedMedia:
    content: bytes
    content_type: str
    filename: str


def parse_twilio_inbound_media(
    payload: dict[str, str],
    settings: Settings,
) -> list[TwilioInboundMedia]:
    count = twilio_inbound_media_count(payload)
    if count == 0:
        return []
    message_sid = payload.get("MessageSid", "").strip()
    if not TWILIO_MESSAGE_SID_PATTERN.fullmatch(message_sid):
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid message identifier.")
    items: list[TwilioInboundMedia] = []
    for index in range(count):
        url = payload.get(f"MediaUrl{index}", "").strip()
        content_type = normalize_content_type(payload.get(f"MediaContentType{index}", ""))
        if not url or not content_type:
            raise TwilioMediaRejectedError("Twilio MMS omitted required media details.")
        media_sid = validate_twilio_media_url(
            url,
            account_sid=settings.twilio_account_sid,
            message_sid=message_sid,
        )
        if content_type not in ALLOWED_TWILIO_IMAGE_TYPES:
            raise TwilioMediaRejectedError("Stonegate accepts image attachments from MMS only.")
        items.append(
            TwilioInboundMedia(
                index=index,
                url=url,
                content_type=content_type,
                media_sid=media_sid,
            )
        )
    return items


def twilio_inbound_media_count(payload: dict[str, str]) -> int:
    raw_count = payload.get("NumMedia", "0").strip() or "0"
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid media count.") from exc
    if count < 0 or count > MAX_TWILIO_MEDIA_COUNT:
        raise TwilioMediaRejectedError("Twilio MMS supplied an unsupported media count.")
    return count


def validate_twilio_media_url(
    url: str,
    *,
    account_sid: str | None,
    message_sid: str,
) -> str:
    if not account_sid:
        raise TwilioMediaError("Twilio media access is not configured.")
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid media URL.") from exc
    port = safe_url_port(parsed)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.twilio.com"
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
    ):
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid media URL.")
    expected_prefix = (
        f"/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}/Media/"
    )
    if not parsed.path.startswith(expected_prefix):
        raise TwilioMediaRejectedError("Twilio MMS media does not match this account and message.")
    media_sid = parsed.path.removeprefix(expected_prefix).removesuffix(".json")
    if "/" in media_sid or not TWILIO_MEDIA_SID_PATTERN.fullmatch(media_sid):
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid media identifier.")
    return media_sid


class TwilioMediaClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def download(self, media: TwilioInboundMedia) -> TwilioDownloadedMedia:
        credentials = self._credentials()
        url = media.url
        content: bytes | None = None
        response_type = ""
        for redirect_count in range(3):
            parsed = urlparse(url)
            auth = credentials if parsed.hostname == "api.twilio.com" else None
            try:
                with self.client.stream("GET", url, auth=auth) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location", "")
                        if not location or redirect_count == 2:
                            raise TwilioMediaError("Twilio MMS media redirect was invalid.")
                        url = validate_twilio_media_redirect(urljoin(url, location))
                        continue
                    if response.status_code >= 500 or response.status_code == 429:
                        raise TwilioMediaError(
                            f"Twilio MMS media download failed with status {response.status_code}."
                        )
                    if response.status_code >= 400:
                        raise TwilioMediaRejectedError(
                            f"Twilio MMS media is unavailable (status {response.status_code})."
                        )
                    content_length = parse_content_length(response.headers.get("content-length"))
                    if (
                        content_length is not None
                        and content_length > self.settings.twilio_mms_max_media_bytes
                    ):
                        raise TwilioMediaRejectedError(
                            "The MMS photo exceeds Stonegate's size limit."
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if len(body) + len(chunk) > self.settings.twilio_mms_max_media_bytes:
                            raise TwilioMediaRejectedError(
                                "The MMS photo exceeds Stonegate's size limit."
                            )
                        body.extend(chunk)
                    content = bytes(body)
                    response_type = normalize_content_type(response.headers.get("content-type", ""))
                    break
            except httpx.RequestError as exc:
                raise TwilioMediaError("Twilio MMS media could not be reached.") from exc
        if content is None:
            raise TwilioMediaError("Twilio MMS media could not be retrieved.")
        if response_type and response_type != media.content_type:
            raise TwilioMediaRejectedError("Twilio MMS media type did not match the webhook.")
        validate_image_signature(content, media.content_type)
        extension = ALLOWED_TWILIO_IMAGE_TYPES[media.content_type]
        return TwilioDownloadedMedia(
            content=content,
            content_type=media.content_type,
            filename=f"seller-photo-{media.index + 1}.{extension}",
        )

    def _credentials(self) -> tuple[str, str]:
        if self.settings.twilio_api_key_sid and self.settings.twilio_api_key_secret:
            return self.settings.twilio_api_key_sid, self.settings.twilio_api_key_secret
        if self.settings.twilio_account_sid and self.settings.twilio_auth_token:
            return self.settings.twilio_account_sid, self.settings.twilio_auth_token
        raise TwilioMediaError("Twilio media access credentials are not configured.")


def get_twilio_media_client(settings: Settings) -> TwilioMediaClient:
    return TwilioMediaClient(settings)


def validate_twilio_media_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise TwilioMediaRejectedError("Twilio MMS media redirect was not trusted.") from exc
    port = safe_url_port(parsed)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"api.twilio.com", "mms.twiliocdn.com"}
        or port not in {None, 443}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise TwilioMediaRejectedError("Twilio MMS media redirect was not trusted.")
    return url


def safe_url_port(parsed_url: ParseResult) -> int | None:
    try:
        return parsed_url.port
    except ValueError as exc:
        raise TwilioMediaRejectedError("Twilio MMS supplied an invalid media URL.") from exc


def validate_image_signature(content: bytes, content_type: str) -> None:
    valid = {
        "image/gif": content.startswith((b"GIF87a", b"GIF89a")),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/tiff": content.startswith((b"II*\x00", b"MM\x00*")),
        "image/webp": len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP",
        "image/heic": is_heif_family(content),
        "image/heif": is_heif_family(content),
    }.get(content_type, False)
    if not valid:
        raise TwilioMediaRejectedError("The MMS attachment was not a valid image file.")


def is_heif_family(content: bytes) -> bool:
    return len(content) >= 12 and content[4:8] == b"ftyp" and content[8:12] in {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"mif1",
        b"msf1",
    }


def normalize_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def parse_content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None
