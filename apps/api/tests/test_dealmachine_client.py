import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.integrations.dealmachine_client import (
    UNDERWRITING_PROPERTY_FIELDS,
    DealMachineClient,
)


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "DEALMACHINE_API_KEY": "dm_sk_live_test",
            "DEALMACHINE_BASE_URL": "https://api.v2.dealmachine.test/v1",
        }
    )


def test_underwriting_property_lookup_excludes_contacts() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "input": {"full_address": "1200 Barton Springs Rd, Austin, TX"},
                        "matched": True,
                        "dm_property_id": "prop_subject",
                        "full_address": "1200 Barton Springs Rd, Austin, TX 78704",
                        "num_bedrooms": 3,
                    }
                ],
                "credits": {
                    "used": 1,
                    "properties": 1,
                    "people": 0,
                    "deduplicated": 0,
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = DealMachineClient(_settings(), client=http_client).lookup_underwriting_property(
            address=" 1200 Barton Springs Rd, Austin, TX "
        )

    assert result.matched is True
    assert result.property is not None
    assert result.property["dm_property_id"] == "prop_subject"
    assert result.credits["people"] == 0
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/enrichment/address"
    assert requests[0].headers["Authorization"] == "Bearer dm_sk_live_test"
    body = json.loads(requests[0].content)
    assert body == {
        "data": [{"full_address": "1200 Barton Springs Rd, Austin, TX"}],
        "fields": UNDERWRITING_PROPERTY_FIELDS,
        "contact_audience": "none",
    }


def test_underwriting_comps_use_subject_credit_endpoint_and_closed_sales_only() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "dm_property_id": "prop_subject",
                        "found": True,
                        "subject": {"display_line_1": "1200 Barton Springs Rd"},
                        "comps": [
                            {
                                "dm_property_id": "prop_comp_1",
                                "type": "sale",
                                "sale_price": 425000,
                                "sale_date": "2026-06-15",
                            },
                            "invalid-row",
                        ],
                        "summary": {"count": 1, "median_price": 425000},
                        "value_estimation": {"estimated_value": 430000},
                        "total_comps_found": 1,
                    }
                ],
                "credits": {"used": 1, "properties": 1, "deduplicated": 0},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = DealMachineClient(_settings(), client=http_client).get_underwriting_comparables(
            property_id="prop_subject",
            radius_miles=0.5,
            timeframe="12months",
            limit=15,
        )

    assert result.found is True
    assert result.subject_property_id == "prop_subject"
    assert result.total_comps_found == 1
    assert result.comparables == [
        {
            "dm_property_id": "prop_comp_1",
            "type": "sale",
            "sale_price": 425000,
            "sale_date": "2026-06-15",
        }
    ]
    assert result.provider_value_estimation == {"estimated_value": 430000}
    assert result.credits["used"] == 1
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/comps"
    assert json.loads(requests[0].content) == {
        "property_ids": ["prop_subject"],
        "location": {"type": "radius", "radius_miles": 0.5},
        "criteria": {
            "timeframe": "12months",
            "limit": 15,
            "sort_by": "match",
            "sort_direction": "desc",
            "include_foreclosures": False,
            "include_active_listings": False,
        },
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"property_id": "not-a-property"}, "beginning with 'prop_'"),
        ({"property_id": "prop_subject", "radius_miles": 4}, "at most 3 miles"),
        ({"property_id": "prop_subject", "limit": 101}, "between 1 and 100"),
    ],
)
def test_underwriting_comps_reject_unsafe_requests(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(500))
    with httpx.Client(transport=transport) as client:
        provider = DealMachineClient(_settings(), client=client)
        with pytest.raises(ValueError, match=message):
            provider.get_underwriting_comparables(**kwargs)  # type: ignore[arg-type]
