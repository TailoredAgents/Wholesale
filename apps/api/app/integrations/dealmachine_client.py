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
        try:
            response = self.client.post(
                f"{self.base_url}/properties/search",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=request,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise DealMachineError(_error_message(exc.response)) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DealMachineError("DealMachine could not complete the buyer search.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise DealMachineError("DealMachine returned an unexpected search response.")
        return payload


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return f"DealMachine search failed: {error['message']}"
    return f"DealMachine search failed with status {response.status_code}."
