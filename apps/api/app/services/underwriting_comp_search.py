from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.integrations.rentcast_client import RentCastClientError
from app.schemas.leads import MarketAnalysisCompRead
from app.services.underwriting_v2 import analyze_recorded_sales

SearchLevelKey = Literal["preferred", "expanded", "extended"]

SEARCH_STRATEGY_VERSION = "adaptive_v1"
MINIMUM_CLOSED_SALES = 3


class ClosedSaleProvider(Protocol):
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
        ...


@dataclass(frozen=True)
class ClosedSaleSearchProfile:
    key: SearchLevelKey
    radius_miles: float
    days_old: int
    bedroom_tolerance: float
    bathroom_tolerance: float
    square_footage_tolerance: float
    year_built_tolerance: int


SEARCH_PROFILES = (
    ClosedSaleSearchProfile(
        key="preferred",
        radius_miles=0.5,
        days_old=180,
        bedroom_tolerance=0,
        bathroom_tolerance=0.5,
        square_footage_tolerance=0.15,
        year_built_tolerance=15,
    ),
    ClosedSaleSearchProfile(
        key="expanded",
        radius_miles=1,
        days_old=365,
        bedroom_tolerance=1,
        bathroom_tolerance=1,
        square_footage_tolerance=0.2,
        year_built_tolerance=25,
    ),
    ClosedSaleSearchProfile(
        key="extended",
        radius_miles=3,
        days_old=730,
        bedroom_tolerance=1,
        bathroom_tolerance=1,
        square_footage_tolerance=0.25,
        year_built_tolerance=35,
    ),
)


@dataclass(frozen=True)
class AdaptiveClosedSaleSearchResult:
    records: list[dict[str, Any]]
    summary: dict[str, Any]
    provider_returned_count: int
    warnings: list[str]


def search_adaptive_closed_sales(
    client: ClosedSaleProvider,
    *,
    address: str,
    subject_facts: dict[str, Any],
    local_property_type: str | None,
    condition_overrides: dict[str, str],
) -> AdaptiveClosedSaleSearchResult:
    subject = dict(subject_facts)
    if not clean_text(subject.get("propertyType")) and local_property_type:
        subject["propertyType"] = local_property_type

    unique_records: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    total_provider_results = 0
    total_duplicate_results = 0
    expansion_reason: str | None = None
    final_selected: list[MarketAnalysisCompRead] = []
    final_rejected: list[MarketAnalysisCompRead] = []
    sufficient = False
    market_area_warning: str | None = None
    provider_error: str | None = None

    for profile in SEARCH_PROFILES:
        try:
            returned = client.get_recent_sales(
                address=address,
                property_type=(clean_text(subject.get("propertyType")) or local_property_type),
                bedrooms=optional_float(subject.get("bedrooms")),
                bathrooms=optional_float(subject.get("bathrooms")),
                square_footage=optional_int(subject.get("squareFootage")),
                year_built=optional_int(subject.get("yearBuilt")),
                latitude=optional_float(subject.get("latitude")),
                longitude=optional_float(subject.get("longitude")),
                radius=profile.radius_miles,
                days_old=profile.days_old,
                limit=50,
                bedroom_tolerance=profile.bedroom_tolerance,
                bathroom_tolerance=profile.bathroom_tolerance,
                square_footage_tolerance=profile.square_footage_tolerance,
                year_built_tolerance=profile.year_built_tolerance,
            )
        except RentCastClientError as exc:
            if not unique_records:
                raise
            provider_error = str(exc)
            attempts.append(
                attempt_payload(
                    profile,
                    returned_count=0,
                    unique_added_count=0,
                    duplicate_count=0,
                    cumulative_unique_count=len(unique_records),
                    selected_count=len(final_selected),
                    rejected_count=len(final_rejected),
                    same_subdivision_count=count_same_subdivision(
                        subject,
                        final_selected,
                    ),
                    expansion_reason=expansion_reason,
                    provider_error=provider_error,
                )
            )
            break

        total_provider_results += len(returned)
        unique_added_count, duplicate_count = merge_unique_sales(
            unique_records,
            returned,
            search_level=profile.key,
        )
        total_duplicate_results += duplicate_count
        final_selected, final_rejected = analyze_recorded_sales(
            subject,
            list(unique_records.values()),
            condition_overrides=condition_overrides,
        )
        sufficient, market_area_warning = closed_sale_evidence_is_sufficient(
            subject,
            final_selected,
        )
        attempts.append(
            attempt_payload(
                profile,
                returned_count=len(returned),
                unique_added_count=unique_added_count,
                duplicate_count=duplicate_count,
                cumulative_unique_count=len(unique_records),
                selected_count=len(final_selected),
                rejected_count=len(final_rejected),
                same_subdivision_count=count_same_subdivision(
                    subject,
                    final_selected,
                ),
                expansion_reason=expansion_reason,
                provider_error=None,
            )
        )
        if sufficient:
            break
        expansion_reason = expansion_reason_for(
            subject,
            final_selected,
            market_area_warning,
        )

    last_provider_level = (
        attempts[-1]["level"] if attempts and attempts[-1]["level"] != "manual" else "preferred"
    )
    shortage_reason = (
        None
        if sufficient
        else evidence_shortage_reason(
            subject,
            final_selected,
            market_area_warning,
            provider_error,
        )
    )
    final_level = last_provider_level if sufficient else "manual"
    if not sufficient:
        attempts.append(
            {
                "level": "manual",
                "radius_miles": None,
                "days_old": None,
                "bedroom_tolerance": None,
                "bathroom_tolerance": None,
                "square_footage_tolerance_percentage": None,
                "year_built_tolerance_years": None,
                "returned_count": 0,
                "unique_added_count": 0,
                "duplicate_count": 0,
                "cumulative_unique_count": len(unique_records),
                "selected_count": len(final_selected),
                "rejected_count": len(final_rejected),
                "same_subdivision_count": count_same_subdivision(
                    subject,
                    final_selected,
                ),
                "expansion_reason": shortage_reason,
                "provider_error": None,
            }
        )

    final_market_warning = market_area_warning_for(
        subject,
        final_selected,
        final_level=final_level,
        existing_warning=market_area_warning,
    )
    summary = {
        "strategy_version": SEARCH_STRATEGY_VERSION,
        "final_level": final_level,
        "sufficient_closed_sales": sufficient,
        "minimum_closed_sales": MINIMUM_CLOSED_SALES,
        "total_provider_results": total_provider_results,
        "total_unique_sales": len(unique_records),
        "duplicate_count": total_duplicate_results,
        "subject_subdivision": clean_text(subject.get("subdivision")),
        "same_subdivision_count": count_same_subdivision(subject, final_selected),
        "market_area_warning": final_market_warning,
        "evidence_shortage_reason": shortage_reason,
        "next_action": next_action(
            final_level=final_level,
            selected_count=len(final_selected),
        ),
        "attempts": attempts,
    }
    return AdaptiveClosedSaleSearchResult(
        records=list(unique_records.values()),
        summary=summary,
        provider_returned_count=total_provider_results,
        warnings=warnings_from_search_summary(summary),
    )


def attempt_payload(
    profile: ClosedSaleSearchProfile,
    *,
    returned_count: int,
    unique_added_count: int,
    duplicate_count: int,
    cumulative_unique_count: int,
    selected_count: int,
    rejected_count: int,
    same_subdivision_count: int,
    expansion_reason: str | None,
    provider_error: str | None,
) -> dict[str, Any]:
    return {
        "level": profile.key,
        "radius_miles": profile.radius_miles,
        "days_old": profile.days_old,
        "bedroom_tolerance": profile.bedroom_tolerance,
        "bathroom_tolerance": profile.bathroom_tolerance,
        "square_footage_tolerance_percentage": round(profile.square_footage_tolerance * 100),
        "year_built_tolerance_years": profile.year_built_tolerance,
        "returned_count": returned_count,
        "unique_added_count": unique_added_count,
        "duplicate_count": duplicate_count,
        "cumulative_unique_count": cumulative_unique_count,
        "selected_count": selected_count,
        "rejected_count": rejected_count,
        "same_subdivision_count": same_subdivision_count,
        "expansion_reason": expansion_reason,
        "provider_error": provider_error,
    }


def merge_unique_sales(
    unique_records: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    search_level: SearchLevelKey,
) -> tuple[int, int]:
    added = 0
    duplicates = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        key = closed_sale_key(record, fallback_index=index)
        annotated = {**record, "_stonegateSearchLevel": search_level}
        existing = unique_records.get(key)
        if existing is None:
            unique_records[key] = annotated
            added += 1
            continue
        duplicates += 1
        unique_records[key] = merge_record_details(existing, annotated)
    return added, duplicates


def merge_record_details(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "_stonegateSearchLevel":
            continue
        if merged.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    return merged


def closed_sale_key(record: dict[str, Any], *, fallback_index: int) -> str:
    provider_id = normalize_identifier(record.get("id"))
    if provider_id:
        return f"id:{provider_id}"
    address = normalize_identifier(record.get("formattedAddress"))
    if address:
        return f"address:{address}"
    fallback_parts = [
        normalize_identifier(record.get("lastSaleDate")),
        normalize_identifier(record.get("lastSalePrice")),
        normalize_identifier(record.get("latitude")),
        normalize_identifier(record.get("longitude")),
        normalize_identifier(record.get("squareFootage")),
    ]
    fallback = "|".join(part for part in fallback_parts if part)
    return f"facts:{fallback}" if fallback else f"unknown:{fallback_index}"


def closed_sale_evidence_is_sufficient(
    subject: dict[str, Any],
    selected: list[MarketAnalysisCompRead],
) -> tuple[bool, str | None]:
    if len(selected) < MINIMUM_CLOSED_SALES:
        return False, None
    subject_subdivision = normalize_identifier(subject.get("subdivision"))
    if not subject_subdivision:
        return True, None
    comps_with_subdivision = [comp for comp in selected if normalize_identifier(comp.subdivision)]
    if not comps_with_subdivision:
        return (
            True,
            "The subject subdivision is known, but the selected sales do not include "
            "subdivision data; confirm the micro-market boundary during review.",
        )
    same_subdivision_count = count_same_subdivision(subject, selected)
    if same_subdivision_count >= 2:
        return True, None
    return (
        False,
        "Fewer than two selected sales match the subject subdivision even though "
        "subdivision evidence is available.",
    )


def expansion_reason_for(
    subject: dict[str, Any],
    selected: list[MarketAnalysisCompRead],
    market_area_warning: str | None,
) -> str:
    if len(selected) < MINIMUM_CLOSED_SALES:
        return (
            f"Only {len(selected)} usable closed sale(s) remained after screening; "
            "the next controlled search level was required."
        )
    if market_area_warning:
        return market_area_warning
    if clean_text(subject.get("subdivision")):
        return "Subdivision support was not strong enough at the prior search level."
    return "The prior search level did not meet the closed-sale evidence threshold."


def evidence_shortage_reason(
    subject: dict[str, Any],
    selected: list[MarketAnalysisCompRead],
    market_area_warning: str | None,
    provider_error: str | None,
) -> str:
    if provider_error:
        return (
            f"The provider stopped responding after {len(selected)} usable closed sale(s) "
            "were found; the wider search could not be completed."
        )
    if len(selected) < MINIMUM_CLOSED_SALES:
        return (
            f"The complete adaptive search found {len(selected)} usable closed sale(s); "
            f"at least {MINIMUM_CLOSED_SALES} are required for a sufficient set."
        )
    if market_area_warning:
        return market_area_warning
    if clean_text(subject.get("subdivision")):
        return "The returned sales did not adequately support the subject subdivision."
    return "The returned closed sales did not meet the minimum evidence standard."


def market_area_warning_for(
    subject: dict[str, Any],
    selected: list[MarketAnalysisCompRead],
    *,
    final_level: str,
    existing_warning: str | None,
) -> str | None:
    warnings: list[str] = []
    if existing_warning:
        warnings.append(existing_warning)
    if final_level == "expanded":
        warnings.append(
            "The comp set required the expanded search; confirm neighborhood boundaries."
        )
    elif final_level in {"extended", "manual"}:
        warnings.append(
            "The comp set reached the extended search; distance, recency, and "
            "micro-market differences require specific review."
        )
    subject_subdivision = normalize_identifier(subject.get("subdivision"))
    mismatched = sum(comp.subdivision_match is False for comp in selected)
    if subject_subdivision and mismatched:
        warnings.append(
            f"{mismatched} selected sale(s) are outside the recorded subject subdivision."
        )
    return " ".join(dedupe_strings(warnings)) or None


def warnings_from_search_summary(summary: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    final_level = clean_text(summary.get("final_level")) or "preferred"
    shortage_reason = clean_text(summary.get("evidence_shortage_reason"))
    market_area_warning = clean_text(summary.get("market_area_warning"))
    if shortage_reason:
        warnings.append(shortage_reason)
    elif market_area_warning:
        warnings.append(market_area_warning)
    elif final_level in {"expanded", "extended"}:
        warnings.append(f"Closed-sale discovery finished at the {final_level} evidence level.")
    attempts = summary.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            provider_error = clean_text(attempt.get("provider_error"))
            if provider_error:
                warnings.append(provider_error)
    return dedupe_strings(warnings)


def next_action(*, final_level: str, selected_count: int) -> str:
    if final_level == "preferred":
        return "Verify comp condition and approve or revise the recommended closed-sale set."
    if final_level in {"expanded", "extended"}:
        return (
            "Review the widened-market sales, especially location and condition, before "
            "approving the value conclusion."
        )
    return (
        f"Verify the subject facts and obtain a known closed sale for manual review; "
        f"only {selected_count} usable provider sale(s) are currently available."
    )


def count_same_subdivision(
    subject: dict[str, Any],
    selected: list[MarketAnalysisCompRead],
) -> int:
    subject_subdivision = normalize_identifier(subject.get("subdivision"))
    if not subject_subdivision:
        return 0
    return sum(
        normalize_identifier(comp.subdivision) == subject_subdivision
        for comp in selected
        if normalize_identifier(comp.subdivision)
    )


def normalize_identifier(value: object) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return "".join(character for character in text.casefold() if character.isalnum())


def clean_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    return None


def dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
