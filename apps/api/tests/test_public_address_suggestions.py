from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.main import app
from app.routers import public as public_router
from app.services.request_rate_limit import FixedWindowRateLimiter


def test_public_address_suggestions_are_retired_in_favor_of_direct_entry(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "realestateapi_api_key", "re_test_secret")

    response = TestClient(app).get(
        "/api/v1/public/address-suggestions",
        params={"q": "  313   Vineyard  ", "limit": 2},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {"available": False, "suggestions": []}


def test_public_address_suggestions_do_not_depend_on_retired_provider_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    client = TestClient(app)
    monkeypatch.setattr(settings, "realestateapi_api_key", None)

    missing_configuration = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "313 Vineyard"},
    )

    monkeypatch.setattr(settings, "realestateapi_api_key", "unused-retired-secret")
    configured_but_retired = client.get(
        "/api/v1/public/address-suggestions",
        params={"q": "313 Vineyard"},
    )

    expected = {"available": False, "suggestions": []}
    assert missing_configuration.status_code == 200
    assert missing_configuration.headers["Cache-Control"] == "no-store"
    assert missing_configuration.json() == expected
    assert configured_but_retired.status_code == 200
    assert configured_but_retired.headers["Cache-Control"] == "no-store"
    assert configured_but_retired.json() == expected


def test_public_address_suggestions_validate_and_rate_limit(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "realestateapi_api_key", "re_test_secret")
    monkeypatch.setattr(settings, "public_intake_rate_limit_enabled", True)
    monkeypatch.setattr(settings, "public_conversion_event_rate_limit_requests", 1)
    monkeypatch.setattr(settings, "public_conversion_event_rate_limit_window_seconds", 60)
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
