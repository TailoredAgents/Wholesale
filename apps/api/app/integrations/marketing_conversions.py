from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.models.foundation import OfflineConversionExport

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_INGEST_URL = "https://datamanager.googleapis.com/v1/events:ingest"
META_EVENT_NAMES = {
    "qualified_lead": "QualifiedLead",
    "appointment_scheduled": "Schedule",
    "contract_signed": "ContractSigned",
    "funded_deal": "Purchase",
    "ViewContent": "ViewContent",
    "Contact": "Contact",
    "Lead": "Lead",
}


@dataclass(frozen=True)
class ConversionDeliveryResult:
    request_id: str | None
    response: dict[str, Any]


class ConversionDeliveryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        response: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response
        self.request_id = request_id


class MarketingConversionClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=30)
        self.owns_client = client is None

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def deliver(self, export: OfflineConversionExport) -> ConversionDeliveryResult:
        if export.platform == "google_ads":
            return self._deliver_google(export)
        if export.platform == "meta":
            return self._deliver_meta(export)
        raise ConversionDeliveryError(f"Unsupported conversion platform: {export.platform}")

    def _deliver_google(
        self,
        export: OfflineConversionExport,
    ) -> ConversionDeliveryResult:
        blockers = self.settings.google_conversion_configuration_blockers
        if blockers:
            raise ConversionDeliveryError(
                f"Google conversion delivery is not configured: {', '.join(blockers)}"
            )
        try:
            token_response = self.client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": self.settings.google_data_manager_client_id,
                    "client_secret": self.settings.google_data_manager_client_secret,
                    "refresh_token": self.settings.google_data_manager_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
            response = self.client.post(
                GOOGLE_INGEST_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json=build_google_payload(export, self.settings),
            )
            response.raise_for_status()
            body = sanitize_response(response.json())
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            response_body = response_json(getattr(exc, "response", None))
            raise ConversionDeliveryError(
                provider_error_message("Google Data Manager", exc, response_body),
                response=response_body,
            ) from exc
        return ConversionDeliveryResult(
            request_id=string_value(body.get("requestId")),
            response=body,
        )

    def _deliver_meta(
        self,
        export: OfflineConversionExport,
    ) -> ConversionDeliveryResult:
        blockers = self.settings.meta_conversion_configuration_blockers
        if blockers:
            raise ConversionDeliveryError(
                f"Meta conversion delivery is not configured: {', '.join(blockers)}"
            )
        url = (
            f"https://graph.facebook.com/{self.settings.meta_conversions_api_version}/"
            f"{self.settings.meta_pixel_id}/events"
        )
        payload = build_meta_payload(export, self.settings)
        response: httpx.Response | None = None
        try:
            response = self.client.post(
                url,
                # Keep credentials out of the URL so httpx errors, reverse-proxy logs,
                # and provider request IDs can never capture the access token.
                headers={
                    "Authorization": (f"Bearer {self.settings.meta_conversions_access_token}")
                },
                json=payload,
            )
            response.raise_for_status()
            body = sanitize_response(response.json())
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            exception_response = getattr(exc, "response", None)
            response_body = with_meta_delivery_metadata(
                response_json(exception_response if exception_response is not None else response)
                or {},
                test_mode_enabled=bool(self.settings.meta_test_event_code),
            )
            raise ConversionDeliveryError(
                provider_error_message("Meta Conversions API", exc, response_body),
                response=response_body,
                request_id=string_value(response_body.get("fbtrace_id")),
            ) from exc
        body = with_meta_delivery_metadata(
            body,
            test_mode_enabled=bool(self.settings.meta_test_event_code),
        )
        accepted_count = body.get("events_received")
        if type(accepted_count) is not int or accepted_count != 1:
            raise ConversionDeliveryError(
                "Meta Conversions API did not confirm acceptance of exactly one event.",
                response=body,
                request_id=string_value(body.get("fbtrace_id")),
            )
        return ConversionDeliveryResult(
            request_id=string_value(body.get("fbtrace_id")),
            response=body,
        )


def build_google_payload(
    export: OfflineConversionExport,
    settings: Settings,
) -> dict[str, Any]:
    action_id = settings.google_data_manager_conversion_actions.get(export.event_name)
    if not action_id:
        raise ConversionDeliveryError(
            f"No Google conversion action is mapped for {export.event_name}."
        )
    snapshot = export.payload_snapshot
    user_identifiers = [
        *[
            {"emailAddress": value}
            for value in snapshot.get("email_hashes", [])
            if isinstance(value, str)
        ],
        *[
            {"phoneNumber": value}
            for value in snapshot.get("phone_hashes", [])
            if isinstance(value, str)
        ],
    ]
    event: dict[str, Any] = {
        "transactionId": export.event_key,
        "eventTimestamp": export.occurred_at.isoformat(),
        "eventSource": "WEB",
        "adIdentifiers": {export.click_id_type: export.click_id},
    }
    if user_identifiers:
        event["userData"] = {"userIdentifiers": user_identifiers[:10]}
    if export.value_cents is not None:
        event["conversionValue"] = export.value_cents / 100
        event["currency"] = export.currency
    destination: dict[str, Any] = {
        "reference": "stonegate_conversion",
        "operatingAccount": {
            "accountType": "GOOGLE_ADS",
            "accountId": settings.google_data_manager_operating_account_id,
        },
        "productDestinationId": action_id,
    }
    if settings.google_data_manager_login_account_id:
        destination["loginAccount"] = {
            "accountType": "GOOGLE_ADS",
            "accountId": settings.google_data_manager_login_account_id,
        }
    return {
        "destinations": [destination],
        "events": [event],
        "encoding": "HEX",
        "validateOnly": False,
    }


def build_meta_payload(
    export: OfflineConversionExport,
    settings: Settings,
) -> dict[str, Any]:
    snapshot = export.payload_snapshot
    user_data: dict[str, Any] = {}
    for snapshot_key, meta_key in (
        ("email_hashes", "em"),
        ("first_name_hashes", "fn"),
        ("last_name_hashes", "ln"),
    ):
        hashes = [
            value for value in snapshot.get(snapshot_key, []) if isinstance(value, str)
        ]
        if hashes:
            user_data[meta_key] = hashes
    external_id_hash = snapshot.get("external_id_hash")
    if isinstance(external_id_hash, str):
        user_data["external_id"] = [external_id_hash]
    client_ip_address = snapshot.get("client_ip_address")
    if isinstance(client_ip_address, str) and client_ip_address:
        user_data["client_ip_address"] = client_ip_address
    client_user_agent = snapshot.get("client_user_agent")
    if isinstance(client_user_agent, str) and client_user_agent:
        user_data["client_user_agent"] = client_user_agent
    fbc = snapshot.get("fbc")
    if isinstance(fbc, str) and fbc:
        user_data["fbc"] = fbc
    fbp = snapshot.get("fbp")
    if isinstance(fbp, str) and fbp:
        user_data["fbp"] = fbp
    fbclid = snapshot.get("fbclid")
    if not isinstance(fbclid, str) or not fbclid.strip():
        fbclid = export.click_id if export.click_id_type == "fbclid" else None
    click_timestamp = original_click_timestamp(
        snapshot.get("click_captured_at"),
        occurred_at=export.occurred_at,
    )
    if isinstance(fbclid, str) and fbclid and click_timestamp is not None:
        user_data.setdefault(
            "fbc",
            (
                fbclid
                if fbclid.startswith("fb.")
                else f"fb.1.{int(click_timestamp.timestamp() * 1000)}.{fbclid}"
            ),
        )
    event: dict[str, Any] = {
        "event_name": META_EVENT_NAMES.get(export.event_name, export.event_name),
        "event_time": int(export.occurred_at.timestamp()),
        "event_id": export.event_key,
        "action_source": "website",
        "event_source_url": snapshot.get("landing_page") or settings.marketing_website_base_url,
        "user_data": user_data,
    }
    if export.value_cents is not None:
        event["custom_data"] = {
            "value": export.value_cents / 100,
            "currency": export.currency,
        }
    payload: dict[str, Any] = {"data": [event]}
    if settings.meta_test_event_code:
        payload["test_event_code"] = settings.meta_test_event_code
    return payload


def response_json(response: httpx.Response | None) -> dict[str, Any] | None:
    if response is None:
        return None
    try:
        body = response.json()
    except (TypeError, ValueError):
        text = response.text.strip()
        return (
            {"status_code": response.status_code, "detail": text[:500]}
            if text
            else {"status_code": response.status_code}
        )
    sanitized = sanitize_response(body)
    sanitized["status_code"] = response.status_code
    return sanitized


def with_meta_delivery_metadata(
    body: dict[str, Any],
    *,
    test_mode_enabled: bool,
) -> dict[str, Any]:
    accepted_count = body.get("events_received")
    messages = body.get("messages")
    body["stonegate_delivery"] = {
        "accepted_count": accepted_count if type(accepted_count) is int else None,
        "warning_count": len(messages) if isinstance(messages, list) else 0,
        "test_mode_enabled": test_mode_enabled,
    }
    return body


def sanitize_response(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"detail": str(value)[:500]}
    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = "".join(character for character in key.lower() if character.isalnum())
        if "token" in normalized_key or normalized_key == "authorization":
            continue
        if isinstance(item, dict):
            sanitized[key] = sanitize_response(item)
        elif isinstance(item, list):
            sanitized[key] = [
                sanitize_response(entry) if isinstance(entry, dict) else str(entry)[:500]
                for entry in item[:20]
            ]
        elif isinstance(item, str):
            sanitized[key] = item[:1000]
        elif isinstance(item, (int, float, bool)) or item is None:
            sanitized[key] = item
        else:
            sanitized[key] = str(item)[:500]
    return sanitized


def provider_error_message(
    provider: str,
    exc: Exception,
    response: dict[str, Any] | None,
) -> str:
    detail = response.get("error") if response else None
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status")
    if not detail and response:
        detail = response.get("detail")
    if not detail:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
            detail = f"HTTP {exc.response.status_code}"
        elif isinstance(exc, httpx.RequestError):
            detail = type(exc).__name__
        else:
            detail = type(exc).__name__
    return f"{provider} delivery failed: {str(detail)[:700]}"


def original_click_timestamp(
    value: object,
    *,
    occurred_at: datetime,
) -> datetime | None:
    """Return only a plausible, timezone-aware original click time."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    normalized = parsed.astimezone(UTC)
    normalized_occurrence = (
        occurred_at.replace(tzinfo=UTC)
        if occurred_at.tzinfo is None
        else occurred_at.astimezone(UTC)
    )
    if normalized > normalized_occurrence + timedelta(minutes=5):
        return None
    return normalized


def string_value(value: Any) -> str | None:
    return str(value) if value is not None else None
