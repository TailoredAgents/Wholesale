from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from app.core.config import Settings


class DealMachineError(RuntimeError):
    pass


@dataclass(frozen=True)
class DealMachinePropertyLookup:
    matched: bool
    property: dict[str, Any] | None
    credits: dict[str, Any]
    match_warning: dict[str, Any] | None
    match_failure: dict[str, Any] | None
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class DealMachineComparableSearch:
    subject_property_id: str
    found: bool
    subject_property: dict[str, Any]
    comparables: list[dict[str, Any]]
    summary: dict[str, Any]
    provider_value_estimation: dict[str, Any]
    total_comps_found: int
    credits: dict[str, Any]
    request: dict[str, Any]
    raw_response: dict[str, Any]


UNDERWRITING_PROPERTY_FIELDS = [
    "estimated_value",
    "estimated_equity_amount",
    "estimated_equity_percentage",
    "num_bedrooms",
    "num_bathrooms",
    "living_area_sqft",
    "year_built",
    "num_units",
    "num_buildings",
    "building_style",
    "stories",
    "property_construction_type",
    "property_type",
    "property_class",
    "school_district_name",
    "num_mortgages",
    "estimated_loan_to_value_percentage",
    "total_estimated_loan_balance",
    "mortgage_1_loan_balance",
    "mortgage_1_loan_interest_rate",
    "mortgage_1_loan_type",
    "mortgage_1_loan_due_date",
    "mortgage_1_loan_recording_date",
    "market_status",
    "mls_current_listing_price",
    "mls_days_on_market",
    "mls_last_initial_listing_date",
    "last_sale_date",
    "last_sale_price",
    "last_sale_doc_type",
    "tax_amount",
    "tax_delinquent_year",
    "tax_year",
    "assessed_total_value",
    "assessed_improvement_value",
    "assessed_land_value",
    "tax_assessment_year",
    "num_total_active_liens",
    "num_total_open_liens",
    "hoa_1_fee_amount",
    "lot_size_acres",
    "lot_size_frontage_feet",
    "lot_size_depth_feet",
    "zoning",
    "parcel_number_raw",
    "legal_description",
    "lot_number",
    "municipality_name",
    "subdivision_name",
    "pool",
    "garage_type",
    "basement",
    "patio",
    "porch",
    "driveway",
    "air_conditioning",
    "heating_type",
    "heating_fuel",
    "sewer",
    "water",
    "has_fireplaces",
    "exterior_walls",
    "roof_type",
    "roof_cover",
    "floor_cover",
    "building_condition",
    "building_quality",
    "flood_zone",
]
COMPARABLE_TIMEFRAMES = {"3months", "6months", "12months", "all"}
COMPARABLE_SORT_FIELDS = {"distance", "price", "date", "match"}


class DealMachineClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.dealmachine_api_key:
            raise DealMachineError("DealMachine API credentials are not configured.")
        self.base_url = settings.dealmachine_base_url.rstrip("/")
        self.api_key = settings.dealmachine_api_key
        self.client = client or httpx.Client(timeout=settings.dealmachine_request_timeout_seconds)

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", "/properties/search", json=request)
        if not isinstance(payload.get("data"), list):
            raise DealMachineError("DealMachine returned an unexpected search response.")
        return payload

    def estimate_property_search(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/properties/search",
            json={**request, "estimate_cost": True},
        )
        if not isinstance(payload.get("estimated_credits"), dict):
            raise DealMachineError("DealMachine returned an unexpected cost estimate.")
        return payload

    def get_usage(self) -> dict[str, Any]:
        payload = self._request("GET", "/usage")
        if not isinstance(payload.get("plan"), dict) or not isinstance(
            payload.get("credits"), dict
        ):
            raise DealMachineError("DealMachine returned an unexpected usage response.")
        return payload

    def list_property_filters(self) -> list[object]:
        payload = self._request(
            "GET",
            "/filters",
            params={
                "source_type": "properties",
                "search": "Property Type",
                "per_page": 250,
            },
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise DealMachineError("DealMachine returned unexpected filter metadata.")
        return data

    def lookup_underwriting_property(self, *, address: str) -> DealMachinePropertyLookup:
        """Resolve one subject address without purchasing owner/contact information."""
        normalized_address = address.strip()
        if not normalized_address:
            raise ValueError("A property address is required for DealMachine lookup.")
        payload = self._request(
            "POST",
            "/enrichment/address",
            json={
                "data": [{"full_address": normalized_address}],
                "fields": UNDERWRITING_PROPERTY_FIELDS,
                "contact_audience": "none",
            },
            operation="underwriting property lookup",
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise DealMachineError(
                "DealMachine returned an unexpected underwriting property response."
            )
        record = data[0]
        matched = record.get("matched") is True
        credits = payload.get("credits")
        warning = record.get("match_warning")
        failure = record.get("match_failure")
        return DealMachinePropertyLookup(
            matched=matched,
            property=record if matched else None,
            credits=credits if isinstance(credits, dict) else {},
            match_warning=warning if isinstance(warning, dict) else None,
            match_failure=failure if isinstance(failure, dict) else None,
            raw_response=payload,
        )

    def get_underwriting_comparables(
        self,
        *,
        property_id: str,
        radius_miles: float = 1,
        timeframe: Literal["3months", "6months", "12months", "all"] = "6months",
        limit: int = 25,
        sort_by: Literal["distance", "price", "date", "match"] = "match",
        sort_direction: Literal["asc", "desc"] = "desc",
    ) -> DealMachineComparableSearch:
        """Fetch DealMachine's closed-sale comp candidates for one known subject.

        DealMachine's documented comp endpoint costs one property-data credit for the
        subject; the comparable rows themselves are free. Active listings and foreclosure
        transfers are explicitly excluded because this method feeds closed-sale evidence.
        """
        normalized_property_id = property_id.strip()
        if not normalized_property_id.startswith("prop_"):
            raise ValueError("A DealMachine property ID beginning with 'prop_' is required.")
        if not 0 < radius_miles <= 3:
            raise ValueError("DealMachine comp radius must be greater than 0 and at most 3 miles.")
        if timeframe not in COMPARABLE_TIMEFRAMES:
            raise ValueError("DealMachine comp timeframe is not supported.")
        if not 1 <= limit <= 100:
            raise ValueError("DealMachine comp limit must be between 1 and 100.")
        if sort_by not in COMPARABLE_SORT_FIELDS:
            raise ValueError("DealMachine comp sort field is not supported.")
        if sort_direction not in {"asc", "desc"}:
            raise ValueError("DealMachine comp sort direction is not supported.")

        request: dict[str, Any] = {
            "property_ids": [normalized_property_id],
            "location": {"type": "radius", "radius_miles": radius_miles},
            "criteria": {
                "timeframe": timeframe,
                "limit": limit,
                "sort_by": sort_by,
                "sort_direction": sort_direction,
                "include_foreclosures": False,
                "include_active_listings": False,
            },
        }
        payload = self._request(
            "POST",
            "/comps",
            json=request,
            operation="underwriting comparable search",
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise DealMachineError(
                "DealMachine returned an unexpected underwriting comparable response."
            )
        result = data[0]
        response_property_id = result.get("dm_property_id")
        if response_property_id != normalized_property_id:
            raise DealMachineError(
                "DealMachine returned comparables for an unexpected subject property."
            )
        raw_comparables = result.get("comps")
        comparables = (
            [item for item in raw_comparables if isinstance(item, dict)]
            if isinstance(raw_comparables, list)
            else []
        )
        subject = result.get("subject")
        summary = result.get("summary")
        value_estimation = result.get("value_estimation")
        credits = payload.get("credits")
        total_comps_found = result.get("total_comps_found")
        return DealMachineComparableSearch(
            subject_property_id=normalized_property_id,
            found=result.get("found") is True,
            subject_property=subject if isinstance(subject, dict) else {},
            comparables=comparables,
            summary=summary if isinstance(summary, dict) else {},
            provider_value_estimation=(
                value_estimation if isinstance(value_estimation, dict) else {}
            ),
            total_comps_found=(
                total_comps_found
                if isinstance(total_comps_found, int) and not isinstance(total_comps_found, bool)
                else len(comparables)
            ),
            credits=credits if isinstance(credits, dict) else {},
            request=request,
            raw_response=payload,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str | int | float | bool | None] | None = None,
        operation: str = "buyer search",
    ) -> dict[str, Any]:
        try:
            response = self.client.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=json,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise DealMachineError(_error_message(exc.response)) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise DealMachineError(f"DealMachine could not complete the {operation}.") from exc
        if not isinstance(payload, dict):
            raise DealMachineError("DealMachine returned an unexpected response.")
        return payload


def get_dealmachine_image(
    image_url: str,
    *,
    timeout_seconds: float = 20,
) -> tuple[bytes, str]:
    if not is_dealmachine_image_url(image_url):
        raise DealMachineError("DealMachine returned an invalid property image URL.")
    try:
        response = httpx.get(image_url, timeout=timeout_seconds, follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DealMachineError("DealMachine property imagery is unavailable.") from exc
    content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
    if not content_type.startswith("image/"):
        raise DealMachineError("DealMachine returned a non-image property response.")
    return response.content, content_type


def is_dealmachine_image_url(image_url: str) -> bool:
    parsed = urlparse(image_url)
    return parsed.scheme == "https" and parsed.hostname == "img.dealmachine.com"


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        request_id = error.get("request_id")
        suffix = f" (request {request_id})" if isinstance(request_id, str) else ""
        return f"DealMachine request failed: {error['message']}{suffix}"
    if response.status_code in {401, 403}:
        return "DealMachine rejected the API key or account permissions."
    if response.status_code == 429:
        return "DealMachine rate-limited the request. Try again shortly."
    return f"DealMachine request failed with status {response.status_code}."
