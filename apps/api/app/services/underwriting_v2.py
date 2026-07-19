from dataclasses import dataclass
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from statistics import median
from typing import Any

from app.core.config import Settings
from app.integrations.rentcast_client import RentCastRentEstimate, RentCastValueEstimate
from app.schemas.leads import MarketAnalysisCompRead

MONEY = 100
METHODOLOGY_VERSION = "v2.1"


@dataclass(frozen=True)
class UnderwritingV2Result:
    selected_comps: list[MarketAnalysisCompRead]
    rejected_comps: list[MarketAnalysisCompRead]
    as_is_low_cents: int | None
    as_is_value_cents: int | None
    as_is_high_cents: int | None
    arv_low_cents: int | None
    arv_point_cents: int | None
    arv_high_cents: int | None
    conservative_arv_cents: int | None
    repair_low_cents: int
    repair_high_cents: int
    base_rehab_cents: int
    rehab_contingency_percentage: int
    total_rehab_cents: int
    flip_buyer_max_cents: int | None
    rental_buyer_max_cents: int | None
    recommended_disposition_cents: int | None
    seller_contract_ceiling_cents: int | None
    recommended_opening_offer_cents: int | None
    legacy_rule_cents: int | None
    monthly_rent_cents: int | None
    confidence_score: int
    manual_review_required: bool
    review_reasons: list[str]
    data_disagreements: list[str]
    assumptions: dict[str, Any]


def analyze_underwriting_v2(
    *,
    estimate: RentCastValueEstimate,
    subject_record: dict[str, Any],
    sale_records: list[dict[str, Any]],
    rent_estimate: RentCastRentEstimate | None,
    local_property_type: str | None,
    lead_condition: str | None,
    current_condition_override: str | None,
    target_condition: str,
    repair_level_override: str | None,
    base_rehab_override_cents: int | None,
    repair_items: list[dict[str, Any]],
    contingency_override_percentage: int | None,
    holding_period_months: int,
    condition_overrides: dict[str, str],
    settings: Settings,
) -> UnderwritingV2Result:
    subject = merge_subject_facts(subject_record, estimate.subject_property)
    selected_comps, rejected_comps = analyze_recorded_sales(
        subject,
        sale_records,
        condition_overrides=condition_overrides,
    )
    data_disagreements = find_data_disagreements(
        subject_record=subject_record,
        avm_subject=estimate.subject_property,
        local_property_type=local_property_type,
    )

    renovated = [
        comp for comp in selected_comps if comp.condition_classification == "renovated"
    ]
    as_is = [comp for comp in selected_comps if comp.condition_classification == "as_is"]
    if len(renovated) >= 3:
        arv_evidence = renovated
        arv_value_basis = "verified_renovated_recorded_sales"
    else:
        arv_evidence = [
            comp
            for comp in selected_comps
            if comp.condition_classification != "as_is"
        ]
        arv_value_basis = (
            "provisional_unverified_recorded_sales"
            if arv_evidence
            else "unsupported"
        )
    arv_low, arv_point, arv_high = weighted_value_range(arv_evidence)
    if arv_point is None:
        arv_value_basis = "unsupported"

    as_is_low, as_is_point, as_is_high = weighted_value_range(as_is)
    as_is_value_basis = "verified_as_is_recorded_sales"
    if as_is_point is None:
        as_is_low = dollars_to_cents(estimate.price_range_low)
        as_is_point = dollars_to_cents(estimate.price)
        as_is_high = dollars_to_cents(estimate.price_range_high)
        as_is_value_basis = "provider_avm_benchmark"

    repair_level = normalize_repair_level(
        repair_level_override or current_condition_override or lead_condition
    )
    subject_square_feet = integer(subject.get("squareFootage"))
    repair = repair_assumptions(
        repair_level,
        subject_square_feet,
        base_rehab_override_cents=base_rehab_override_cents,
        repair_items=repair_items,
        contingency_override_percentage=contingency_override_percentage,
    )
    confidence_score, review_reasons = confidence_and_review_reasons(
        selected_comps=selected_comps,
        renovated_comps=renovated,
        as_is_comps=as_is,
        arv_low_cents=arv_low,
        arv_point_cents=arv_point,
        arv_high_cents=arv_high,
        avm_value_cents=dollars_to_cents(estimate.price),
        data_disagreements=data_disagreements,
    )
    conservative_arv = conservative_arv_cents(
        low=arv_low,
        point=arv_point,
        confidence_score=confidence_score,
    )
    buyer_economics = calculate_buyer_economics(
        conservative_arv_cents=conservative_arv,
        repair_level=repair_level,
        base_rehab_cents=repair["base_rehab_cents"],
        total_rehab_cents=repair["total_rehab_cents"],
        subject_record=subject,
        rent_estimate=rent_estimate,
        property_type=string(subject.get("propertyType")) or local_property_type,
        holding_period_months=holding_period_months,
        settings=settings,
    )
    disposition_values = [
        value
        for value in (
            buyer_economics["flip_buyer_max_cents"],
            buyer_economics["rental_buyer_max_cents"],
        )
        if isinstance(value, int) and value > 0
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
            round(
                seller_ceiling
                * (1 - settings.underwriting_negotiation_reserve_percentage)
            ),
        )
        if seller_ceiling is not None
        else None
    )
    legacy_rule = (
        max(
            0,
            round(
                conservative_arv * settings.underwriting_offer_high_percentage
                - repair["total_rehab_cents"]
                - assignment_fee
            ),
        )
        if conservative_arv is not None
        else None
    )
    if buyer_economics["rental_buyer_max_cents"] is None:
        review_reasons.append("Rental exit could not be supported with the available data.")

    assumptions = {
        "target_condition": normalize_key(target_condition) or "standard_flip",
        "current_condition": normalize_key(current_condition_override or lead_condition),
        "repair_level": repair_level,
        "arv_value_basis": arv_value_basis,
        "as_is_value_basis": as_is_value_basis,
        "arv_comp_count": len(arv_evidence),
        "subject_square_feet": subject_square_feet,
        "selected_median_price_per_square_foot_cents": median_optional_int(
            [
                comp.price_per_square_foot_cents
                for comp in selected_comps
                if comp.price_per_square_foot_cents is not None
            ]
        ),
        "ppsf_outlier_count": sum(
            "Price-per-square-foot outlier" in comp.selection_reason
            for comp in rejected_comps
        ),
        "comp_value_method": "subject_size_ppsf_indicator",
        "ppsf_outlier_method": "verified_renovated_median_mad_and_35_percent_guardrail",
        "purchase_cost_percentage": settings.underwriting_purchase_cost_percentage,
        "financing_holding_percentage": buyer_economics["assumptions"].get(
            "financing_holding_percentage"
        ),
        "resale_cost_percentage": settings.underwriting_resale_cost_percentage,
        "assignment_fee_cents": assignment_fee,
        "transaction_reserve_cents": transaction_reserve,
        "negotiation_reserve_percentage": settings.underwriting_negotiation_reserve_percentage,
        "rental_target_cap_rate": settings.underwriting_rental_target_cap_rate,
        **repair,
        **buyer_economics["assumptions"],
    }
    manual_review_required = confidence_score < 75 or any(
        reason
        for reason in review_reasons
        if not reason.startswith("Rental exit could not")
    )
    return UnderwritingV2Result(
        selected_comps=selected_comps,
        rejected_comps=rejected_comps,
        as_is_low_cents=as_is_low,
        as_is_value_cents=as_is_point,
        as_is_high_cents=as_is_high,
        arv_low_cents=arv_low,
        arv_point_cents=arv_point,
        arv_high_cents=arv_high,
        conservative_arv_cents=conservative_arv,
        repair_low_cents=repair["repair_low_cents"],
        repair_high_cents=repair["repair_high_cents"],
        base_rehab_cents=repair["base_rehab_cents"],
        rehab_contingency_percentage=repair["contingency_percentage"],
        total_rehab_cents=repair["total_rehab_cents"],
        flip_buyer_max_cents=optional_int(buyer_economics["flip_buyer_max_cents"]),
        rental_buyer_max_cents=optional_int(buyer_economics["rental_buyer_max_cents"]),
        recommended_disposition_cents=recommended_disposition,
        seller_contract_ceiling_cents=seller_ceiling,
        recommended_opening_offer_cents=opening_offer,
        legacy_rule_cents=legacy_rule,
        monthly_rent_cents=optional_int(buyer_economics["monthly_rent_cents"]),
        confidence_score=confidence_score,
        manual_review_required=manual_review_required,
        review_reasons=dedupe(review_reasons),
        data_disagreements=data_disagreements,
        assumptions=assumptions,
    )


def analyze_recorded_sales(
    subject: dict[str, Any],
    sale_records: list[dict[str, Any]],
    *,
    condition_overrides: dict[str, str],
) -> tuple[list[MarketAnalysisCompRead], list[MarketAnalysisCompRead]]:
    scored = [
        score_recorded_sale(
            subject,
            record,
            condition_overrides=condition_overrides,
        )
        for record in sale_records
    ]
    scored = reject_renovated_price_per_square_foot_outliers(scored)
    eligible = [comp for comp in scored if comp.selection_status != "rejected"]
    selected = sorted(eligible, key=lambda comp: comp.score, reverse=True)[:5]
    selected_keys = {comp_key(comp) for comp in selected}
    rejected = []
    for comp in scored:
        if comp_key(comp) in selected_keys:
            continue
        if comp.selection_status == "rejected":
            rejected.append(comp)
        else:
            rejected.append(
                comp.model_copy(
                    update={
                        "selection_status": "rejected",
                        "selection_reason": (
                            "Eligible recorded sale, but ranked below the five strongest matches."
                        ),
                    }
                )
            )
    return (
        [comp.model_copy(update={"selection_status": "selected"}) for comp in selected],
        [comp.model_copy(update={"selection_status": "rejected"}) for comp in rejected],
    )


def score_recorded_sale(
    subject: dict[str, Any],
    record: dict[str, Any],
    *,
    condition_overrides: dict[str, str],
) -> MarketAnalysisCompRead:
    provider_id = string(record.get("id"))
    address = string(record.get("formattedAddress"))
    sale_price = integer(record.get("lastSalePrice"))
    sale_date = string(record.get("lastSaleDate"))
    subject_square_feet = integer(subject.get("squareFootage"))
    comp_square_feet = integer(record.get("squareFootage"))
    price_per_square_foot_cents = (
        round(sale_price * MONEY / comp_square_feet)
        if sale_price is not None and comp_square_feet and comp_square_feet > 0
        else None
    )
    subject_size_value_cents = (
        round(sale_price * subject_square_feet / comp_square_feet) * MONEY
        if sale_price is not None
        and subject_square_feet
        and subject_square_feet > 0
        and comp_square_feet
        and comp_square_feet > 0
        else dollars_to_cents(sale_price)
    )
    condition = normalize_condition_override(
        condition_overrides.get(provider_id or "")
        or condition_overrides.get(address or "")
    )
    base: dict[str, Any] = {
        "provider_id": provider_id,
        "formatted_address": address,
        "status": "Recorded sale",
        "listing_type": "Property record",
        "property_type": string(record.get("propertyType")),
        "price_cents": dollars_to_cents(sale_price),
        "bedrooms": number(record.get("bedrooms")),
        "bathrooms": number(record.get("bathrooms")),
        "square_footage": integer(record.get("squareFootage")),
        "year_built": integer(record.get("yearBuilt")),
        "distance_miles": record_distance(subject, record),
        "days_old": days_since(sale_date),
        "correlation": None,
        "listed_date": None,
        "removed_date": None,
        "last_seen_date": None,
        "sale_date": sale_date,
        "price_source": "recorded_sale",
        "verification_status": "recorded",
        "condition_classification": condition,
        "condition_evidence": (
            "human_classification" if condition != "unknown" else "not_provided"
        ),
        "lot_size": integer(record.get("lotSize")),
        "adjusted_value_cents": subject_size_value_cents,
        "price_per_square_foot_cents": price_per_square_foot_cents,
        "weight": None,
    }
    rejection = recorded_sale_rejection_reason(subject, record, sale_price, sale_date)
    if rejection:
        return MarketAnalysisCompRead(
            **base,
            selection_status="rejected",
            selection_reason=rejection,
            score=0,
        )

    score = 100
    reasons = ["recorded sale price and date"]
    distance = optional_float(base["distance_miles"])
    if distance is None:
        score -= 12
        reasons.append("distance unavailable")
    elif distance > 0.5:
        score -= 8
        reasons.append("outside initial 0.5-mile area")
    days_old = optional_int(base["days_old"])
    if days_old is None:
        score -= 10
        reasons.append("sale recency unavailable")
    elif days_old > 180:
        score -= 8
        reasons.append("older than 180 days")

    size_difference = relative_difference(
        integer(subject.get("squareFootage")),
        integer(record.get("squareFootage")),
    )
    if size_difference is not None:
        score -= round(size_difference * 75)
        reasons.append(f"{round(size_difference * 100)}% size difference")
    year_difference = absolute_difference(
        integer(subject.get("yearBuilt")),
        integer(record.get("yearBuilt")),
    )
    if year_difference is not None and year_difference > 15:
        score -= 6
        reasons.append(f"{year_difference}-year age difference")
    lot_difference = relative_difference(
        integer(subject.get("lotSize")),
        integer(record.get("lotSize")),
    )
    if lot_difference is not None and lot_difference > 0.3:
        score -= 5
        reasons.append("material lot-size difference")
    bounded_score = max(1, min(100, score))
    return MarketAnalysisCompRead(
        **{**base, "weight": round(bounded_score / 100, 3)},
        selection_status="candidate",
        selection_reason=", ".join(reasons),
        score=bounded_score,
    )


def recorded_sale_rejection_reason(
    subject: dict[str, Any],
    record: dict[str, Any],
    sale_price: int | None,
    sale_date: str | None,
) -> str | None:
    if same_property(subject, record):
        return "Subject property sale; excluded from comparable set."
    if sale_price is None or sale_price <= 0:
        return "Missing recorded sale price."
    if not sale_date:
        return "Missing recorded sale date."
    subject_type = normalize_key(string(subject.get("propertyType")))
    comp_type = normalize_key(string(record.get("propertyType")))
    if subject_type and comp_type and subject_type != comp_type:
        return "Different property type."
    size_difference = relative_difference(
        integer(subject.get("squareFootage")),
        integer(record.get("squareFootage")),
    )
    if size_difference is not None and size_difference > 0.20:
        return "Living area differs by more than 20%."
    bed_difference = absolute_difference(
        number(subject.get("bedrooms")),
        number(record.get("bedrooms")),
    )
    if bed_difference is not None and bed_difference > 1:
        return "Bedroom count differs by more than one."
    bath_difference = absolute_difference(
        number(subject.get("bathrooms")),
        number(record.get("bathrooms")),
    )
    if bath_difference is not None and bath_difference > 1:
        return "Bathroom count differs by more than one."
    year_difference = absolute_difference(
        integer(subject.get("yearBuilt")),
        integer(record.get("yearBuilt")),
    )
    if year_difference is not None and year_difference > 25:
        return "Year built differs by more than 25 years."
    return None


def reject_renovated_price_per_square_foot_outliers(
    comps: list[MarketAnalysisCompRead],
) -> list[MarketAnalysisCompRead]:
    eligible = [
        comp
        for comp in comps
        if comp.selection_status != "rejected"
        and comp.condition_classification == "renovated"
        and comp.price_per_square_foot_cents is not None
    ]
    if len(eligible) < 3:
        return comps

    values = [
        comp.price_per_square_foot_cents
        for comp in eligible
        if comp.price_per_square_foot_cents is not None
    ]
    center = float(median(values))
    deviations = [abs(value - center) for value in values]
    mad = float(median(deviations))
    updated: list[MarketAnalysisCompRead] = []
    for comp in comps:
        value = comp.price_per_square_foot_cents
        if comp.selection_status == "rejected" or value is None or center <= 0:
            updated.append(comp)
            continue
        ratio = value / center
        modified_z = 0.6745 * abs(value - center) / mad if mad > 0 else 0
        statistically_extreme = modified_z > 3.5 and (ratio < 0.75 or ratio > 1.25)
        if ratio < 0.65 or ratio > 1.35 or statistically_extreme:
            updated.append(
                comp.model_copy(
                    update={
                        "selection_status": "rejected",
                        "selection_reason": (
                            "Price-per-square-foot outlier: "
                            f"{format_ppsf(value)} versus {format_ppsf(round(center))} "
                            "verified-renovated median."
                        ),
                        "score": 0,
                        "weight": None,
                    }
                )
            )
        else:
            updated.append(comp)
    return updated


def weighted_value_range(
    comps: list[MarketAnalysisCompRead],
) -> tuple[int | None, int | None, int | None]:
    values = [
        (comp.adjusted_value_cents or comp.price_cents, comp.weight or comp.score / 100)
        for comp in comps
        if (comp.adjusted_value_cents or comp.price_cents) is not None
    ]
    normalized = [(value, weight) for value, weight in values if value is not None]
    if not normalized:
        return None, None, None
    return (
        weighted_quantile(normalized, 0.25),
        weighted_quantile(normalized, 0.5),
        weighted_quantile(normalized, 0.75),
    )


def weighted_quantile(values: list[tuple[int, float]], target: float) -> int:
    ordered = sorted(values, key=lambda item: item[0])
    total_weight = sum(max(weight, 0.01) for _, weight in ordered)
    threshold = total_weight * target
    running = 0.0
    for value, weight in ordered:
        running += max(weight, 0.01)
        if running >= threshold:
            return value
    return ordered[-1][0]


def repair_assumptions(
    level: str,
    square_feet: int | None,
    *,
    base_rehab_override_cents: int | None,
    repair_items: list[dict[str, Any]],
    contingency_override_percentage: int | None,
) -> dict[str, Any]:
    rules = {
        "light": (15, 25, 10, 15_000_00, 30_000_00),
        "moderate": (30, 50, 15, 35_000_00, 60_000_00),
        "heavy": (60, 90, 20, 70_000_00, 120_000_00),
        "structural": (100, 140, 25, 120_000_00, 200_000_00),
    }
    low_rate, high_rate, default_contingency, fallback_low, fallback_high = rules[level]
    if square_feet and square_feet > 0:
        system_low = round(square_feet * low_rate * MONEY)
        system_high = round(square_feet * high_rate * MONEY)
    else:
        system_low, system_high = fallback_low, fallback_high

    itemized_total = sum(
        cost
        for item in repair_items
        if (cost := optional_int(item.get("estimated_cost_cents"))) is not None
    )
    if repair_items and itemized_total > 0:
        base_rehab = itemized_total
        repair_source = "itemized"
    elif base_rehab_override_cents is not None:
        base_rehab = base_rehab_override_cents
        repair_source = "user_total"
    else:
        base_rehab = round((system_low + system_high) / 2)
        repair_source = "system_estimate"

    contingency = (
        contingency_override_percentage
        if contingency_override_percentage is not None
        else default_contingency
    )
    total_rehab = round(base_rehab * (1 + contingency / 100))
    if repair_source == "system_estimate":
        repair_low, repair_high = system_low, system_high
    else:
        repair_low, repair_high = base_rehab, total_rehab
    return {
        "repair_low_cents": repair_low,
        "repair_high_cents": repair_high,
        "base_rehab_cents": base_rehab,
        "contingency_percentage": contingency,
        "total_rehab_cents": total_rehab,
        "repair_estimate_source": repair_source,
        "system_repair_low_cents": system_low,
        "system_repair_high_cents": system_high,
        "repair_items": repair_items,
    }


def calculate_buyer_economics(
    *,
    conservative_arv_cents: int | None,
    repair_level: str,
    base_rehab_cents: int,
    total_rehab_cents: int,
    subject_record: dict[str, Any],
    rent_estimate: RentCastRentEstimate | None,
    property_type: str | None,
    holding_period_months: int,
    settings: Settings,
) -> dict[str, Any]:
    if conservative_arv_cents is None:
        return {
            "flip_buyer_max_cents": None,
            "rental_buyer_max_cents": None,
            "monthly_rent_cents": dollars_to_cents(rent_estimate.rent)
            if rent_estimate
            else None,
            "assumptions": {},
        }
    profit_rules = {
        "light": (35_000_00, 0.12),
        "moderate": (45_000_00, 0.15),
        "heavy": (60_000_00, 0.18),
        "structural": (75_000_00, 0.20),
    }
    minimum_profit, profit_percentage = profit_rules[repair_level]
    required_profit = max(minimum_profit, round(conservative_arv_cents * profit_percentage))
    purchase_costs = round(
        conservative_arv_cents * settings.underwriting_purchase_cost_percentage
    )
    financing_holding_percentage = round(
        settings.underwriting_financing_holding_percentage
        * holding_period_months
        / 6,
        4,
    )
    financing_holding = round(conservative_arv_cents * financing_holding_percentage)
    resale_costs = round(
        conservative_arv_cents * settings.underwriting_resale_cost_percentage
    )
    flip_max = max(
        0,
        conservative_arv_cents
        - total_rehab_cents
        - purchase_costs
        - financing_holding
        - resale_costs
        - required_profit,
    )

    monthly_rent = dollars_to_cents(rent_estimate.rent) if rent_estimate else None
    rental_max = None
    rental_noi = None
    stabilized_rental_value = None
    normalized_type = normalize_key(property_type)
    if monthly_rent and normalized_type not in {"multi_family", "apartment"}:
        annual_rent = monthly_rent * 12
        vacancy = round(annual_rent * 0.05)
        maintenance = round(annual_rent * 0.08)
        management = round(annual_rent * 0.08)
        recorded_taxes = latest_mapping_amount(subject_record.get("propertyTaxes")) * MONEY
        taxes = (
            recorded_taxes
            if recorded_taxes > 0
            else round(conservative_arv_cents * 0.012)
        )
        insurance = round(conservative_arv_cents * 0.01)
        rental_noi = max(0, annual_rent - vacancy - maintenance - management - taxes - insurance)
        if settings.underwriting_rental_target_cap_rate > 0:
            stabilized_rental_value = round(
                rental_noi / settings.underwriting_rental_target_cap_rate
            )
            rental_purchase_costs = round(
                stabilized_rental_value * settings.underwriting_purchase_cost_percentage
            )
            rental_max = max(
                0,
                stabilized_rental_value - total_rehab_cents - rental_purchase_costs,
            )
    return {
        "flip_buyer_max_cents": flip_max,
        "rental_buyer_max_cents": rental_max,
        "monthly_rent_cents": monthly_rent,
        "assumptions": {
            "base_rehab_cents": base_rehab_cents,
            "required_buyer_profit_cents": required_profit,
            "buyer_profit_percentage": profit_percentage,
            "purchase_costs_cents": purchase_costs,
            "financing_holding_costs_cents": financing_holding,
            "financing_holding_percentage": financing_holding_percentage,
            "holding_period_months": holding_period_months,
            "resale_costs_cents": resale_costs,
            "rental_noi_cents": rental_noi,
            "stabilized_rental_value_cents": stabilized_rental_value,
            "rental_vacancy_percentage": 0.05,
            "rental_maintenance_percentage": 0.08,
            "rental_management_percentage": 0.08,
            "rental_insurance_percentage": 0.01,
            "annual_property_taxes_cents": taxes if monthly_rent else None,
            "property_tax_source": (
                "provider_record" if recorded_taxes > 0 else "1.2% fallback"
            )
            if monthly_rent
            else None,
        },
    }


def confidence_and_review_reasons(
    *,
    selected_comps: list[MarketAnalysisCompRead],
    renovated_comps: list[MarketAnalysisCompRead],
    as_is_comps: list[MarketAnalysisCompRead],
    arv_low_cents: int | None,
    arv_point_cents: int | None,
    arv_high_cents: int | None,
    avm_value_cents: int | None,
    data_disagreements: list[str],
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    average_score = (
        sum(comp.score for comp in selected_comps) / len(selected_comps)
        if selected_comps
        else 0
    )
    confidence = 20 + min(len(selected_comps), 5) * 10 + average_score * 0.25
    if len(selected_comps) < 3:
        reasons.append("Fewer than three verified recorded sales were available.")
        confidence -= 15
    if len(renovated_comps) < 3:
        reasons.append(
            "ARV and offer calculations are preliminary until at least three recorded sales "
            "have confirmed renovated condition."
        )
        confidence = min(confidence, 59)
    else:
        confidence += 10
    if len(as_is_comps) < 2:
        reasons.append("As-is value is an AVM benchmark until as-is comps are classified.")
    spread = value_spread(arv_low_cents, arv_point_cents, arv_high_cents)
    if spread is not None and spread > 0.15:
        reasons.append("The supported ARV range is wider than 15%.")
        confidence -= 12
    elif spread is not None and spread > 0.10:
        confidence -= 5
    if (
        avm_value_cents
        and arv_low_cents
        and arv_high_cents
        and not (arv_low_cents * 0.9 <= avm_value_cents <= arv_high_cents * 1.1)
    ):
        reasons.append("The RentCast AVM falls outside the recorded-sale range.")
        confidence -= 8
    if data_disagreements:
        reasons.append("Subject property facts disagree between available data sources.")
        confidence -= 12
    return max(20, min(95, round(confidence))), reasons


def conservative_arv_cents(
    *,
    low: int | None,
    point: int | None,
    confidence_score: int,
) -> int | None:
    if point is None:
        return low
    if confidence_score >= 80:
        haircut = 0.02
    elif confidence_score >= 60:
        haircut = 0.05
    else:
        haircut = 0.08
    adjusted = round(point * (1 - haircut))
    return max(low or 0, adjusted)


def find_data_disagreements(
    *,
    subject_record: dict[str, Any],
    avm_subject: dict[str, Any],
    local_property_type: str | None,
) -> list[str]:
    disagreements: list[str] = []
    record_type = normalize_key(string(subject_record.get("propertyType")))
    avm_type = normalize_key(string(avm_subject.get("propertyType")))
    local_type = normalize_key(local_property_type)
    known_types = {value for value in (record_type, avm_type, local_type) if value}
    if len(known_types) > 1:
        disagreements.append("Property type differs between seller/CRM and provider records.")
    for key, label, tolerance in (
        ("squareFootage", "living area", 0.1),
        ("bedrooms", "bedroom count", 0.0),
        ("bathrooms", "bathroom count", 0.0),
    ):
        record_value = number(subject_record.get(key))
        avm_value = number(avm_subject.get(key))
        if record_value is None or avm_value is None:
            continue
        if key == "squareFootage":
            differs = (relative_difference(record_value, avm_value) or 0) > tolerance
        else:
            differs = abs(record_value - avm_value) > tolerance
        if differs:
            disagreements.append(f"Provider sources disagree on {label}.")
    return disagreements


def merge_subject_facts(
    subject_record: dict[str, Any],
    avm_subject: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(avm_subject)
    merged.update({key: value for key, value in subject_record.items() if value is not None})
    return merged


def record_distance(subject: dict[str, Any], record: dict[str, Any]) -> float | None:
    provided = number(record.get("distance"))
    if provided is not None:
        return round(provided, 3)
    coordinates = (
        number(subject.get("latitude")),
        number(subject.get("longitude")),
        number(record.get("latitude")),
        number(record.get("longitude")),
    )
    if any(value is None for value in coordinates):
        return None
    subject_lat, subject_lng, comp_lat, comp_lng = coordinates
    if (
        subject_lat is None
        or subject_lng is None
        or comp_lat is None
        or comp_lng is None
    ):
        return None
    return round(haversine_miles(subject_lat, subject_lng, comp_lat, comp_lng), 3)


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    origin_lat = radians(lat1)
    destination_lat = radians(lat2)
    value = (
        sin(delta_lat / 2) ** 2
        + cos(origin_lat) * cos(destination_lat) * sin(delta_lng / 2) ** 2
    )
    return 2 * 3958.8 * asin(sqrt(value))


def same_property(subject: dict[str, Any], record: dict[str, Any]) -> bool:
    subject_id = string(subject.get("id"))
    record_id = string(record.get("id"))
    if subject_id and record_id:
        return subject_id == record_id
    return normalize_key(string(subject.get("formattedAddress"))) == normalize_key(
        string(record.get("formattedAddress"))
    )


def days_since(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - parsed.astimezone(UTC)).days)


def normalize_repair_level(value: str | None) -> str:
    normalized = normalize_key(value)
    if normalized in {"new", "turnkey", "excellent", "good", "cosmetic", "light"}:
        return "light"
    if normalized in {
        "major_repairs",
        "heavy_repairs",
        "full_gut",
        "fire_damage",
        "heavy",
    }:
        return "heavy"
    if normalized in {"tear_down", "structural", "foundation"}:
        return "structural"
    return "moderate"


def normalize_condition_override(value: str | None) -> str:
    normalized = normalize_key(value)
    return normalized if normalized in {"as_is", "renovated"} else "unknown"


def normalize_key(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def value_spread(low: int | None, point: int | None, high: int | None) -> float | None:
    if low is None or point is None or high is None or point <= 0:
        return None
    return (high - low) / point


def relative_difference(first: float | int | None, second: float | int | None) -> float | None:
    if first is None or second is None or first == 0:
        return None
    return abs(float(first) - float(second)) / abs(float(first))


def absolute_difference(
    first: float | int | None,
    second: float | int | None,
) -> float | None:
    if first is None or second is None:
        return None
    return abs(float(first) - float(second))


def dollars_to_cents(value: int | None) -> int | None:
    return value * MONEY if value is not None else None


def format_ppsf(value_cents: int) -> str:
    return f"${value_cents / MONEY:,.0f}/sqft"


def median_optional_int(values: list[int]) -> int | None:
    return round(median(values)) if values else None


def latest_mapping_amount(value: Any) -> int:
    if isinstance(value, dict):
        latest_key = max(value, key=tax_year_sort_key, default=None)
        if latest_key is None:
            return 0
        latest_value = value[latest_key]
        if isinstance(latest_value, dict):
            return (
                integer(latest_value.get("total"))
                or integer(latest_value.get("amount"))
                or 0
            )
        return integer(latest_value) or 0
    return integer(value) or 0


def tax_year_sort_key(value: Any) -> tuple[int, str]:
    rendered = str(value)
    return (integer(rendered) or 0, rendered)


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def integer(value: Any) -> int | None:
    if isinstance(value, str):
        try:
            return round(float(value))
        except ValueError:
            return None
    numeric = number(value)
    return round(numeric) if numeric is not None else None


def string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def comp_key(comp: MarketAnalysisCompRead) -> str:
    return comp.provider_id or comp.formatted_address or ""


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
