from typing import Any

import httpx
from pytest import MonkeyPatch

from app.integrations.rentcast_client import RentCastClient


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
