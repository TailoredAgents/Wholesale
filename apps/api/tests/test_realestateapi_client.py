import httpx
import pytest

from app.core.config import Settings
from app.integrations.realestateapi_client import (
    RealEstateAPIClient,
    RealEstateAPIError,
    is_realestateapi_image_url,
    realestateapi_primary_image_url,
)


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "REALESTATEAPI_API_KEY": "re_test_secret",
            "REALESTATEAPI_BASE_URL": "https://api.realestateapi.test",
        }
    )


def test_property_detail_requests_exact_match_and_standard_comps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/PropertyDetail"
        assert request.headers["x-api-key"] == "re_test_secret"
        assert request.content == (
            b'{"address":"123 Main St, Atlanta, GA 30303","exact_match":true,"comps":true}'
        )
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "data": {
                    "id": 123,
                    "estimatedValue": 400_000,
                    "comps": [{"id": 456, "lastSaleAmount": 390_000}],
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = RealEstateAPIClient(_settings(), client=client).get_property_detail(
            address="123 Main St, Atlanta, GA 30303"
        )

    assert result.found is True
    assert result.property["estimatedValue"] == 400_000
    assert result.comparables[0]["id"] == 456


def test_property_detail_supports_county_scoped_apn_without_residential_comps() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/PropertyDetail"
        assert request.headers["x-api-key"] == "re_test_secret"
        assert request.content == (
            b'{"apn":"0012-03-A.004","county":"Fulton County","state":"GA",'
            b'"exact_match":true,"comps":false}'
        )
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "data": {
                    "id": "land-parcel-1",
                    "lotInfo": {"apn": "001203A004", "lotAcres": 3.25},
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = RealEstateAPIClient(_settings(), client=client).get_property_detail(
            apn="0012-03-A.004",
            county="Fulton County",
            state="ga",
            include_comps=False,
        )

    assert result.found is True
    assert result.property["lotInfo"]["lotAcres"] == 3.25
    assert result.comparables == []


def test_property_detail_rejects_ambiguous_or_incomplete_lookup_identity() -> None:
    client = RealEstateAPIClient(_settings())

    with pytest.raises(RealEstateAPIError, match="one lookup identity"):
        client.get_property_detail(
            address="123 Main St, Atlanta, GA 30303",
            apn="001-002",
            county="Fulton",
            state="GA",
        )
    with pytest.raises(RealEstateAPIError, match="APN with county and state"):
        client.get_property_detail(apn="001-002", county="Fulton")


def test_land_property_search_sends_closed_land_sale_filters_and_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/PropertySearch"
        assert request.headers["x-api-key"] == "re_test_secret"
        assert request.content == (
            b'{"count":false,"size":25,"resultIndex":0,"property_type":"LAND",'
            b'"last_sale_arms_length":true,"last_sale_date_min":"2023-08-08",'
            b'"lot_size_min":43560,"lot_size_max":435600,"state":"GA",'
            b'"latitude":34.4817,"longitude":-84.371,"radius":25}'
        )
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "resultCount": 2,
                "responseCount": 2,
                "data": {
                    "results": [
                        {"id": "sale-1", "lastSaleAmount": 100_000},
                        {"id": "sale-2", "lastSaleAmount": 125_000},
                    ]
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = RealEstateAPIClient(_settings(), client=client).search_land_sales(
            state="ga",
            county="Pickens",
            latitude=34.4817,
            longitude=-84.371,
            radius_miles=25,
            sale_date_min="2023-08-08",
            lot_size_min=43_560,
            lot_size_max=435_600,
            size=25,
        )

    assert [record["id"] for record in result.properties] == ["sale-1", "sale-2"]
    assert result.result_count == 2
    assert result.response_count == 2


def test_property_detail_treats_payload_404_as_no_match() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"statusCode": 404, "statusMessage": "Not found"},
        )
    )
    with httpx.Client(transport=transport) as client:
        result = RealEstateAPIClient(_settings(), client=client).get_property_detail(
            address="Missing address"
        )
    assert result.found is False
    assert result.status_code == 404


def test_property_detail_errors_do_not_expose_api_key() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(401, json={"statusMessage": "Invalid key"})
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(RealEstateAPIError, match="HTTP 401") as caught,
    ):
        RealEstateAPIClient(_settings(), client=client).get_property_detail(address="123 Main St")
    assert "re_test_secret" not in str(caught.value)


def test_listing_image_requires_the_documented_https_cdn() -> None:
    valid = "https://imagecdn.realty.dev/mls_photos/123/1.jpg"
    assert realestateapi_primary_image_url({"media": {"primaryListingImageUrl": valid}}) == valid
    assert is_realestateapi_image_url(valid) is True
    assert is_realestateapi_image_url("http://imagecdn.realty.dev/1.jpg") is False
    assert is_realestateapi_image_url("https://example.com/1.jpg") is False
    assert realestateapi_primary_image_url({"media": {"photosCount": "0"}}) is None
