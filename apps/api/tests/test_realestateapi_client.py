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


def test_address_autocomplete_requests_full_addresses_and_prefers_georgia() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/AutoComplete"
        assert request.headers["x-api-key"] == "re_test_secret"
        assert request.content == b'{"search":"313 Vineyard","search_types":["A"]}'
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "data": [
                    {
                        "id": "out-of-state",
                        "searchType": "A",
                        "title": "313 Vineyard Ave, Charlotte, NC, 28202",
                        "address": "313 Vineyard Ave, Charlotte, NC, 28202",
                        "street": "Vineyard Ave",
                        "city": "Charlotte",
                        "state": "NC",
                        "zip": "28202",
                        "latitude": 35.2271,
                        "owner": {"name": "Must not be exposed"},
                    },
                    {
                        "id": 12345,
                        "searchType": "A",
                        "title": "313 Vineyard Dr, Dallas, GA, 30132",
                        "address": "313 Vineyard Dr, Dallas, GA, 30132",
                        "street": "Vineyard Dr",
                        "city": "Dallas",
                        "state": "ga",
                        "zip": "30132",
                    },
                    {
                        "id": "not-an-address",
                        "searchType": "C",
                        "title": "Dallas, GA",
                        "city": "Dallas",
                        "state": "GA",
                        "zip": "30132",
                    },
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        suggestions = RealEstateAPIClient(_settings(), client=client).autocomplete_addresses(
            "  313   Vineyard  ",
            max_results=2,
        )

    assert [suggestion.provider_id for suggestion in suggestions] == ["12345", "out-of-state"]
    assert suggestions[0].street_address == "313 Vineyard Dr"
    assert suggestions[0].state == "GA"
    assert suggestions[1].state == "NC"
    assert set(vars(suggestions[0])) == {
        "provider_id",
        "label",
        "street_address",
        "city",
        "state",
        "postal_code",
    }


def test_address_autocomplete_normalizes_nested_shape_and_discards_unsafe_records() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "statusCode": 200,
                "data": {
                    "results": [
                        {
                            "propertyId": "nested-1",
                            "search_type": "A",
                            "title": "55 Auburn Ave, Atlanta, GA 30303",
                            "address": {
                                "address": "55 Auburn Ave, Atlanta, GA 30303",
                                "house": "55",
                                "street": "Auburn Ave",
                                "city": "Atlanta",
                                "state": "GA",
                                "postalCode": "30303",
                                "county": "Fulton",
                            },
                            "api_key": "provider-secret-that-must-not-leak",
                        },
                        {
                            "id": "incomplete",
                            "searchType": "A",
                            "title": "Auburn Ave, Atlanta, GA",
                            "street": "Auburn Ave",
                            "city": "Atlanta",
                            "state": "GA",
                        },
                        {
                            "id": "oversized",
                            "searchType": "A",
                            "title": "x" * 301,
                            "address": "x" * 301,
                            "street": "1 Main St",
                            "city": "Atlanta",
                            "state": "GA",
                            "zip": "30303",
                        },
                    ]
                },
            },
        )
    )

    with httpx.Client(transport=transport) as client:
        suggestions = RealEstateAPIClient(_settings(), client=client).autocomplete_addresses(
            "55 Auburn"
        )

    assert len(suggestions) == 2
    assert suggestions[0].provider_id == "nested-1"
    assert suggestions[0].street_address == "55 Auburn Ave"
    assert "provider-secret" not in repr(suggestions[0])
    assert suggestions[1].label == "1 Main St, Atlanta, GA 30303"
    assert "x" * 50 not in repr(suggestions[1])


def test_address_autocomplete_provider_errors_do_not_expose_credentials() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            429,
            json={"statusMessage": "Rate limit reached"},
        )
    )
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(RealEstateAPIError, match="HTTP 429") as caught,
    ):
        RealEstateAPIClient(_settings(), client=client).autocomplete_addresses("55 Auburn")

    assert "re_test_secret" not in str(caught.value)


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
