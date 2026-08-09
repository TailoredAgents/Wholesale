from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.services.land_comparable_evidence import land_use_group

MONEY_ROUNDING_CENTS = Decimal("10000")  # nearest $100


def analyze_land_valuation(
    *,
    selected_comps: list[dict[str, Any]],
    subject_acres: Decimal,
    subject_lot_count: int | None,
    valuation_basis: str,
    subject_parcel_id: str | None,
    subject_use: str | None,
    subject_coordinates_available: bool,
    access_evidence_status: str,
    access_evidence_reference: str | None,
    snapshot_is_fresh: bool,
    subject_identity_conflicted: bool,
    active_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    minimum_comparable_count = int(
        (active_policy or {}).get("minimum_comparable_count") or 3
    )
    indications = [
        item
        for item in selected_comps
        if (indication := integer_value(item.get("subject_indication_cents"))) is not None
        and indication > 0
    ]
    broad_market_count = sum(
        str(item.get("evidence_tier")) in {"preferred", "expanded"}
        for item in indications
    )
    evidence_sufficient = bool(
        len(indications) >= minimum_comparable_count and broad_market_count >= 2
    )
    review_reasons: list[str] = []
    if len(indications) < minimum_comparable_count:
        review_reasons.append(
            f"At least {minimum_comparable_count} eligible closed Land sales are required."
        )
    if broad_market_count < 2:
        review_reasons.append(
            "At least two selected sales must fall inside the preferred or expanded tiers."
        )
    if any(str(item.get("evidence_tier")) == "extended" for item in indications):
        review_reasons.append("Extended-tier comparable evidence requires human review.")
    if any(
        land_use_group(str(item.get("property_use") or "")) == "unknown"
        for item in indications
    ):
        review_reasons.append("One or more selected sales has unknown Land use.")
    if not subject_coordinates_available:
        review_reasons.append("The subject lacks coordinates, so county-level geography was used.")

    low_cents = point_cents = high_cents = None
    dispersion_basis_points = None
    if evidence_sufficient:
        low_cents = rounded_money(weighted_percentile(indications, Decimal("0.25")))
        point_cents = rounded_money(weighted_percentile(indications, Decimal("0.50")))
        high_cents = rounded_money(weighted_percentile(indications, Decimal("0.75")))
        low_cents, point_cents, high_cents = sorted(
            (low_cents, point_cents, high_cents)
        )
        if point_cents > 0:
            dispersion_basis_points = round(
                (high_cents - low_cents) / point_cents * 10_000
            )

    maximum_dispersion = int(
        (active_policy or {}).get("maximum_dispersion_basis_points") or 5000
    )
    dispersion_acceptable = bool(
        dispersion_basis_points is not None
        and dispersion_basis_points <= maximum_dispersion
    )
    if evidence_sufficient and not dispersion_acceptable:
        review_reasons.append(
            "Comparable indications are too dispersed for actionable offer guidance."
        )

    guidance_blockers: list[str] = []
    if active_policy is None:
        guidance_blockers.append("No owner-approved Land offer policy is active.")
    if access_evidence_status != "verified" or not (
        access_evidence_reference and access_evidence_reference.strip()
    ):
        guidance_blockers.append("Legal access has not been human-verified with evidence.")
    if not subject_parcel_id or not subject_parcel_id.strip():
        guidance_blockers.append("The subject parcel/APN is missing.")
    if land_use_group(subject_use) == "unknown":
        guidance_blockers.append(
            "The subject Land use is unknown or has not been mapped to a supported use group."
        )
    if not subject_coordinates_available:
        guidance_blockers.append("Subject coordinates are required for actionable comp geography.")
    if subject_acres <= 0:
        guidance_blockers.append("The subject acreage is missing or invalid.")
    if valuation_basis == "per_lot" and not subject_lot_count:
        guidance_blockers.append("Per-lot valuation requires a verified subject lot count.")
    if not snapshot_is_fresh:
        guidance_blockers.append("The Land property snapshot is stale.")
    if subject_identity_conflicted:
        guidance_blockers.append("The subject parcel identity has unresolved conflicts.")
    if not evidence_sufficient:
        guidance_blockers.append("Closed-sale evidence is insufficient.")
    if evidence_sufficient and not dispersion_acceptable:
        guidance_blockers.append("Comparable dispersion exceeds the active policy limit.")
    if any(str(item.get("evidence_tier")) == "extended" for item in indications):
        guidance_blockers.append(
            "Extended-tier comparable evidence requires human review before offer guidance."
        )
    if any(
        land_use_group(str(item.get("property_use") or "")) == "unknown"
        for item in indications
    ):
        guidance_blockers.append(
            "Every selected sale needs a compatible, identified Land use."
        )

    quick_sale_low_cents = quick_sale_high_cents = None
    opening_offer_cents = seller_contract_ceiling_cents = None
    policy_values = active_policy or {}
    assignment_fee_cents = int(policy_values.get("assignment_fee_cents") or 0)
    closing_title_reserve_cents = int(
        policy_values.get("closing_title_reserve_cents") or 0
    )
    curative_reserve_cents = int(policy_values.get("curative_reserve_cents") or 0)
    uncertainty_reserve_cents = int(
        policy_values.get("uncertainty_reserve_cents") or 0
    )
    if not guidance_blockers and low_cents is not None and point_cents is not None:
        low_discount = Decimal(
            int(policy_values["quick_sale_discount_low_basis_points"])
        ) / Decimal(10_000)
        high_discount = Decimal(
            int(policy_values["quick_sale_discount_high_basis_points"])
        ) / Decimal(10_000)
        quick_sale_low_cents = rounded_money(
            Decimal(low_cents) * (Decimal(1) - high_discount)
        )
        quick_sale_high_cents = rounded_money(
            Decimal(point_cents) * (Decimal(1) - low_discount)
        )
        seller_contract_ceiling_cents = rounded_money(
            Decimal(quick_sale_low_cents)
            - Decimal(assignment_fee_cents)
            - Decimal(closing_title_reserve_cents)
            - Decimal(curative_reserve_cents)
            - Decimal(uncertainty_reserve_cents)
        )
        if seller_contract_ceiling_cents <= 0:
            guidance_blockers.append(
                "Policy reserves consume the supported quick-sale value."
            )
            quick_sale_low_cents = None
            quick_sale_high_cents = None
            seller_contract_ceiling_cents = None
        else:
            opening_reserve = Decimal(
                int(policy_values["opening_reserve_basis_points"])
            ) / Decimal(10_000)
            opening_offer_cents = rounded_money(
                Decimal(seller_contract_ceiling_cents)
                * (Decimal(1) - opening_reserve)
            )

    confidence_score = land_confidence_score(
        selected_comps=indications,
        evidence_sufficient=evidence_sufficient,
        dispersion_acceptable=dispersion_acceptable,
        snapshot_is_fresh=snapshot_is_fresh,
        subject_identity_conflicted=subject_identity_conflicted,
    )
    status = (
        "insufficient_evidence"
        if not evidence_sufficient
        else "needs_review"
        if review_reasons
        else "ready"
    )
    return {
        "status": status,
        "guidance_status": "withheld" if guidance_blockers else "available",
        "supported_value_low_cents": low_cents,
        "supported_value_cents": point_cents,
        "supported_value_high_cents": high_cents,
        "quick_sale_low_cents": quick_sale_low_cents,
        "quick_sale_high_cents": quick_sale_high_cents,
        "opening_offer_cents": opening_offer_cents,
        "seller_contract_ceiling_cents": seller_contract_ceiling_cents,
        "assignment_fee_cents": assignment_fee_cents,
        "closing_title_reserve_cents": closing_title_reserve_cents,
        "curative_reserve_cents": curative_reserve_cents,
        "uncertainty_reserve_cents": uncertainty_reserve_cents,
        "confidence_score": confidence_score,
        "review_reasons": list(dict.fromkeys(review_reasons)),
        "guidance_blockers": list(dict.fromkeys(guidance_blockers)),
        "dispersion_basis_points": dispersion_basis_points,
        "minimum_comparable_count": minimum_comparable_count,
        "broad_market_comp_count": broad_market_count,
        "calculation": {
            "valuation_basis": valuation_basis,
            "acreage_adjustment_factor": 1.0,
            "acreage_adjustment_policy": (
                "No acreage multiplier is applied in land_v1. Evidence is restricted to "
                "declared acreage-ratio tiers."
            ),
            "supported_range_method": "weighted_25th_50th_75th_percentiles",
            "rounding": "nearest_100_dollars_half_up",
        },
    }


def weighted_percentile(
    comps: list[dict[str, Any]],
    percentile: Decimal,
) -> Decimal:
    ordered = sorted(
        comps,
        key=lambda item: int(item.get("subject_indication_cents") or 0),
    )
    weights = [Decimal(str(item.get("weight") or 0)) for item in ordered]
    total_weight = sum(weights, Decimal(0))
    if total_weight <= 0:
        weights = [Decimal(1) for _ in ordered]
        total_weight = Decimal(len(ordered))
    target = total_weight * percentile
    cumulative = Decimal(0)
    for item, weight in zip(ordered, weights, strict=True):
        cumulative += weight
        if cumulative >= target:
            return Decimal(int(item["subject_indication_cents"]))
    return Decimal(int(ordered[-1]["subject_indication_cents"]))


def rounded_money(value: Decimal) -> int:
    rounded_units = (value / MONEY_ROUNDING_CENTS).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    return int(rounded_units * MONEY_ROUNDING_CENTS)


def land_confidence_score(
    *,
    selected_comps: list[dict[str, Any]],
    evidence_sufficient: bool,
    dispersion_acceptable: bool,
    snapshot_is_fresh: bool,
    subject_identity_conflicted: bool,
) -> int:
    score = min(45, len(selected_comps) * 8)
    score += min(
        25,
        sum(
            5
            for item in selected_comps
            if str(item.get("evidence_tier")) in {"preferred", "expanded"}
        ),
    )
    score += 10 if snapshot_is_fresh else 0
    score += 15 if dispersion_acceptable else 0
    score += 5 if evidence_sufficient else 0
    score -= 25 if subject_identity_conflicted else 0
    return max(0, min(100, score))


def integer_value(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
