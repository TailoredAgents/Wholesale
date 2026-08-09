from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings

REALESTATEAPI_IMAGE_HOSTS = frozenset({"imagecdn.realty.dev"})
MAX_PROPERTY_IMAGE_BYTES = 12_000_000


class RealEstateAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealEstateAPIPropertyDetail:
    found: bool
    property: dict[str, Any]
    comparables: list[dict[str, Any]]
    status_code: int
    status_message: str | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class RealEstateAPIPropertySearch:
    properties: list[dict[str, Any]]
    result_count: int | None
    response_count: int
    status_code: int
    status_message: str | None
    raw_response: dict[str, Any]


class RealEstateAPIClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.realestateapi_api_key:
            raise RealEstateAPIError("REALESTATEAPI_API_KEY is not configured.")
        self.api_key = settings.realestateapi_api_key
        self.base_url = settings.realestateapi_base_url.rstrip("/")
        self.timeout_seconds = settings.realestateapi_request_timeout_seconds
        self.client = client

    def get_property_detail(
        self,
        *,
        address: str | None = None,
        apn: str | None = None,
        county: str | None = None,
        state: str | None = None,
        include_comps: bool = True,
    ) -> RealEstateAPIPropertyDetail:
        clean_address = address.strip() if address and address.strip() else None
        clean_apn = apn.strip() if apn and apn.strip() else None
        if clean_address and clean_apn:
            raise RealEstateAPIError(
                "RealEstateAPI property detail accepts one lookup identity at a time."
            )
        if clean_address:
            # Preserve the legacy House request shape and ordering.
            request_payload: dict[str, Any] = {
                "address": clean_address,
                "exact_match": True,
                "comps": include_comps,
            }
        elif (
            clean_apn
            and county
            and county.strip()
            and state
            and len(state.strip()) == 2
        ):
            request_payload = {
                "apn": clean_apn,
                "county": county.strip(),
                "state": state.strip().upper(),
                "exact_match": True,
                "comps": include_comps,
            }
        else:
            raise RealEstateAPIError(
                "RealEstateAPI property detail requires an address or APN with county and state."
            )
        try:
            request = self.client.post if self.client is not None else httpx.post
            response = request(
                f"{self.base_url}/v2/PropertyDetail",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                },
                json=request_payload,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise RealEstateAPIError(f"RealEstateAPI property request failed: {exc}") from exc

        if response.status_code == 404:
            return RealEstateAPIPropertyDetail(
                found=False,
                property={},
                comparables=[],
                status_code=404,
                status_message="No exact property match was found.",
                raw_response={},
            )
        if response.is_error:
            raise RealEstateAPIError(_http_error_message(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise RealEstateAPIError("RealEstateAPI returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RealEstateAPIError("RealEstateAPI returned an unexpected response shape.")

        payload_status = _integer(payload.get("statusCode")) or response.status_code
        status_message = _string(payload.get("statusMessage"))
        if payload_status == 404:
            return RealEstateAPIPropertyDetail(
                found=False,
                property={},
                comparables=[],
                status_code=payload_status,
                status_message=status_message or "No exact property match was found.",
                raw_response=payload,
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RealEstateAPIError(
                status_message or "RealEstateAPI did not return a property record."
            )
        comps = data.get("comps")
        return RealEstateAPIPropertyDetail(
            found=True,
            property=data,
            comparables=[item for item in comps if isinstance(item, dict)]
            if isinstance(comps, list)
            else [],
            status_code=payload_status,
            status_message=status_message,
            raw_response=payload,
        )

    def search_land_sales(
        self,
        *,
        state: str,
        county: str | None,
        latitude: float | None,
        longitude: float | None,
        radius_miles: float,
        sale_date_min: str,
        lot_size_min: int,
        lot_size_max: int,
        size: int,
    ) -> RealEstateAPIPropertySearch:
        if not state.strip() or len(state.strip()) != 2:
            raise RealEstateAPIError("Land comparable search requires a two-letter state.")
        if (latitude is None) != (longitude is None):
            raise RealEstateAPIError(
                "Land comparable search requires both latitude and longitude."
            )
        request_payload: dict[str, Any] = {
            "count": False,
            "size": size,
            "resultIndex": 0,
            "property_type": "LAND",
            "last_sale_arms_length": True,
            "last_sale_date_min": sale_date_min,
            "lot_size_min": lot_size_min,
            "lot_size_max": lot_size_max,
            "state": state.strip().upper(),
        }
        if latitude is not None and longitude is not None:
            request_payload.update(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius": radius_miles,
                }
            )
        elif county and county.strip():
            request_payload["county"] = county.strip()
        else:
            raise RealEstateAPIError(
                "Land comparable search requires coordinates or a county."
            )
        try:
            request = self.client.post if self.client is not None else httpx.post
            response = request(
                f"{self.base_url}/v2/PropertySearch",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                },
                json=request_payload,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise RealEstateAPIError(
                f"RealEstateAPI land comparable request failed: {exc}"
            ) from exc
        if response.is_error:
            raise RealEstateAPIError(_http_error_message(response))
        try:
            payload = response.json()
        except ValueError as exc:
            raise RealEstateAPIError("RealEstateAPI returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RealEstateAPIError("RealEstateAPI returned an unexpected response shape.")
        data = payload.get("data")
        if isinstance(data, dict):
            nested = data.get("results") or data.get("properties") or data.get("data")
            records = nested if isinstance(nested, list) else []
        else:
            records = data if isinstance(data, list) else []
        properties = [item for item in records if isinstance(item, dict)]
        payload_status = _integer(payload.get("statusCode")) or response.status_code
        return RealEstateAPIPropertySearch(
            properties=properties,
            result_count=_integer(payload.get("resultCount")),
            response_count=_integer(payload.get("responseCount")) or len(properties),
            status_code=payload_status,
            status_message=_string(payload.get("statusMessage")),
            raw_response=payload,
        )


def realestateapi_primary_image_url(property_payload: dict[str, Any]) -> str | None:
    media = property_payload.get("media")
    if not isinstance(media, dict):
        return None
    candidates: list[Any] = [media.get("primaryListingImageUrl")]
    photos = media.get("photosList")
    if isinstance(photos, list) and photos and isinstance(photos[0], dict):
        candidates.extend(
            [photos[0].get("highRes"), photos[0].get("midRes"), photos[0].get("lowRes")]
        )
    for value in candidates:
        url = _string(value)
        if url and is_realestateapi_image_url(url):
            return url
    return None


def is_realestateapi_image_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.lower() in REALESTATEAPI_IMAGE_HOSTS
        and parsed.username is None
        and parsed.password is None
    )


def get_realestateapi_image(
    image_url: str,
    *,
    timeout_seconds: float,
) -> tuple[bytes, str]:
    if not is_realestateapi_image_url(image_url):
        raise RealEstateAPIError("RealEstateAPI returned an unsupported property image URL.")
    try:
        response = httpx.get(
            image_url,
            headers={"Accept": "image/jpeg,image/png,image/webp"},
            timeout=timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RealEstateAPIError(f"RealEstateAPI property image request failed: {exc}") from exc
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise RealEstateAPIError("RealEstateAPI property image returned unsupported content.")
    if len(response.content) > MAX_PROPERTY_IMAGE_BYTES:
        raise RealEstateAPIError("RealEstateAPI property image exceeded the size limit.")
    return response.content, content_type


def _http_error_message(response: httpx.Response) -> str:
    message = None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = _string(payload.get("statusMessage") or payload.get("message"))
    suffix = f": {message}" if message else ""
    return f"RealEstateAPI property request failed (HTTP {response.status_code}){suffix}"


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
