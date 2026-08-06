from datetime import UTC, datetime
from typing import Any, Protocol

from app.integrations.rentcast_client import RentCastClientError

MONEY = 100
SUPPORTING_EVIDENCE_VERSION = "supporting_v1"


class SupportingEvidenceProvider(Protocol):
    def get_sale_listings(
        self,
        *,
        address: str,
        property_type: str | None,
        bedrooms: float | None,
        bathrooms: float | None,
        square_footage: int | None,
        radius: float = 1,
        days_old: int = 180,
        limit: int = 12,
    ) -> list[dict[str, Any]]: ...

    def get_market_statistics(
        self,
        *,
        postal_code: str,
        history_months: int = 12,
    ) -> dict[str, Any]: ...


def collect_supporting_market_evidence(
    provider: SupportingEvidenceProvider,
    *,
    address: str,
    postal_code: str,
    subject_facts: dict[str, Any],
    local_property_type: str | None,
) -> dict[str, Any]:
    """Collect context that is explicitly excluded from closed-sale valuation math."""
    listings: list[dict[str, Any]] = []
    market_context: dict[str, Any] | None = None
    errors: list[str] = []

    get_listings = getattr(provider, "get_sale_listings", None)
    if callable(get_listings):
        try:
            raw_listings = get_listings(
                address=address,
                property_type=string(subject_facts.get("propertyType")) or local_property_type,
                bedrooms=number(subject_facts.get("bedrooms")),
                bathrooms=number(subject_facts.get("bathrooms")),
                square_footage=integer(subject_facts.get("squareFootage")),
            )
            listings = normalize_sale_listings(raw_listings, subject_facts=subject_facts)
        except RentCastClientError as exc:
            errors.append(str(exc))
    else:
        errors.append("The configured provider does not expose supporting sale listings.")

    get_market = getattr(provider, "get_market_statistics", None)
    normalized_postal_code = five_digit_postal_code(postal_code)
    if callable(get_market) and normalized_postal_code:
        try:
            market_context = normalize_market_statistics(
                get_market(postal_code=normalized_postal_code, history_months=12)
            )
        except RentCastClientError as exc:
            errors.append(str(exc))
    elif not normalized_postal_code:
        errors.append("A five-digit ZIP code is required for market statistics.")
    else:
        errors.append("The configured provider does not expose sale market statistics.")

    if listings and market_context:
        status = "completed"
    elif listings or market_context:
        status = "partial"
    else:
        status = "unavailable"
    return {
        "version": SUPPORTING_EVIDENCE_VERSION,
        "status": status,
        "provider": "rentcast",
        "evidence_role": "supporting_only",
        "valuation_use": "excluded_from_arv_and_offer_math",
        "sale_listings": listings,
        "market_context": market_context,
        "errors": errors,
        "collected_at": datetime.now(UTC).isoformat(),
    }


def unavailable_supporting_evidence(reason: str) -> dict[str, Any]:
    return {
        "version": SUPPORTING_EVIDENCE_VERSION,
        "status": "unavailable",
        "provider": "rentcast",
        "evidence_role": "supporting_only",
        "valuation_use": "excluded_from_arv_and_offer_math",
        "sale_listings": [],
        "market_context": None,
        "errors": [reason],
        "collected_at": None,
    }


def normalize_sale_listings(
    records: list[dict[str, Any]],
    *,
    subject_facts: dict[str, Any],
) -> list[dict[str, Any]]:
    subject_address = address_key(string(subject_facts.get("formattedAddress")))
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for record in records:
        address = string(record.get("formattedAddress"))
        key = string(record.get("id")) or address_key(address)
        if not key or key in seen or (subject_address and address_key(address) == subject_address):
            continue
        seen.add(key)
        price = integer(record.get("price"))
        normalized.append(
            {
                "provider_id": string(record.get("id")),
                "formatted_address": address,
                "status": string(record.get("status")) or "Active",
                "listing_type": string(record.get("listingType")),
                "property_type": string(record.get("propertyType")),
                "asking_price_cents": price * MONEY if price is not None else None,
                "bedrooms": number(record.get("bedrooms")),
                "bathrooms": number(record.get("bathrooms")),
                "square_footage": integer(record.get("squareFootage")),
                "year_built": integer(record.get("yearBuilt")),
                "distance_miles": number(record.get("distance")),
                "listed_date": string(record.get("listedDate")),
                "last_seen_date": string(record.get("lastSeenDate")),
                "days_on_market": integer(record.get("daysOnMarket")),
                "source": "rentcast_sale_listing",
                "evidence_role": "supporting_only",
            }
        )
    return normalized[:8]


def normalize_market_statistics(payload: dict[str, Any]) -> dict[str, Any] | None:
    sale_data = payload.get("saleData")
    if not isinstance(sale_data, dict):
        return None
    history = sale_data.get("history")
    if isinstance(history, list):
        history_rows = [row for row in history if isinstance(row, dict)]
    elif isinstance(history, dict):
        history_rows = [
            {"date": history_date, **row}
            for history_date, row in history.items()
            if isinstance(row, dict)
        ]
    else:
        history_rows = []
    history_rows.sort(
        key=lambda row: string(row.get("date")) or string(row.get("lastUpdatedDate")) or ""
    )
    current_median = integer(sale_data.get("medianPrice"))
    comparison = next(
        (
            integer(row.get("medianPrice"))
            for row in history_rows
            if integer(row.get("medianPrice")) is not None
            and integer(row.get("medianPrice")) != current_median
        ),
        None,
    )
    median_change = (
        round((current_median - comparison) / comparison * 100, 1)
        if current_median is not None and comparison is not None and comparison > 0
        else None
    )
    return {
        "zip_code": string(payload.get("zipCode")) or string(payload.get("id")),
        "last_updated_date": string(sale_data.get("lastUpdatedDate")),
        "median_list_price_cents": cents(sale_data.get("medianPrice")),
        "average_list_price_cents": cents(sale_data.get("averagePrice")),
        "median_price_per_square_foot_cents": cents(sale_data.get("medianPricePerSquareFoot")),
        "average_days_on_market": number(sale_data.get("averageDaysOnMarket")),
        "median_days_on_market": number(sale_data.get("medianDaysOnMarket")),
        "total_listings": integer(sale_data.get("totalListings")),
        "new_listings": integer(sale_data.get("newListings")),
        "median_list_price_change_percentage": median_change,
        "history_months_returned": len(history_rows),
        "source": "rentcast_market_statistics",
        "evidence_role": "supporting_only",
    }


def cents(value: Any) -> int | None:
    amount = number(value)
    return round(amount * MONEY) if amount is not None else None


def five_digit_postal_code(value: str) -> str | None:
    digits = "".join(character for character in value if character.isdigit())
    return digits[:5] if len(digits) >= 5 else None


def address_key(value: str | None) -> str:
    return "".join(character for character in (value or "").lower() if character.isalnum())


def string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(value)
    return None


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
