from dataclasses import dataclass
from typing import Any

import httpx


class GoogleStreetViewError(RuntimeError):
    pass


@dataclass(frozen=True)
class StreetViewMetadata:
    available: bool
    panorama_id: str | None
    imagery_date: str | None
    latitude: float | None
    longitude: float | None
    copyright: str | None
    raw_response: dict[str, Any]


class GoogleStreetViewClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://maps.googleapis.com/maps/api/streetview",
        timeout_seconds: float = 20,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_metadata(self, *, location: str) -> StreetViewMetadata:
        try:
            response = httpx.get(
                f"{self.base_url}/metadata",
                params={"location": location, "key": self.api_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GoogleStreetViewError("Google Street View metadata lookup failed.") from exc
        if not isinstance(payload, dict):
            raise GoogleStreetViewError("Google Street View returned invalid metadata.")
        status = str(payload.get("status") or "")
        if status == "ZERO_RESULTS":
            return StreetViewMetadata(False, None, None, None, None, None, payload)
        if status != "OK":
            message = str(payload.get("error_message") or status or "unknown error")
            raise GoogleStreetViewError(f"Google Street View metadata was rejected: {message}")
        location_payload = payload.get("location")
        coordinates = location_payload if isinstance(location_payload, dict) else {}
        return StreetViewMetadata(
            available=True,
            panorama_id=string_value(payload.get("pano_id")),
            imagery_date=string_value(payload.get("date")),
            latitude=number_value(coordinates.get("lat")),
            longitude=number_value(coordinates.get("lng")),
            copyright=string_value(payload.get("copyright")),
            raw_response=payload,
        )

    def get_image(self, *, panorama_id: str) -> tuple[bytes, str]:
        try:
            response = httpx.get(
                self.base_url,
                params={
                    "pano": panorama_id,
                    "size": "640x400",
                    "fov": 90,
                    "pitch": 0,
                    "return_error_code": "true",
                    "key": self.api_key,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GoogleStreetViewError("Google Street View image is unavailable.") from exc
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise GoogleStreetViewError("Google Street View returned a non-image response.")
        return response.content, content_type


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
