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
            b'{"address":"123 Main St, Atlanta, GA 30303",'
            b'"exact_match":true,"comps":true}'
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
        RealEstateAPIClient(_settings(), client=client).get_property_detail(
            address="123 Main St"
        )
    assert "re_test_secret" not in str(caught.value)


def test_listing_image_requires_the_documented_https_cdn() -> None:
    valid = "https://imagecdn.realty.dev/mls_photos/123/1.jpg"
    assert realestateapi_primary_image_url(
        {"media": {"primaryListingImageUrl": valid}}
    ) == valid
    assert is_realestateapi_image_url(valid) is True
    assert is_realestateapi_image_url("http://imagecdn.realty.dev/1.jpg") is False
    assert is_realestateapi_image_url("https://example.com/1.jpg") is False
    assert realestateapi_primary_image_url({"media": {"photosCount": "0"}}) is None
