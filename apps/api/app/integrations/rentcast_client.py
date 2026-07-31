from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class RentCastClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        operation: str,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.error_code = error_code


@dataclass(frozen=True)
class RentCastValueEstimate:
    price: int | None
    price_range_low: int | None
    price_range_high: int | None
    subject_property: dict[str, Any]
    comparables: list[dict[str, Any]]
    raw_response: dict[str, Any]


@dataclass(frozen=True)
class RentCastRentEstimate:
    rent: int | None
    rent_range_low: int | None
    rent_range_high: int | None
    comparables: list[dict[str, Any]]
    raw_response: dict[str, Any]


class RentCastClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.rentcast.io/v1",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_value_estimate(
        self,
        *,
        address: str,
        property_type: str | None = None,
        max_radius: float = 5,
        days_old: int = 270,
        comp_count: int = 20,
    ) -> RentCastValueEstimate:
        params: dict[str, str | int | float | bool] = {
            "address": address,
            "maxRadius": max_radius,
            "daysOld": days_old,
            "compCount": comp_count,
            "lookupSubjectAttributes": True,
        }
        mapped_property_type = map_property_type(property_type)
        if mapped_property_type:
            params["propertyType"] = mapped_property_type

        try:
            response = httpx.get(
                f"{self.base_url}/avm/value",
                headers={
                    "Accept": "application/json",
                    "X-Api-Key": self.api_key,
                },
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise rentcast_http_error(exc.response, operation="value estimate") from exc
        except httpx.HTTPError as exc:
            raise RentCastClientError(
                f"RentCast value estimate request failed: {exc}",
                operation="value estimate",
            ) from exc

        payload = parse_rentcast_json(response, operation="value estimate")
        if not isinstance(payload, dict):
            raise RentCastClientError(
                "RentCast value estimate returned an unexpected response shape.",
                operation="value estimate",
                status_code=response.status_code,
            )

        return value_estimate_from_payload(payload)

    def get_property_record(
        self,
        *,
        address: str,
        property_id: str | None = None,
    ) -> dict[str, Any]:
        if property_id:
            payload = self._get_json(
                f"/properties/{quote(property_id, safe='')}",
                {},
                operation="property record",
            )
            return payload
        records = self._get_property_records(
            {"address": address, "limit": 1},
            operation="property record",
        )
        return records[0] if records else {}

    def get_recent_sales(
        self,
        *,
        address: str,
        property_type: str | None,
        bedrooms: float | None,
        bathrooms: float | None,
        square_footage: int | None,
        year_built: int | None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius: float = 1,
        days_old: int = 365,
        limit: int = 50,
        bedroom_tolerance: float | None = 1,
        bathroom_tolerance: float | None = 1,
        square_footage_tolerance: float | None = 0.2,
        year_built_tolerance: int | None = 25,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int | float | bool] = {
            "radius": radius,
            "saleDateRange": days_old,
            "limit": limit,
        }
        if latitude is not None and longitude is not None:
            params["latitude"] = latitude
            params["longitude"] = longitude
        else:
            params["address"] = address
        mapped_property_type = map_property_type(property_type)
        if mapped_property_type:
            params["propertyType"] = mapped_property_type
        if bedrooms is not None and bedroom_tolerance is not None:
            params["bedrooms"] = numeric_range(
                bedrooms - bedroom_tolerance,
                bedrooms + bedroom_tolerance,
            )
        if bathrooms is not None and bathroom_tolerance is not None:
            params["bathrooms"] = numeric_range(
                bathrooms - bathroom_tolerance,
                bathrooms + bathroom_tolerance,
            )
        if (
            square_footage is not None
            and square_footage > 0
            and square_footage_tolerance is not None
        ):
            params["squareFootage"] = numeric_range(
                round(square_footage * (1 - square_footage_tolerance)),
                round(square_footage * (1 + square_footage_tolerance)),
            )
        if (
            year_built is not None
            and year_built > 0
            and year_built_tolerance is not None
        ):
            params["yearBuilt"] = numeric_range(
                max(1700, year_built - year_built_tolerance),
                year_built + year_built_tolerance,
            )
        return self._get_property_records(params, operation="recent sales")

    def get_rent_estimate(
        self,
        *,
        address: str,
        property_type: str | None = None,
    ) -> RentCastRentEstimate:
        params: dict[str, str | int | float | bool] = {
            "address": address,
            "lookupSubjectAttributes": True,
        }
        mapped_property_type = map_property_type(property_type)
        if mapped_property_type:
            params["propertyType"] = mapped_property_type
        payload = self._get_json(
            "/avm/rent/long-term",
            params,
            operation="rent estimate",
        )
        return rent_estimate_from_payload(payload)

    def _get_property_records(
        self,
        params: dict[str, str | int | float | bool],
        *,
        operation: str,
    ) -> list[dict[str, Any]]:
        payload = self._get_json_value("/properties", params, operation=operation)
        if not isinstance(payload, list):
            raise RentCastClientError(
                f"RentCast {operation} returned an unexpected response shape.",
                operation=operation,
            )
        return [record for record in payload if isinstance(record, dict)]

    def _get_json(
        self,
        path: str,
        params: dict[str, str | int | float | bool],
        *,
        operation: str,
    ) -> dict[str, Any]:
        payload = self._get_json_value(path, params, operation=operation)
        if not isinstance(payload, dict):
            raise RentCastClientError(
                f"RentCast {operation} returned an unexpected response shape.",
                operation=operation,
            )
        return payload

    def _get_json_value(
        self,
        path: str,
        params: dict[str, str | int | float | bool],
        *,
        operation: str,
    ) -> Any:
        try:
            response = httpx.get(
                f"{self.base_url}{path}",
                headers={
                    "Accept": "application/json",
                    "X-Api-Key": self.api_key,
                },
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise rentcast_http_error(exc.response, operation=operation) from exc
        except httpx.HTTPError as exc:
            raise RentCastClientError(
                f"RentCast {operation} request failed: {exc}",
                operation=operation,
            ) from exc
        return parse_rentcast_json(response, operation=operation)


def parse_rentcast_error(response: httpx.Response) -> str:
    message, _error_code = rentcast_error_details(response)
    return message or f"RentCast returned HTTP {response.status_code}."


def rentcast_http_error(
    response: httpx.Response,
    *,
    operation: str,
) -> RentCastClientError:
    provider_message, error_code = rentcast_error_details(response)
    qualifiers = [f"HTTP {response.status_code}"]
    if error_code:
        qualifiers.append(error_code)
    message = f"RentCast {operation} failed ({', '.join(qualifiers)})"
    if provider_message:
        message = f"{message}: {provider_message}"
    return RentCastClientError(
        message,
        operation=operation,
        status_code=response.status_code,
        error_code=error_code,
    )


def rentcast_error_details(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        error_code = payload.get("error")
        normalized_error_code = (
            error_code.strip()
            if isinstance(error_code, str) and error_code.strip()
            else None
        )
        for key in ("message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), normalized_error_code
        return None, normalized_error_code
    return None, None


def parse_rentcast_json(response: httpx.Response, *, operation: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise RentCastClientError(
            f"RentCast {operation} returned invalid JSON (HTTP {response.status_code}).",
            operation=operation,
            status_code=response.status_code,
        ) from exc


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def value_estimate_from_payload(payload: dict[str, Any]) -> RentCastValueEstimate:
    subject_property = payload.get("subjectProperty")
    comparables = payload.get("comparables")
    return RentCastValueEstimate(
        price=optional_int(payload.get("price")),
        price_range_low=optional_int(payload.get("priceRangeLow")),
        price_range_high=optional_int(payload.get("priceRangeHigh")),
        subject_property=subject_property if isinstance(subject_property, dict) else {},
        comparables=comparables if isinstance(comparables, list) else [],
        raw_response=payload,
    )


def rent_estimate_from_payload(payload: dict[str, Any]) -> RentCastRentEstimate:
    comparables = payload.get("comparables")
    return RentCastRentEstimate(
        rent=optional_int(payload.get("rent")),
        rent_range_low=optional_int(payload.get("rentRangeLow")),
        rent_range_high=optional_int(payload.get("rentRangeHigh")),
        comparables=comparables if isinstance(comparables, list) else [],
        raw_response=payload,
    )


def map_property_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "single_family": "Single Family",
        "sfh": "Single Family",
        "condo": "Condo",
        "condominium": "Condo",
        "townhouse": "Townhouse",
        "townhome": "Townhouse",
        "manufactured": "Manufactured",
        "mobile_home": "Manufactured",
        "multi_family": "Multi-Family",
        "multifamily": "Multi-Family",
        "apartment": "Apartment",
        "land": "Land",
    }.get(normalized)


def numeric_range(low: float | int, high: float | int) -> str:
    normalized_low = max(0, low)
    low_value = int(normalized_low) if float(normalized_low).is_integer() else normalized_low
    high_value = int(high) if float(high).is_integer() else high
    return f"{low_value}:{high_value}"
