from __future__ import annotations

import math
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.domain.assets import parcel_identity_key

SQUARE_FEET_PER_ACRE = Decimal("43560")
LAND_SEARCH_TIERS: dict[str, dict[str, Decimal | int]] = {
    "preferred": {
        "radius_miles": Decimal("10"),
        "months": 24,
        "minimum_ratio": Decimal("0.50"),
        "maximum_ratio": Decimal("2.00"),
    },
    "expanded": {
        "radius_miles": Decimal("25"),
        "months": 36,
        "minimum_ratio": Decimal("0.33"),
        "maximum_ratio": Decimal("3.00"),
    },
    "extended": {
        "radius_miles": Decimal("50"),
        "months": 60,
        "minimum_ratio": Decimal("0.20"),
        "maximum_ratio": Decimal("5.00"),
    },
}


def land_search_bounds(
    *,
    subject_acres: Decimal,
    tier: str,
    today: date,
) -> dict[str, Any]:
    policy = LAND_SEARCH_TIERS[tier]
    minimum_ratio = Decimal(str(policy["minimum_ratio"]))
    maximum_ratio = Decimal(str(policy["maximum_ratio"]))
    minimum_square_feet = max(
        1,
        int((subject_acres * minimum_ratio * SQUARE_FEET_PER_ACRE).to_integral_value()),
    )
    maximum_square_feet = max(
        minimum_square_feet,
        int((subject_acres * maximum_ratio * SQUARE_FEET_PER_ACRE).to_integral_value()),
    )
    months = int(policy["months"])
    year = today.year
    month = today.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(today.day, days_in_month(year, month))
    return {
        "tier": tier,
        "radius_miles": float(policy["radius_miles"]),
        "months": months,
        "sale_date_min": date(year, month, day).isoformat(),
        "lot_size_min": minimum_square_feet,
        "lot_size_max": maximum_square_feet,
        "minimum_ratio": float(minimum_ratio),
        "maximum_ratio": float(maximum_ratio),
    }


def normalize_realestateapi_land_sale(
    record: dict[str, Any],
    *,
    subject_acres: Decimal,
    subject_lot_count: int | None,
    valuation_basis: str,
    subject_latitude: float | None,
    subject_longitude: float | None,
    today: date,
) -> dict[str, Any]:
    address = address_values(record)
    lot_info = dictionary(record.get("lotInfo"))
    property_info = dictionary(record.get("propertyInfo"))
    property_address = dictionary(property_info.get("address"))
    parcel_id = string_value(lot_info.get("apn") or lot_info.get("apnUnformatted")) or string_value(
        record.get("apn")
    )
    county = string_value(
        record.get("county") or address.get("county") or property_address.get("county")
    )
    state = string_value(
        record.get("state") or address.get("state") or property_address.get("state")
    )
    provider_id = string_value(record.get("id") or record.get("propertyId"))
    formatted_address = formatted_address_value(record, address, property_address)
    sale_price_dollars = decimal_value(
        first_value(
            record,
            "latestArmsLengthSaleAmount",
            "lastSaleAmount",
            "lastSalePrice",
            "saleAmount",
        )
    )
    sale_date_value = string_value(
        first_value(
            record,
            "latestArmsLengthSaleDate",
            "lastSaleDate",
            "saleDate",
        )
    )
    sale_date = parse_date(sale_date_value)
    lot_square_feet = integer_value(
        record.get("lotSquareFeet")
        or lot_info.get("lotSquareFeet")
        or record.get("lotSizeSquareFeet")
    )
    acres = (
        Decimal(lot_square_feet) / SQUARE_FEET_PER_ACRE
        if lot_square_feet and lot_square_feet > 0
        else decimal_value(lot_info.get("lotAcres") or record.get("lotAcres"))
    )
    lot_count = integer_value(
        lot_info.get("lotCount") or record.get("lotCount") or record.get("lotsCount")
    )
    latitude = float_value(record.get("latitude") or property_info.get("latitude"))
    longitude = float_value(record.get("longitude") or property_info.get("longitude"))
    distance = None
    if (
        subject_latitude is not None
        and subject_longitude is not None
        and latitude is not None
        and longitude is not None
    ):
        distance = haversine_miles(
            subject_latitude,
            subject_longitude,
            latitude,
            longitude,
        )
    days_old = (today - sale_date).days if sale_date else None
    acreage_ratio = acres / subject_acres if acres and subject_acres > 0 else None
    sale_price_cents = money_to_cents(sale_price_dollars)
    price_per_acre_cents = (
        round_decimal_to_int(Decimal(sale_price_cents) / acres)
        if sale_price_cents is not None and acres and acres > 0
        else None
    )
    price_per_lot_cents = (
        round_decimal_to_int(Decimal(sale_price_cents) / Decimal(lot_count))
        if sale_price_cents is not None and lot_count and lot_count > 0
        else None
    )
    unit_price = (
        price_per_lot_cents if valuation_basis == "per_lot" else price_per_acre_cents
    )
    subject_units = (
        Decimal(subject_lot_count or 0)
        if valuation_basis == "per_lot"
        else subject_acres
    )
    indication = (
        round_decimal_to_int(Decimal(unit_price) * subject_units)
        if unit_price is not None and subject_units > 0
        else None
    )
    evidence_tier = classify_evidence_tier(
        distance_miles=distance,
        days_old=days_old,
        acreage_ratio=acreage_ratio,
    )
    property_type = string_value(record.get("propertyType") or property_info.get("propertyType"))
    property_use = string_value(
        record.get("propertyUse")
        or record.get("landUse")
        or lot_info.get("landUse")
        or property_info.get("propertyUse")
    )
    zoning = string_value(record.get("zoning") or lot_info.get("zoning"))
    key = (
        parcel_identity_key(parcel_id, county=county, state=state)
        or (f"provider:{provider_id}" if provider_id else None)
        or (f"address:{formatted_address.lower()}" if formatted_address else "unidentified")
    )
    return {
        "key": key,
        "provider_id": provider_id,
        "formatted_address": formatted_address,
        "parcel_id": parcel_id,
        "county": county,
        "state": state.upper() if state else None,
        "property_type": property_type,
        "property_use": property_use,
        "zoning": zoning,
        "sale_date": sale_date.isoformat() if sale_date else sale_date_value,
        "sale_price_cents": sale_price_cents,
        "lot_square_feet": lot_square_feet,
        "acres": float(acres.quantize(Decimal("0.0001"))) if acres else None,
        "lot_count": lot_count,
        "price_per_acre_cents": price_per_acre_cents,
        "price_per_lot_cents": price_per_lot_cents,
        "adjustment_factor": 1.0,
        "adjusted_unit_price_cents": unit_price,
        "subject_indication_cents": indication,
        "distance_miles": round(distance, 2) if distance is not None else None,
        "days_old": days_old,
        "acreage_ratio": round(float(acreage_ratio), 4) if acreage_ratio else None,
        "evidence_tier": evidence_tier,
        "score": evidence_score(
            evidence_tier=evidence_tier,
            distance_miles=distance,
            days_old=days_old,
            acreage_ratio=acreage_ratio,
            property_use=property_use,
        ),
        "weight": 0.0,
        "selection_status": "rejected",
        "selection_reason": "Candidate has not been evaluated.",
        "source": "realestateapi",
        "arms_length_evidence": "provider_search_filter:last_sale_arms_length=true",
        "latitude": latitude,
        "longitude": longitude,
    }


def evaluate_land_sales(
    records: list[dict[str, Any]],
    *,
    subject_parcel_id: str | None,
    subject_county: str | None,
    subject_state: str,
    subject_use: str | None,
    selected_keys: set[str] | None,
    maximum_selected: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subject_key = parcel_identity_key(
        subject_parcel_id,
        county=subject_county,
        state=subject_state,
    )
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    subject_use_group = land_use_group(subject_use)
    for record in records:
        item = dict(record)
        key = str(item.get("key") or "unidentified")
        reason = eligibility_failure(
            item,
            subject_key=subject_key,
            subject_use_group=subject_use_group,
        )
        if reason is None and key in seen:
            reason = "Duplicate comparable identity."
        if reason is None and selected_keys is not None and key not in selected_keys:
            reason = "Excluded during human comparable review."
        if reason is not None:
            item["selection_status"] = "rejected"
            item["selection_reason"] = reason
            rejected.append(item)
            continue
        seen.add(key)
        eligible.append(item)
    eligible.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            int(item.get("days_old") or 999999),
            str(item.get("key") or ""),
        ),
    )
    # The first sort field is negative, so ascending preserves highest score first.
    selected = eligible[:maximum_selected]
    overflow = eligible[maximum_selected:]
    total_score = sum(max(1, int(item.get("score") or 0)) for item in selected)
    for item in selected:
        item["selection_status"] = "selected"
        item["selection_reason"] = "Eligible closed Land sale selected by deterministic score."
        item["weight"] = round(max(1, int(item.get("score") or 0)) / total_score, 6)
    for item in overflow:
        item["selection_status"] = "rejected"
        item["selection_reason"] = "Eligible evidence ranked outside the eight-sale limit."
    rejected.extend(overflow)
    return selected, rejected


def eligibility_failure(
    item: dict[str, Any],
    *,
    subject_key: str | None,
    subject_use_group: str,
) -> str | None:
    property_type = str(item.get("property_type") or "").strip().upper()
    if "LAND" not in property_type:
        return "Property type is not Land."
    if item.get("sale_price_cents") is None or int(item["sale_price_cents"]) <= 0:
        return "A positive closed-sale price is missing."
    if not item.get("sale_date") or item.get("days_old") is None:
        return "A valid closed-sale date is missing."
    if item.get("subject_indication_cents") is None:
        return "The comparable lacks the unit evidence required by this valuation basis."
    if item.get("evidence_tier") is None:
        return "The sale falls outside the supported Land evidence tiers."
    if subject_key and item.get("key") == subject_key:
        return "The subject parcel cannot be used as its own comparable."
    comparable_use_group = land_use_group(string_value(item.get("property_use")))
    if comparable_use_group == "unknown":
        return "The comparable Land use is unknown."
    if (
        subject_use_group != "unknown"
        and subject_use_group != comparable_use_group
    ):
        return "The comparable Land use is incompatible with the subject."
    return None


def classify_evidence_tier(
    *,
    distance_miles: float | None,
    days_old: int | None,
    acreage_ratio: Decimal | None,
) -> str | None:
    if days_old is None or acreage_ratio is None:
        return None
    for tier in ("preferred", "expanded", "extended"):
        policy = LAND_SEARCH_TIERS[tier]
        within_distance = distance_miles is None or distance_miles <= float(
            policy["radius_miles"]
        )
        if (
            within_distance
            and days_old <= int(policy["months"]) * 31
            and Decimal(str(policy["minimum_ratio"]))
            <= acreage_ratio
            <= Decimal(str(policy["maximum_ratio"]))
        ):
            return tier
    return None


def evidence_score(
    *,
    evidence_tier: str | None,
    distance_miles: float | None,
    days_old: int | None,
    acreage_ratio: Decimal | None,
    property_use: str | None,
) -> int:
    score = (
        {"preferred": 100, "expanded": 80, "extended": 60}.get(evidence_tier, 0)
        if evidence_tier is not None
        else 0
    )
    if score == 0:
        return 0
    if distance_miles is not None:
        score -= min(15, round(distance_miles / 4))
    if days_old is not None:
        score -= min(15, round(days_old / 365 * 3))
    if acreage_ratio and acreage_ratio > 0:
        score -= min(15, round(abs(math.log(float(acreage_ratio))) * 8))
    if land_use_group(property_use) == "unknown":
        score -= 5
    return max(1, score)


def land_use_group(value: str | None) -> str:
    normalized = " ".join(str(value or "").strip().lower().replace("_", "-").split())
    for key in ("residential", "agricultural", "farm", "commercial", "industrial", "recreational"):
        if key in normalized:
            return "agricultural" if key == "farm" else key
    return "unknown"


def address_values(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("address") or record.get("propertyAddress")
    return value if isinstance(value, dict) else {}


def formatted_address_value(
    record: dict[str, Any],
    address: dict[str, Any],
    property_address: dict[str, Any],
) -> str | None:
    direct = string_value(
        record.get("formattedAddress")
        or address.get("formattedAddress")
        or address.get("address")
        or property_address.get("formattedAddress")
        or property_address.get("address")
    )
    if direct:
        return direct
    street = string_value(
        record.get("streetAddress")
        or address.get("street")
        or property_address.get("street")
    )
    city = string_value(record.get("city") or address.get("city") or property_address.get("city"))
    state = string_value(
        record.get("state") or address.get("state") or property_address.get("state")
    )
    postal = string_value(
        record.get("zip") or address.get("zip") or property_address.get("zip")
    )
    locality = " ".join(value for value in (state, postal) if value)
    return ", ".join(value for value in (street, city, locality) if value) or None


def dictionary(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_value(record: dict[str, Any], *keys: str) -> Any:
    return next((record[key] for key in keys if record.get(key) is not None), None)


def string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def integer_value(value: Any) -> int | None:
    decimal = decimal_value(value)
    return int(decimal.to_integral_value(rounding=ROUND_HALF_UP)) if decimal is not None else None


def float_value(value: Any) -> float | None:
    decimal = decimal_value(value)
    return float(decimal) if decimal is not None else None


def money_to_cents(value: Decimal | None) -> int | None:
    return round_decimal_to_int(value * 100) if value is not None and value > 0 else None


def round_decimal_to_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def haversine_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius_miles = 3958.7613
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_miles * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def days_in_month(year: int, month: int) -> int:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month - date(year, month, 1)).days
