from __future__ import annotations

import email.utils
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.core.config import Settings

MAX_RESPONSE_BYTES = 2_000_000
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


class BatchDialerAPIError(RuntimeError):
    """Safe provider error that never includes the configured API key."""


class BatchDialerAuthenticationError(BatchDialerAPIError):
    pass


class BatchDialerTransientError(BatchDialerAPIError):
    pass


class BatchDialerContractError(BatchDialerAPIError):
    pass


@dataclass(frozen=True)
class BatchDialerCDRPage:
    items: tuple[dict[str, Any], ...]
    next_page: str | None


class BatchDialerClient:
    """Small, bounded client for BatchDialer's documented API surface."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        api_key = (settings.batchdialer_api_key or "").strip()
        if not api_key:
            raise BatchDialerAuthenticationError("BATCHDIALER_API_KEY is not configured.")
        self._api_key = api_key
        self._base_url = settings.batchdialer_api_base_url.rstrip("/")
        self._timeout = settings.batchdialer_http_timeout_seconds
        self._max_attempts = settings.batchdialer_http_max_attempts
        self._account_timezone = ZoneInfo(settings.batchdialer_account_timezone)
        self._client = client
        self._sleeper = sleeper
        self._jitter = jitter

    def get_campaigns(self) -> tuple[dict[str, Any], ...]:
        payload = self._request_json("GET", "/campaigns")
        candidate = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(candidate, list):
            raise BatchDialerContractError("BatchDialer campaigns returned an invalid shape.")
        return tuple(_dict_items(candidate, "campaigns"))

    def get_cdr_page(
        self,
        *,
        call_date: date,
        page_length: int = 100,
        next_page: str | None = None,
    ) -> BatchDialerCDRPage:
        if not 1 <= page_length <= 100:
            raise ValueError("BatchDialer page length must be between 1 and 100.")
        params: dict[str, str | int] = {
            "pagelength": page_length,
            "callDate": datetime.combine(
                call_date,
                datetime.min.time(),
                tzinfo=self._account_timezone,
            ).isoformat(),
        }
        if next_page:
            params["next_page"] = next_page
        payload = self._request_json("GET", "/v2/cdrs", params=params)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise BatchDialerContractError("BatchDialer CDRs returned an invalid shape.")
        raw_cursor = payload.get("nextPage")
        if raw_cursor is not None and not isinstance(raw_cursor, str):
            raise BatchDialerContractError("BatchDialer returned an invalid CDR cursor.")
        cursor = raw_cursor.strip() if isinstance(raw_cursor, str) else None
        return BatchDialerCDRPage(
            items=tuple(_dict_items(payload["items"], "CDRs")),
            next_page=cursor or None,
        )

    def get_contact(self, contact_id: str | int) -> dict[str, Any]:
        normalized = _numeric_identifier(contact_id, "contact")
        payload = self._request_json("GET", f"/contact/{normalized}")
        if not isinstance(payload, dict):
            raise BatchDialerContractError("BatchDialer contact returned an invalid shape.")
        return payload

    def get_contact_history(self, vendor_contact_id: str) -> tuple[dict[str, Any], ...]:
        normalized = vendor_contact_id.strip()
        if not normalized:
            return ()
        payload = self._request_json(
            "POST",
            "/cdrs/by-lead-id",
            json_body={"vendor_contact_id": normalized, "sort_order": "desc"},
        )
        if not isinstance(payload, list):
            raise BatchDialerContractError("BatchDialer call history returned an invalid shape.")
        return tuple(_dict_items(payload, "call history"))

    def get_transcript(self, cdr_id: str | int) -> tuple[dict[str, Any], ...]:
        normalized = _numeric_identifier(cdr_id, "CDR")
        payload = self._request_json("GET", f"/cdrs/{normalized}/transcription")
        if not isinstance(payload, list):
            raise BatchDialerContractError("BatchDialer transcript returned an invalid shape.")
        segments = tuple(_dict_items(payload, "transcript"))
        for segment in segments:
            if not isinstance(segment.get("role"), str) or not isinstance(
                segment.get("text"), str
            ):
                raise BatchDialerContractError(
                    "BatchDialer transcript contains an invalid segment."
                )
        return segments

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        last_error: BatchDialerAPIError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._send(method, path, params=params, json_body=json_body)
            except httpx.HTTPError as exc:
                last_error = BatchDialerTransientError(
                    "BatchDialer request failed before a response was received."
                )
                if attempt == self._max_attempts:
                    raise last_error from exc
                self._sleeper(self._backoff_seconds(attempt, None))
                continue

            if response.status_code in {401, 403}:
                raise BatchDialerAuthenticationError(
                    "BatchDialer rejected the configured API key."
                )
            if response.is_redirect:
                raise BatchDialerContractError("BatchDialer returned an unexpected redirect.")
            if response.status_code in RETRYABLE_STATUS_CODES:
                last_error = BatchDialerTransientError(
                    f"BatchDialer temporarily failed with HTTP {response.status_code}."
                )
                if attempt == self._max_attempts:
                    raise last_error
                self._sleeper(
                    self._backoff_seconds(attempt, response.headers.get("Retry-After"))
                )
                continue
            if response.is_error:
                raise BatchDialerAPIError(
                    f"BatchDialer request failed with HTTP {response.status_code}."
                )
            content_length = response.headers.get("content-length")
            if (
                content_length
                and content_length.isdigit()
                and int(content_length) > MAX_RESPONSE_BYTES
            ):
                raise BatchDialerContractError("BatchDialer response is too large.")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise BatchDialerContractError("BatchDialer response is too large.")
            try:
                return response.json()
            except ValueError as exc:
                raise BatchDialerContractError("BatchDialer returned invalid JSON.") from exc
        assert last_error is not None
        raise last_error

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None,
        json_body: dict[str, Any] | None,
    ) -> httpx.Response:
        kwargs: dict[str, Any] = {
            "headers": {
                "Accept": "application/json",
                "X-ApiKey": self._api_key,
            },
            "params": params,
            "timeout": self._timeout,
            "follow_redirects": False,
        }
        if json_body is not None:
            kwargs["headers"]["Content-Type"] = "application/json"
            kwargs["json"] = json_body
        url = f"{self._base_url}{path}"
        if self._client is not None:
            return self._client.request(method, url, **kwargs)
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            return client.request(method, url, **kwargs)

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        parsed_retry = _retry_after_seconds(retry_after)
        if parsed_retry is not None:
            return min(parsed_retry, 60.0)
        return float(min(2 ** (attempt - 1) + float(self._jitter()), 30.0))


def _dict_items(values: list[Any], label: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            raise BatchDialerContractError(f"BatchDialer {label} contains an invalid record.")
        items.append(value)
    return items


def _numeric_identifier(value: str | int, label: str) -> str:
    normalized = str(value).strip()
    if not normalized.isdigit():
        raise ValueError(f"BatchDialer {label} identifier must be numeric.")
    return normalized


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.strip()
    try:
        return max(0.0, float(normalized))
    except ValueError:
        pass
    try:
        retry_at = email.utils.parsedate_to_datetime(normalized)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
