import hashlib
import hmac
from typing import Any

import httpx

from app.core.config import Settings

META_LEAD_FIELDS = ",".join(
    (
        "id",
        "created_time",
        "ad_id",
        "ad_name",
        "adset_id",
        "adset_name",
        "campaign_id",
        "campaign_name",
        "form_id",
        "field_data",
        "platform",
        "is_organic",
    )
)


class MetaLeadAdsError(RuntimeError):
    def __init__(self, message: str, *, response: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.response = response


class MetaLeadAdsClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=settings.meta_lead_ads_request_timeout_seconds
        )
        self.owns_client = client is None

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def fetch_lead(self, provider_lead_id: str) -> dict[str, object]:
        if not provider_lead_id.isdigit():
            raise MetaLeadAdsError("Meta returned an invalid lead identifier.")
        if not self.settings.meta_lead_ads_access_token:
            raise MetaLeadAdsError("Meta Lead Ads access token is not configured.")
        url = (
            f"https://graph.facebook.com/{self.settings.meta_lead_ads_api_version}/"
            f"{provider_lead_id}"
        )
        try:
            response = self.client.get(
                url,
                params={
                    "access_token": self.settings.meta_lead_ads_access_token,
                    "fields": META_LEAD_FIELDS,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            provider_response = safe_response(getattr(exc, "response", None))
            message = provider_error_message(provider_response) or (
                f"{type(exc).__name__} while contacting Meta"
            )
            message = message.replace(self.settings.meta_lead_ads_access_token, "[redacted]")
            raise MetaLeadAdsError(
                f"Meta Lead Ads retrieval failed: {message[:700]}",
                response=provider_response,
            ) from exc
        if not isinstance(payload, dict):
            raise MetaLeadAdsError("Meta Lead Ads returned an invalid response.")
        if str(payload.get("id") or "") != provider_lead_id:
            raise MetaLeadAdsError("Meta Lead Ads returned a different lead identifier.")
        return {str(key): value for key, value in payload.items()}


def verify_meta_signature(raw_body: bytes, signature: str | None, app_secret: str | None) -> bool:
    if not signature or not app_secret or not signature.startswith("sha256="):
        return False
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied)


def safe_response(response: httpx.Response | None) -> dict[str, object] | None:
    if response is None:
        return None
    try:
        payload: Any = response.json()
    except (TypeError, ValueError):
        return {"status_code": response.status_code, "detail": response.text[:500]}
    if not isinstance(payload, dict):
        return {"status_code": response.status_code, "detail": str(payload)[:500]}
    result: dict[str, object] = {"status_code": response.status_code}
    error = payload.get("error")
    if isinstance(error, dict):
        result["error"] = {
            key: value
            for key, value in error.items()
            if key in {"message", "type", "code", "error_subcode", "fbtrace_id"}
            and isinstance(value, (str, int, float, bool))
        }
    return result


def provider_error_message(response: dict[str, object] | None) -> str | None:
    if not response:
        return None
    error = response.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return str(error["message"])
    detail = response.get("detail")
    return detail if isinstance(detail, str) else None
