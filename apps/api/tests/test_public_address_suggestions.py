from typing import Any

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.integrations.realestateapi_client import (
    RealEstateAPIAddressSuggestion,
    RealEstateAPIError,
)
from app.main import app
from app.routers import public as public_router
from app.services.request_rate_limit import FixedWindowRateLimiter


class FakeRealEstateAPIClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, _settings: object) -> None:
        pass

    def autocomplete_addresses(
        self,
        search: str,
        *,
        max_results: int,
        preferred_state: str | None,
    ) -> list[RealEstateAPIAddressSuggestion]:
        self.calls.append(
            {
                "search": search,
                "max_results": max_results,
                "preferred_state": preferred_state,
            }
        )
        return [
            RealEstateAPIAddressSuggestion(
                provider_id="property-1",
                label="313 Vineyard Dr, Dallas, GA, 30132",
                street_address="313 Vineyard Dr",
                city="Dallas",
                state="GA",
                postal_code="30132",
            ),
            RealEstateAPIAddressSuggestion(
                provider_id="property-2",
                label="313 Vineyard Ave, Charlotte, NC, 28202",
                street_address="313 Vineyard Ave",
                city="Charlotte",
                state="NC",
                postal_code="28202",
            ),
        ][:max_results]


class FailingRealEstateAPIClient:
    def __init__(self, _settings: object) -> None:
        pass

    def autocomplete_addresses(self, *_args: object, **_kwargs: object) -> object:
        raise RealEstateAPIError("Provider unavailable and private details")


def test_public_address_suggestions_return_only_normalized_fields(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "realestateapi_api_key", "re_test_secret")
    monkeypatch.setattr(public_router, "RealEstateAPIClient", FakeRealEstateAPIClient)
    FakeRealEstateAPIClient.calls = []

    response = TestClient(app).get(
        "/api/v1/public/address-suggestions",
        params={"q": "  313   Vineyard  ", "limit": 2},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "available": True,
        "suggestions": [
            {
                "provider_id": "property-1",
                "label": "313 Vineyard Dr, Dallas, GA, 30132",
                "street_address": "313 Vineyard Dr",
                "city": "Dallas",
                "state": "GA",
                "postal_code": "30132",
            },
            {
                "provider_id": "property-2",
                "label": "313 Vineyard Ave, Charlotte, NC, 28202",
                "street_address": "313 Vineyard Ave",
                "city": "Charlotte",
                "state": "NC",
                "postal_code": "28202",
            },
        ],
    }
    assert FakeRealEstateAPIClient.calls == [
        {"search": "313 Vineyard", "max_results": 2, "preferred_state": "GA"}
    ]


def test_public_address_suggestions_fail_open_without_configuration_or_provider(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    client = TestClient(app)
    monkeypatch.setattr(settings, "realestateapi_api_key", None)

    missing_configuration = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "313 Vineyard"},
    )

    monkeypatch.setattr(settings, "realestateapi_api_key", "re_test_secret")
    monkeypatch.setattr(public_router, "RealEstateAPIClient", FailingRealEstateAPIClient)
    provider_failure = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "313 Vineyard"},
    )

    expected = {"available": False, "suggestions": []}
    assert missing_configuration.status_code == 200
    assert missing_configuration.headers["Cache-Control"] == "no-store"
    assert missing_configuration.json() == expected
    assert provider_failure.status_code == 200
    assert provider_failure.headers["Cache-Control"] == "no-store"
    assert provider_failure.json() == expected
    assert "private details" not in provider_failure.text


def test_public_address_suggestions_validate_and_rate_limit(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "realestateapi_api_key", "re_test_secret")
    monkeypatch.setattr(settings, "public_intake_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "public_conversion_event_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "public_conversion_event_rate_limit_window_seconds", 60)
    monkeypatch.setattr(public_router, "RealEstateAPIClient", FakeRealEstateAPIClient)
    monkeypatch.setattr(public_router, "public_intake_rate_limiter", FixedWindowRateLimiter())
    client = TestClient(app)

    validation_error = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "   "},
    )
    first = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "313 Vineyard"},
    )
    blocked = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "55 Auburn"},
    )

    assert validation_error.status_code == 422
    assert first.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many address searches. Please wait before trying again."
    assert int(blocked.headers["Retry-After"]) >= 1
