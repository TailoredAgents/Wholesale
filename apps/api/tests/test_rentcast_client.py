from typing import Any

import httpx
import pytest
from pytest import MonkeyPatch

from app.integrations.rentcast_client import RentCastClient, RentCastClientError


def test_recent_sales_uses_recorded_sale_filters(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "comp-1",
                    "formattedAddress": "125 Peachtree St, Atlanta, GA 30303",
                    "lastSalePrice": 280000,
                    "lastSaleDate": "2026-05-01T00:00:00Z",
                }
            ]

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    client = RentCastClient(api_key="test-key")

    records = client.get_recent_sales(
        address="123 Peachtree St, Atlanta, GA 30303",
        property_type="single_family",
        bedrooms=3,
        bathrooms=2,
        square_footage=1800,
        year_built=1980,
    )

    assert records[0]["lastSalePrice"] == 280000
    assert captured["url"] == "https://api.rentcast.io/v1/properties"
    assert captured["headers"] == {
        "Accept": "application/json",
        "X-Api-Key": "test-key",
    }
    assert captured["params"] == {
        "address": "123 Peachtree St, Atlanta, GA 30303",
        "radius": 1,
        "saleDateRange": 365,
        "limit": 50,
        "propertyType": "Single Family",
        "bedrooms": "2:4",
        "bathrooms": "1:3",
        "squareFootage": "1440:2160",
        "yearBuilt": "1955:2005",
    }


def test_value_estimate_error_preserves_provider_diagnostics(
    monkeypatch: MonkeyPatch,
) -> None:
    request = httpx.Request(
        "GET",
        "https://api.rentcast.io/v1/avm/value",
    )
    response = httpx.Response(
        401,
        request=request,
        json={
            "status": 401,
            "error": "billing/subscription-inactive",
            "message": "The API subscription is not active.",
        },
    )

    def fake_get(*_args: object, **_kwargs: object) -> httpx.Response:
        return response

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RentCastClientError) as error:
        RentCastClient(api_key="test-key").get_value_estimate(
            address="123 Peachtree St, Atlanta, GA 30303",
        )

    assert error.value.operation == "value estimate"
    assert error.value.status_code == 401
    assert error.value.error_code == "billing/subscription-inactive"
    assert str(error.value) == (
        "RentCast value estimate failed "
        "(HTTP 401, billing/subscription-inactive): "
        "The API subscription is not active."
    )


def test_invalid_json_is_reported_as_provider_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    request = httpx.Request(
        "GET",
        "https://api.rentcast.io/v1/properties",
    )
    response = httpx.Response(
        200,
        request=request,
        text="<html>temporary provider response</html>",
    )

    def fake_get(*_args: object, **_kwargs: object) -> httpx.Response:
        return response

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(RentCastClientError) as error:
        RentCastClient(api_key="test-key").get_property_record(
            address="123 Peachtree St, Atlanta, GA 30303",
        )

    assert error.value.operation == "property record"
    assert error.value.status_code == 200
    assert str(error.value) == (
        "RentCast property record returned invalid JSON (HTTP 200)."
    )


def test_property_record_uses_normalized_avm_id(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"id": "134-Waterstone-Trl,-Canton,-GA-30114"}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    record = RentCastClient(api_key="test-key").get_property_record(
        address="134 Waterstone Trail, Canton, GA 30114",
        property_id="134-Waterstone-Trl,-Canton,-GA-30114",
    )

    assert record["id"] == "134-Waterstone-Trl,-Canton,-GA-30114"
    assert captured["url"] == (
        "https://api.rentcast.io/v1/properties/"
        "134-Waterstone-Trl%2C-Canton%2C-GA-30114"
    )
    assert captured["params"] == {}


def test_recent_sales_prefers_avm_coordinates(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    RentCastClient(api_key="test-key").get_recent_sales(
        address="134 Waterstone Trail, Canton, GA 30114",
        property_type="single_family",
        bedrooms=4,
        bathrooms=3,
        square_footage=2400,
        year_built=2002,
        latitude=34.245,
        longitude=-84.49,
    )

    params = captured["params"]
    assert isinstance(params, dict)
    assert params["latitude"] == 34.245
    assert params["longitude"] == -84.49
    assert "address" not in params


def test_recent_sales_applies_adaptive_search_tolerances(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    RentCastClient(api_key="test-key").get_recent_sales(
        address="134 Waterstone Trail, Canton, GA 30114",
        property_type="single_family",
        bedrooms=4,
        bathrooms=2.5,
        square_footage=2400,
        year_built=2002,
        radius=0.5,
        days_old=180,
        bedroom_tolerance=0,
        bathroom_tolerance=0.5,
        square_footage_tolerance=0.15,
        year_built_tolerance=15,
    )

    params = captured["params"]
    assert isinstance(params, dict)
    assert params["radius"] == 0.5
    assert params["saleDateRange"] == 180
    assert params["bedrooms"] == "4:4"
    assert params["bathrooms"] == "2:3"
    assert params["squareFootage"] == "2040:2760"
    assert params["yearBuilt"] == "1987:2017"


def test_supporting_sale_listings_are_requested_as_active_context(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return [{"id": "listing-1", "status": "Active", "price": 325000}]

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    listings = RentCastClient(api_key="test-key").get_sale_listings(
        address="123 Peachtree St, Atlanta, GA 30303",
        property_type="single_family",
        bedrooms=3,
        bathrooms=2,
        square_footage=1800,
    )

    assert listings[0]["status"] == "Active"
    assert captured["url"] == "https://api.rentcast.io/v1/listings/sale"
    assert captured["params"] == {
        "address": "123 Peachtree St, Atlanta, GA 30303",
        "radius": 1,
        "status": "Active",
        "daysOld": "1:180",
        "limit": 12,
        "propertyType": "Single Family",
        "bedrooms": "2:4",
        "bathrooms": "1:3",
        "squareFootage": "1350:2250",
    }


def test_sale_market_statistics_request_uses_zip_and_history(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"zipCode": "30303", "saleData": {"medianPrice": 310000}}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    payload = RentCastClient(api_key="test-key").get_market_statistics(
        postal_code="30303",
    )

    assert payload["zipCode"] == "30303"
    assert captured["url"] == "https://api.rentcast.io/v1/markets"
    assert captured["params"] == {
        "zipCode": "30303",
        "dataType": "Sale",
        "historyRange": 12,
    }
