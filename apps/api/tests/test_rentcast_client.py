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
