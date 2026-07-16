from dataclasses import dataclass
from typing import Any

import httpx


class RentCastClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class RentCastValueEstimate:
    price: int | None
    price_range_low: int | None
    price_range_high: int | None
    subject_property: dict[str, Any]
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
            raise RentCastClientError(parse_rentcast_error(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise RentCastClientError(f"RentCast request failed: {exc}") from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise RentCastClientError("RentCast returned an unexpected response shape.")

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


def parse_rentcast_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return f"RentCast returned HTTP {response.status_code}."


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
