from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.integrations.rentcast_client import RentCastRentEstimate
from app.services.underwriting_v2 import (
    UnderwritingV2Result,
    calculate_buyer_economics,
    conservative_arv_cents,
)

METHODOLOGY_VERSION = "v3"
SUPPORTED_STATUSES = {"supported", "partial"}


def promote_market_adjusted_result(
    *,
    baseline: UnderwritingV2Result,
    market_adjustment: dict[str, Any],
    rent_estimate: RentCastRentEstimate | None,
    local_property_type: str | None,
    holding_period_months: int,
    settings: Settings,
) -> UnderwritingV2Result:
    """Promote the V3 conclusion and recompute all dependent economics."""
    conclusion = dictionary(market_adjustment.get("conclusion"))
    status = text(market_adjustment.get("status")) or "unsupported"
    point = integer(conclusion.get("arv_point_cents"))
    comp_count = integer(conclusion.get("comp_count")) or 0
    usable = status in SUPPORTED_STATUSES and point is not None and comp_count >= 2
    if not usable:
        return unsupported_result(baseline, market_adjustment)

    low = integer(conclusion.get("arv_low_cents")) or point
    high = integer(conclusion.get("arv_high_cents")) or point
    confidence_score = bounded_confidence(
        integer(conclusion.get("confidence_score")),
        fallback=baseline.confidence_score,
    )
    confidence_tier = text(conclusion.get("confidence_tier")) or "insufficient"
    if comp_count == 2:
        confidence_score = min(confidence_score, 49)
        confidence_tier = "insufficient"
    conservative_arv = conservative_arv_cents(
        low=low,
        point=point,
        confidence_score=confidence_score,
    )
    subject = dictionary(baseline.assumptions.get("canonical_subject_facts"))
    repair_level = text(baseline.assumptions.get("repair_level")) or "moderate"
    buyer_economics = calculate_buyer_economics(
        conservative_arv_cents=conservative_arv,
        repair_level=repair_level,
        base_rehab_cents=baseline.base_rehab_cents,
        total_rehab_cents=baseline.total_rehab_cents,
        subject_record=subject,
        rent_estimate=rent_estimate,
        property_type=text(subject.get("propertyType")) or local_property_type,
        holding_period_months=holding_period_months,
        settings=settings,
    )
    flip_max = integer(buyer_economics.get("flip_buyer_max_cents"))
    rental_max = integer(buyer_economics.get("rental_buyer_max_cents"))
    disposition_values = [
        value for value in (flip_max, rental_max) if value is not None and value > 0
    ]
    recommended_disposition = max(disposition_values) if disposition_values else None
    assignment_fee = settings.underwriting_default_assignment_fee_cents
    transaction_reserve = settings.underwriting_transaction_reserve_cents
    seller_ceiling = (
        max(0, recommended_disposition - assignment_fee - transaction_reserve)
        if recommended_disposition is not None
        else None
    )
    opening_offer = (
        max(
            0,
            round(seller_ceiling * (1 - settings.underwriting_negotiation_reserve_percentage)),
        )
        if seller_ceiling is not None
        else None
    )
    legacy_rule = (
        max(
            0,
            round(
                conservative_arv * settings.underwriting_offer_high_percentage
                - baseline.total_rehab_cents
                - assignment_fee
            ),
        )
        if conservative_arv is not None
        else None
    )
    review_reasons = current_review_reasons(baseline.review_reasons)
    if status == "partial":
        review_reasons.append(
            "Some property differences lack local adjustment support; review the "
            "comparable indications before approving value."
        )
    if comp_count == 2:
        review_reasons.append(
            "This is working guidance from two usable closed sales. Confirm another sale or "
            "have a person approve the evidence before presenting a final offer."
        )
    warnings = strings(market_adjustment.get("warnings"))
    review_reasons.extend(warnings)
    if rental_max is None:
        review_reasons.append("Rental exit could not be supported with the available data.")
    confidence_factors = dictionaries(market_adjustment.get("confidence_factors"))
    assumptions = {
        **baseline.assumptions,
        **dictionary(buyer_economics.get("assumptions")),
        "methodology_version": METHODOLOGY_VERSION,
        "arv_value_basis": "market_supported_adjusted_closed_sales",
        "comp_value_method": "market_supported_adjusted_sale_indications",
        "adjustment_status": status,
        "adjustment_version": text(market_adjustment.get("version")),
        "valuation_evidence_status": (
            "working_two_sale_guidance" if comp_count == 2 else "supported"
        ),
        "rollback_methodology_version": "v2.2",
        "rollback_arv_low_cents": baseline.arv_low_cents,
        "rollback_arv_point_cents": baseline.arv_point_cents,
        "rollback_arv_high_cents": baseline.arv_high_cents,
    }
    return replace(
        baseline,
        arv_low_cents=low,
        arv_point_cents=point,
        arv_high_cents=high,
        conservative_arv_cents=conservative_arv,
        flip_buyer_max_cents=flip_max,
        rental_buyer_max_cents=rental_max,
        recommended_disposition_cents=recommended_disposition,
        seller_contract_ceiling_cents=seller_ceiling,
        recommended_opening_offer_cents=opening_offer,
        legacy_rule_cents=legacy_rule,
        monthly_rent_cents=integer(buyer_economics.get("monthly_rent_cents")),
        confidence_score=confidence_score,
        confidence_tier=confidence_tier,
        confidence_factors=confidence_factors,
        manual_review_required=(
            baseline.manual_review_required
            or status != "supported"
            or confidence_score < 75
            or comp_count == 2
            or market_adjustment.get("requires_manual_review") is True
        ),
        review_reasons=dedupe(review_reasons),
        assumptions=assumptions,
    )


def unsupported_result(
    baseline: UnderwritingV2Result,
    market_adjustment: dict[str, Any],
) -> UnderwritingV2Result:
    conclusion = dictionary(market_adjustment.get("conclusion"))
    confidence_score = min(
        59,
        bounded_confidence(
            integer(conclusion.get("confidence_score")),
            fallback=baseline.confidence_score,
        ),
    )
    reasons = current_review_reasons(baseline.review_reasons)
    reasons.append(
        "Stonegate Valuation could not support working ARV guidance from at least two usable "
        "closed-sale indications. Review or add comparable evidence."
    )
    reasons.extend(strings(market_adjustment.get("warnings")))
    assumptions = {
        **baseline.assumptions,
        "methodology_version": METHODOLOGY_VERSION,
        "arv_value_basis": "unsupported",
        "comp_value_method": "market_supported_adjusted_sale_indications",
        "adjustment_status": text(market_adjustment.get("status")) or "unsupported",
        "adjustment_version": text(market_adjustment.get("version")),
        "rollback_methodology_version": "v2.2",
        "rollback_arv_low_cents": baseline.arv_low_cents,
        "rollback_arv_point_cents": baseline.arv_point_cents,
        "rollback_arv_high_cents": baseline.arv_high_cents,
    }
    return replace(
        baseline,
        arv_low_cents=None,
        arv_point_cents=None,
        arv_high_cents=None,
        conservative_arv_cents=None,
        flip_buyer_max_cents=None,
        rental_buyer_max_cents=None,
        recommended_disposition_cents=None,
        seller_contract_ceiling_cents=None,
        recommended_opening_offer_cents=None,
        legacy_rule_cents=None,
        confidence_score=confidence_score,
        confidence_tier="insufficient",
        confidence_factors=dictionaries(market_adjustment.get("confidence_factors")),
        manual_review_required=True,
        review_reasons=dedupe(reasons),
        assumptions=assumptions,
    )


def current_review_reasons(values: list[str]) -> list[str]:
    stale_fragments = (
        "supported ARV range is wider",
        "RentCast AVM falls outside the recorded-sale range",
        "Rental exit could not be supported",
    )
    return [value for value in values if not any(fragment in value for fragment in stale_fragments)]


def bounded_confidence(value: int | None, *, fallback: int) -> int:
    return max(0, min(100, value if value is not None else fallback))


def integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def dictionary(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dictionaries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
