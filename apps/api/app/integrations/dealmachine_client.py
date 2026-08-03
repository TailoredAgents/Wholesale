from typing import Any

import httpx

from app.core.config import Settings


class DealMachineError(RuntimeError):
    pass


class DealMachineClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.dealmachine_api_key:
            raise DealMachineError("DealMachine API credentials are not configured.")
        self.base_url = settings.dealmachine_base_url.rstrip("/")
        self.api_key = settings.dealmachine_api_key
        self.client = client or httpx.Client(
            timeout=settings.dealmachine_request_timeout_seconds
        )

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", "/properties/search", json=request)
        if not isinstance(payload.get("data"), list):
            raise DealMachineError("DealMachine returned an unexpected search response.")
        return payload

    def estimate_property_search(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/properties/search",
            json={**request, "estimate_cost": True},
        )
        if not isinstance(payload.get("estimated_credits"), dict):
            raise DealMachineError("DealMachine returned an unexpected cost estimate.")
        return payload

    def get_usage(self) -> dict[str, Any]:
        payload = self._request("GET", "/usage")
        if not isinstance(payload.get("plan"), dict) or not isinstance(
            payload.get("credits"), dict
        ):
            raise DealMachineError("DealMachine returned an unexpected usage response.")
        return payload

    def list_property_filters(self) -> list[object]:
        payload = self._request(
            "GET",
            "/filters",
            params={
                "source_type": "properties",
                "search": "Property Type",
                "per_page": 250,
            },
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise DealMachineError("DealMachine returned unexpected filter metadata.")
        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str | int | float | bool | None] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=json,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise DealMachineError(_error_message(exc.response)) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DealMachineError("DealMachine could not complete the buyer search.") from exc
        if not isinstance(payload, dict):
            raise DealMachineError("DealMachine returned an unexpected response.")
        return payload


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        request_id = error.get("request_id")
        suffix = f" (request {request_id})" if isinstance(request_id, str) else ""
        return f"DealMachine request failed: {error['message']}{suffix}"
    if response.status_code in {401, 403}:
        return "DealMachine rejected the API key or account permissions."
    if response.status_code == 429:
        return "DealMachine rate-limited the request. Try again shortly."
    return f"DealMachine request failed with status {response.status_code}."
