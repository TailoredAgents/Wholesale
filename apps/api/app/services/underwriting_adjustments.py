from __future__ import annotations

from datetime import UTC, datetime
from math import sqrt
from statistics import median
from typing import Any

from app.schemas.leads import MarketAnalysisCompRead

METHODOLOGY_VERSION = "v3"
SHADOW_VERSION = "v3.0-adjustment-shadow"
MONEY = 100
RATE_EVIDENCE_MAX_COMPS = 12


def build_market_adjusted_conclusion(
    *,
    subject: dict[str, Any],
    selected_comps: list[MarketAnalysisCompRead],
    active_arv_point_cents: int | None,
    active_arv_low_cents: int | None,
    active_arv_high_cents: int | None,
) -> dict[str, Any]:
    """Build the reproducible market-adjusted closed-sale conclusion used by V3."""
    arv_comps = _arv_evidence(selected_comps)
    rate_comps = sorted(
        arv_comps,
        key=lambda comp: (comp.score, comp.weight or 0),
        reverse=True,
    )[:RATE_EVIDENCE_MAX_COMPS]
    time_evidence = _time_evidence(rate_comps)
    gla_evidence = _numeric_evidence(
        key="living_area",
        label="Living area",
        unit="cents_per_square_foot",
        field="square_footage",
        subject_value=_integer(subject.get("squareFootage")),
        comps=rate_comps,
        time_evidence=time_evidence,
        minimum_difference=100,
        minimum_samples=3,
        require_low_collinearity_with=None,
    )
    lot_evidence = _numeric_evidence(
        key="lot_size",
        label="Lot size",
        unit="cents_per_lot_square_foot",
        field="lot_size",
        subject_value=_integer(subject.get("lotSize")),
        comps=rate_comps,
        time_evidence=time_evidence,
        minimum_difference=1_000,
        minimum_samples=4,
        require_low_collinearity_with="square_footage",
    )

    subject_features = _features(subject)
    binary_evidence = [
        _binary_evidence(
            key=key,
            label=label,
            subject_value=subject_features.get(key),
            comps=rate_comps,
            time_evidence=time_evidence,
            gla_evidence=gla_evidence,
        )
        for key, label in (
            ("garage", "Garage"),
            ("pool", "Pool"),
            ("basement", "Basement"),
        )
    ]
    binary_evidence = _remove_collinear_binary_rates(binary_evidence, rate_comps)
    condition_evidence = _unsupported_evidence(
        key="condition_quality",
        label="Condition and quality",
        reason=(
            "The ARV set already excludes known as-is sales. No condition adjustment is "
            "applied without locally paired, consistently classified sales."
        ),
    )
    room_evidence = _unsupported_evidence(
        key="bedrooms_bathrooms",
        label="Bedrooms and bathrooms",
        reason=(
            "Room-count adjustments are withheld to avoid double counting living area; "
            "they require separate local paired-sale support."
        ),
    )
    evidence = [
        time_evidence,
        gla_evidence,
        lot_evidence,
        *binary_evidence,
        condition_evidence,
        room_evidence,
    ]
    evidence_by_key = {item["key"]: item for item in evidence}
    comp_adjustments = [
        _adjust_comp(
            comp,
            subject=subject,
            subject_features=subject_features,
            evidence=evidence_by_key,
        )
        for comp in arv_comps
        if comp.price_cents is not None
    ]
    values = [
        (item["adjusted_indication_cents"], item["weight"])
        for item in comp_adjustments
        if item["adjusted_indication_cents"] is not None
    ]
    point = _weighted_quantile(values, 0.50)
    low = _weighted_quantile(values, 0.25)
    high = _weighted_quantile(values, 0.75)
    support_count = sum(item["status"] == "supported" for item in evidence)
    expansion_count = sum(
        comp.search_level in {"expanded", "extended", "manual"} for comp in arv_comps
    )
    confidence_score, confidence_tier, confidence_factors = _confidence(
        comps=arv_comps,
        evidence=evidence,
        comp_adjustments=comp_adjustments,
        expansion_count=expansion_count,
    )
    low, high = _widen_range(
        low,
        point,
        high,
        confidence_score=confidence_score,
        expansion_count=expansion_count,
    )
    status = "unsupported"
    if len(comp_adjustments) >= 3 and support_count >= 2:
        status = "supported"
    elif comp_adjustments:
        status = "partial"
    warnings = _warnings(
        evidence=evidence,
        comp_adjustments=comp_adjustments,
        expansion_count=expansion_count,
    )
    return {
        "version": METHODOLOGY_VERSION,
        "status": status,
        "valuation_use": "live_human_reviewed_underwriting",
        "method": "market_supported_adjusted_closed_sales",
        "active_methodology_version": METHODOLOGY_VERSION,
        "policy_sources": [
            {
                "title": "Fannie Mae: Adjustments to Comparable Sales",
                "url": (
                    "https://selling-guide.fanniemae.com/sel/b4-1.3-09/"
                    "adjustments-comparable-sales"
                ),
            },
            {
                "title": "RentCast property data schema",
                "url": "https://developers.rentcast.io/reference/property-data-schema",
            },
        ],
        "baseline": {
            "methodology_version": "v2.2",
            "arv_low_cents": active_arv_low_cents,
            "arv_point_cents": active_arv_point_cents,
            "arv_high_cents": active_arv_high_cents,
        },
        "conclusion": {
            "arv_low_cents": low,
            "arv_point_cents": point,
            "arv_high_cents": high,
            "confidence_score": confidence_score,
            "confidence_tier": confidence_tier,
            "comp_count": len(comp_adjustments),
        },
        "comparison": {
            "point_delta_cents": (
                point - active_arv_point_cents
                if point is not None and active_arv_point_cents is not None
                else None
            ),
            "point_delta_percentage": _percentage_delta(point, active_arv_point_cents),
        },
        "rate_evidence": evidence,
        "comp_adjustments": comp_adjustments,
        "confidence_factors": confidence_factors,
        "warnings": warnings,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def build_adjustment_shadow(
    *,
    subject: dict[str, Any],
    selected_comps: list[MarketAnalysisCompRead],
    active_arv_point_cents: int | None,
    active_arv_low_cents: int | None,
    active_arv_high_cents: int | None,
) -> dict[str, Any]:
    """Compatibility runner for saved V2.2 analyses and regression fixtures."""
    result = build_market_adjusted_conclusion(
        subject=subject,
        selected_comps=selected_comps,
        active_arv_point_cents=active_arv_point_cents,
        active_arv_low_cents=active_arv_low_cents,
        active_arv_high_cents=active_arv_high_cents,
    )
    return {
        **result,
        "version": SHADOW_VERSION,
        "valuation_use": "shadow_only_excluded_from_offer_math",
        "active_methodology_version": "v2.2",
    }


def _arv_evidence(
    comps: list[MarketAnalysisCompRead],
) -> list[MarketAnalysisCompRead]:
    renovated = [comp for comp in comps if comp.condition_classification == "renovated"]
    if len(renovated) >= 3:
        return renovated
    return [comp for comp in comps if comp.condition_classification != "as_is"]


def _time_evidence(comps: list[MarketAnalysisCompRead]) -> dict[str, Any]:
    usable = [
        comp
        for comp in comps
        if comp.price_per_square_foot_cents
        and comp.price_per_square_foot_cents > 0
        and comp.days_old is not None
    ]
    observations: list[dict[str, Any]] = []
    for index, left in enumerate(usable):
        for right in usable[index + 1 :]:
            day_gap = abs((left.days_old or 0) - (right.days_old or 0))
            if day_gap < 60 or not _physically_similar(left, right):
                continue
            newer, older = (
                (left, right)
                if (left.days_old or 0) < (right.days_old or 0)
                else (right, left)
            )
            assert newer.price_per_square_foot_cents is not None
            assert older.price_per_square_foot_cents is not None
            monthly_rate = (
                newer.price_per_square_foot_cents / older.price_per_square_foot_cents
            ) ** (30 / day_gap) - 1
            observations.append(
                {
                    "left_comp_key": _comp_key(newer),
                    "right_comp_key": _comp_key(older),
                    "day_span": day_gap,
                    "monthly_rate": round(monthly_rate, 6),
                }
            )
    rates = [float(item["monthly_rate"]) for item in observations]
    observed_span = max((comp.days_old or 0) for comp in usable) - min(
        (comp.days_old or 0) for comp in usable
    ) if usable else 0
    if len(usable) < 4 or len(rates) < 3 or observed_span < 120:
        return _unsupported_evidence(
            key="market_time",
            label="Market conditions / time",
            reason=(
                "At least four physically similar sales, three time-pair observations, "
                "and 120 days of local coverage are required."
            ),
            sample_count=len(usable),
            observations=observations,
        )
    center = float(median(rates))
    if not _stable_rates(rates, center, relative_limit=1.0, zero_absolute_limit=0.005):
        return _unsupported_evidence(
            key="market_time",
            label="Market conditions / time",
            reason="Local time-pair observations are too inconsistent to support a rate.",
            sample_count=len(usable),
            observations=observations,
        )
    return {
        "key": "market_time",
        "label": "Market conditions / time",
        "status": "supported",
        "unit": "monthly_compound_rate",
        "rate": round(center, 6),
        "sample_count": len(usable),
        "pair_count": len(observations),
        "source_comp_keys": [_comp_key(comp) for comp in usable],
        "method": "median paired PPSF trend among physically similar closed sales",
        "observed_range": {"days": observed_span},
        "observations": observations,
        "reason": None,
    }


def _numeric_evidence(
    *,
    key: str,
    label: str,
    unit: str,
    field: str,
    subject_value: int | None,
    comps: list[MarketAnalysisCompRead],
    time_evidence: dict[str, Any],
    minimum_difference: int,
    minimum_samples: int,
    require_low_collinearity_with: str | None,
) -> dict[str, Any]:
    usable = [
        comp
        for comp in comps
        if comp.price_cents is not None and _comp_number(comp, field) is not None
    ]
    if subject_value is None:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=f"The subject {label.lower()} is unavailable.",
            sample_count=len(usable),
        )
    if require_low_collinearity_with:
        correlation = _correlation(
            [
                (
                    _comp_number(comp, field),
                    _comp_number(comp, require_low_collinearity_with),
                )
                for comp in usable
            ]
        )
        if correlation is not None and abs(correlation) >= 0.70:
            return _unsupported_evidence(
                key=key,
                label=label,
                reason=(
                    f"{label} is strongly correlated with living area in this comp set "
                    "and is withheld to prevent double counting."
                ),
                sample_count=len(usable),
                collinearity=round(correlation, 3),
            )
    observations: list[dict[str, Any]] = []
    for index, left in enumerate(usable):
        for right in usable[index + 1 :]:
            left_value = _comp_number(left, field)
            right_value = _comp_number(right, field)
            if left_value is None or right_value is None:
                continue
            difference = left_value - right_value
            if abs(difference) < minimum_difference:
                continue
            if field != "square_footage" and not _physically_similar(left, right):
                continue
            if field == "square_footage" and not _matched_for_gla(left, right):
                continue
            left_price = _time_normalized_price(left, time_evidence)
            right_price = _time_normalized_price(right, time_evidence)
            rate = round((left_price - right_price) / difference)
            if rate <= 0:
                continue
            observations.append(
                {
                    "left_comp_key": _comp_key(left),
                    "right_comp_key": _comp_key(right),
                    "unit_difference": difference,
                    "rate_cents_per_unit": rate,
                }
            )
    rates = [int(item["rate_cents_per_unit"]) for item in observations]
    value_span = (
        max(_comp_number(comp, field) or 0 for comp in usable)
        - min(_comp_number(comp, field) or 0 for comp in usable)
        if usable
        else 0
    )
    required_span = minimum_difference * 2
    if len(usable) < minimum_samples or len(rates) < 3 or value_span < required_span:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                f"At least {minimum_samples} comparable sales, three matched-pair "
                "observations, and meaningful local variation are required."
            ),
            sample_count=len(usable),
            observations=observations,
        )
    center = int(median(rates))
    dispersion = _relative_mad([float(rate) for rate in rates], float(center))
    if dispersion is None or dispersion > 0.75:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason="Matched-pair rates are too inconsistent to support an adjustment.",
            sample_count=len(usable),
            observations=observations,
        )
    max_observed_difference = max(abs(int(item["unit_difference"])) for item in observations)
    return {
        "key": key,
        "label": label,
        "status": "supported",
        "unit": unit,
        "rate": center,
        "sample_count": len(usable),
        "pair_count": len(observations),
        "source_comp_keys": [_comp_key(comp) for comp in usable],
        "method": "median local matched-pair marginal contribution",
        "observed_range": {
            "minimum": min(_comp_number(comp, field) or 0 for comp in usable),
            "maximum": max(_comp_number(comp, field) or 0 for comp in usable),
            "maximum_pair_difference": max_observed_difference,
            "normalization_target": int(
                median(
                    [
                        value
                        for comp in usable
                        if (value := _comp_number(comp, field)) is not None
                    ]
                )
            ),
        },
        "observations": observations,
        "reason": None,
    }


def _binary_evidence(
    *,
    key: str,
    label: str,
    subject_value: bool | None,
    comps: list[MarketAnalysisCompRead],
    time_evidence: dict[str, Any],
    gla_evidence: dict[str, Any],
) -> dict[str, Any]:
    usable = [comp for comp in comps if _comp_feature(comp, key) is not None]
    if subject_value is None:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=f"The subject {label.lower()} fact is unavailable from county data.",
            sample_count=len(usable),
        )
    with_feature = [comp for comp in usable if _comp_feature(comp, key) is True]
    without_feature = [comp for comp in usable if _comp_feature(comp, key) is False]
    observations: list[dict[str, Any]] = []
    for included in with_feature:
        for excluded in without_feature:
            if not _physically_similar(included, excluded):
                continue
            included_value = _normalized_price(included, time_evidence, gla_evidence)
            excluded_value = _normalized_price(excluded, time_evidence, gla_evidence)
            observations.append(
                {
                    "with_feature_comp_key": _comp_key(included),
                    "without_feature_comp_key": _comp_key(excluded),
                    "adjustment_cents": included_value - excluded_value,
                }
            )
    rates = [int(item["adjustment_cents"]) for item in observations]
    if len(with_feature) < 3 or len(without_feature) < 3 or len(rates) < 3:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                "Three local sales with and three without this feature, plus matched "
                "pairs, are required."
            ),
            sample_count=len(usable),
            observations=observations,
        )
    center = int(median(rates))
    dispersion = _relative_mad([float(rate) for rate in rates], float(center))
    if center <= 0 or dispersion is None or dispersion > 0.75:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason="Local feature-pair prices do not show a stable positive market reaction.",
            sample_count=len(usable),
            observations=observations,
        )
    return {
        "key": key,
        "label": label,
        "status": "supported",
        "unit": "cents_per_feature",
        "rate": center,
        "sample_count": len(usable),
        "pair_count": len(observations),
        "source_comp_keys": [_comp_key(comp) for comp in usable],
        "method": "median local matched-pair feature contribution",
        "observed_range": {
            "with_feature": len(with_feature),
            "without_feature": len(without_feature),
        },
        "observations": observations,
        "reason": None,
    }


def _remove_collinear_binary_rates(
    evidence: list[dict[str, Any]], comps: list[MarketAnalysisCompRead]
) -> list[dict[str, Any]]:
    updated = [dict(item) for item in evidence]
    for left_index, left in enumerate(updated):
        if left["status"] != "supported":
            continue
        for right_index in range(left_index + 1, len(updated)):
            right = updated[right_index]
            if right["status"] != "supported":
                continue
            correlation = _correlation(
                [
                    (
                        _bool_number(_comp_feature(comp, str(left["key"]))),
                        _bool_number(_comp_feature(comp, str(right["key"]))),
                    )
                    for comp in comps
                ]
            )
            if correlation is None or abs(correlation) < 0.70:
                continue
            left_pairs = int(left.get("pair_count") or 0)
            right_pairs = int(right.get("pair_count") or 0)
            remove_index = right_index if left_pairs >= right_pairs else left_index
            retained = left if remove_index == right_index else right
            removed = updated[remove_index]
            updated[remove_index] = _unsupported_evidence(
                key=str(removed["key"]),
                label=str(removed["label"]),
                reason=(
                    f"Withheld because it overlaps strongly with {retained['label']} in "
                    "this comp set and could double count the same market reaction."
                ),
                sample_count=int(removed.get("sample_count") or 0),
                collinearity=round(correlation, 3),
            )
    return updated


def _adjust_comp(
    comp: MarketAnalysisCompRead,
    *,
    subject: dict[str, Any],
    subject_features: dict[str, bool | None],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    assert comp.price_cents is not None
    components: list[dict[str, Any]] = []
    time = evidence["market_time"]
    if time["status"] == "supported" and comp.days_old is not None:
        observed_days = int((time.get("observed_range") or {}).get("days") or 0)
        applied_days = min(comp.days_old, observed_days)
        rate = float(time["rate"])
        amount = round(comp.price_cents * ((1 + rate) ** (applied_days / 30) - 1))
        components.append(
            _component(
                key="market_time",
                label="Market conditions / time",
                amount=amount,
                rate=rate,
                unit="monthly_compound_rate",
                difference=comp.days_old,
                applied_difference=applied_days,
                extrapolation_limited=applied_days != comp.days_old,
            )
        )
    subject_sqft = _integer(subject.get("squareFootage"))
    _append_numeric_component(
        components,
        comp=comp,
        evidence=evidence["living_area"],
        subject_value=subject_sqft,
        comp_value=comp.square_footage,
    )
    subject_lot = _integer(subject.get("lotSize"))
    _append_numeric_component(
        components,
        comp=comp,
        evidence=evidence["lot_size"],
        subject_value=subject_lot,
        comp_value=comp.lot_size,
    )
    for key in ("garage", "pool", "basement"):
        rate_evidence = evidence[key]
        subject_value = subject_features.get(key)
        comp_value = _comp_feature(comp, key)
        if (
            rate_evidence["status"] != "supported"
            or subject_value is None
            or comp_value is None
            or subject_value == comp_value
        ):
            continue
        rate = int(rate_evidence["rate"])
        amount = rate if subject_value and not comp_value else -rate
        components.append(
            _component(
                key=key,
                label=str(rate_evidence["label"]),
                amount=amount,
                rate=rate,
                unit="cents_per_feature",
                difference=1 if subject_value else -1,
                applied_difference=1 if subject_value else -1,
                extrapolation_limited=False,
            )
        )
    total = sum(int(item["amount_cents"]) for item in components)
    adjusted = comp.price_cents + total
    adjustment_ratio = abs(total) / comp.price_cents if comp.price_cents else 0
    return {
        "comp_key": _comp_key(comp),
        "formatted_address": comp.formatted_address,
        "sale_price_cents": comp.price_cents,
        "sale_date": comp.sale_date,
        "weight": comp.weight or max(comp.score / 100, 0.01),
        "components": components,
        "total_adjustment_cents": total,
        "adjusted_indication_cents": adjusted,
        "gross_adjustment_percentage": round(adjustment_ratio * 100, 2),
        "requires_review": adjustment_ratio > 0.25 or any(
            item["extrapolation_limited"] for item in components
        ),
    }


def _append_numeric_component(
    components: list[dict[str, Any]],
    *,
    comp: MarketAnalysisCompRead,
    evidence: dict[str, Any],
    subject_value: int | None,
    comp_value: int | None,
) -> None:
    if evidence["status"] != "supported" or subject_value is None or comp_value is None:
        return
    difference = subject_value - comp_value
    max_difference = int(
        (evidence.get("observed_range") or {}).get("maximum_pair_difference") or 0
    )
    applied_difference = max(-max_difference, min(max_difference, difference))
    rate = int(evidence["rate"])
    components.append(
        _component(
            key=str(evidence["key"]),
            label=str(evidence["label"]),
            amount=applied_difference * rate,
            rate=rate,
            unit=str(evidence["unit"]),
            difference=difference,
            applied_difference=applied_difference,
            extrapolation_limited=applied_difference != difference,
        )
    )


def _component(
    *,
    key: str,
    label: str,
    amount: int,
    rate: int | float,
    unit: str,
    difference: int | float,
    applied_difference: int | float,
    extrapolation_limited: bool,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "amount_cents": amount,
        "rate": rate,
        "unit": unit,
        "difference": difference,
        "applied_difference": applied_difference,
        "extrapolation_limited": extrapolation_limited,
        "source_rate_key": key,
    }


def _confidence(
    *,
    comps: list[MarketAnalysisCompRead],
    evidence: list[dict[str, Any]],
    comp_adjustments: list[dict[str, Any]],
    expansion_count: int,
) -> tuple[int, str, list[dict[str, Any]]]:
    count_score = min(30, len(comps) * 6)
    grade_score = min(20, sum(comp.comp_grade in {"A", "B"} for comp in comps) * 5)
    evidence_score = min(25, sum(item["status"] == "supported" for item in evidence) * 8)
    locality_score = max(0, 15 - expansion_count * 4)
    review_penalty = min(
        20, sum(bool(item["requires_review"]) for item in comp_adjustments) * 5
    )
    score = max(
        10,
        min(
            90,
            10
            + count_score
            + grade_score
            + evidence_score
            + locality_score
            - review_penalty,
        ),
    )
    if score >= 80:
        tier = "high"
    elif score >= 60:
        tier = "moderate"
    elif score >= 40:
        tier = "low"
    else:
        tier = "insufficient"
    factors = [
        {
            "key": "closed_sale_depth",
            "label": "Closed-sale depth",
            "score": count_score,
            "maximum": 30,
            "summary": f"{len(comps)} closed sale(s) support the shadow conclusion.",
        },
        {
            "key": "comparable_quality",
            "label": "Comparable quality",
            "score": grade_score,
            "maximum": 20,
            "summary": f"{sum(comp.comp_grade in {'A', 'B'} for comp in comps)} A/B comp(s).",
        },
        {
            "key": "adjustment_support",
            "label": "Adjustment support",
            "score": evidence_score,
            "maximum": 25,
            "summary": (
                f"{sum(item['status'] == 'supported' for item in evidence)} "
                "supported local rate(s)."
            ),
        },
        {
            "key": "search_locality",
            "label": "Search locality",
            "score": locality_score,
            "maximum": 15,
            "summary": (
                f"{expansion_count} comp(s) required expanded, extended, or manual "
                "sourcing."
            ),
        },
        {
            "key": "adjustment_review",
            "label": "Adjustment review",
            "score": -review_penalty,
            "maximum": 0,
            "summary": (
                f"{sum(bool(item['requires_review']) for item in comp_adjustments)} "
                "indication(s) need extrapolation or magnitude review."
            ),
        },
    ]
    return score, tier, factors


def _widen_range(
    low: int | None,
    point: int | None,
    high: int | None,
    *,
    confidence_score: int,
    expansion_count: int,
) -> tuple[int | None, int | None]:
    if point is None:
        return low, high
    uncertainty = 0.05
    if confidence_score < 60:
        uncertainty += 0.04
    elif confidence_score < 80:
        uncertainty += 0.02
    if expansion_count:
        uncertainty += min(0.04, expansion_count * 0.01)
    floor = round(point * (1 - uncertainty))
    ceiling = round(point * (1 + uncertainty))
    return min(low if low is not None else floor, floor), max(
        high if high is not None else ceiling, ceiling
    )


def _warnings(
    *,
    evidence: list[dict[str, Any]],
    comp_adjustments: list[dict[str, Any]],
    expansion_count: int,
) -> list[str]:
    warnings = [
        "Stonegate uses these adjustments in V3 valuation math; a person must review the "
        "supporting sales before approving an offer."
    ]
    unsupported = [str(item["label"]) for item in evidence if item["status"] != "supported"]
    if unsupported:
        warnings.append("No supported adjustment was applied for: " + ", ".join(unsupported) + ".")
    if expansion_count:
        warnings.append(
            f"{expansion_count} comp(s) came from an expanded, extended, or manual search."
        )
    if any(item["requires_review"] for item in comp_adjustments):
        warnings.append(
            "One or more adjusted indications require review for extrapolation or "
            "adjustment magnitude."
        )
    return warnings


def _unsupported_evidence(
    *,
    key: str,
    label: str,
    reason: str,
    sample_count: int = 0,
    observations: list[dict[str, Any]] | None = None,
    collinearity: float | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "unsupported",
        "unit": None,
        "rate": None,
        "sample_count": sample_count,
        "pair_count": len(observations or []),
        "source_comp_keys": [],
        "method": None,
        "observed_range": None,
        "observations": observations or [],
        "collinearity": collinearity,
        "reason": reason,
    }


def _physically_similar(left: MarketAnalysisCompRead, right: MarketAnalysisCompRead) -> bool:
    if left.condition_classification != right.condition_classification:
        return False
    return (
        _relative_difference(left.square_footage, right.square_footage) <= 0.15
        and _absolute_difference(left.year_built, right.year_built) <= 15
        and _relative_difference(left.lot_size, right.lot_size) <= 0.35
    )


def _matched_for_gla(left: MarketAnalysisCompRead, right: MarketAnalysisCompRead) -> bool:
    if left.condition_classification != right.condition_classification:
        return False
    if _absolute_difference(left.year_built, right.year_built) > 15:
        return False
    if _relative_difference(left.lot_size, right.lot_size) > 0.35:
        return False
    if _absolute_difference(left.days_old, right.days_old) > 180:
        return False
    return True


def _time_normalized_price(comp: MarketAnalysisCompRead, evidence: dict[str, Any]) -> int:
    assert comp.price_cents is not None
    if evidence["status"] != "supported" or comp.days_old is None:
        return comp.price_cents
    observed_days = int((evidence.get("observed_range") or {}).get("days") or 0)
    days = min(comp.days_old, observed_days)
    rate_value = evidence.get("rate")
    rate = float(rate_value) if isinstance(rate_value, (int, float)) else 0.0
    return int(round(comp.price_cents * (1 + rate) ** (days / 30)))


def _normalized_price(
    comp: MarketAnalysisCompRead,
    time_evidence: dict[str, Any],
    gla_evidence: dict[str, Any],
) -> int:
    value = _time_normalized_price(comp, time_evidence)
    if gla_evidence["status"] == "supported" and comp.square_footage is not None:
        target = int(
            (gla_evidence.get("observed_range") or {}).get("normalization_target")
            or comp.square_footage
        )
        value += (target - comp.square_footage) * int(gla_evidence["rate"])
    return value


def _features(record: dict[str, Any]) -> dict[str, bool | None]:
    raw_features = record.get("features")
    raw: dict[str, Any] = raw_features if isinstance(raw_features, dict) else {}
    foundation = str(raw.get("foundationType") or "").lower()
    return {
        "garage": _boolean(raw.get("garage")),
        "pool": _boolean(raw.get("pool")),
        "basement": "basement" in foundation if foundation else None,
    }


def _comp_feature(comp: MarketAnalysisCompRead, key: str) -> bool | None:
    return {
        "garage": comp.garage,
        "pool": comp.pool,
        "basement": comp.basement,
    }.get(key)


def _comp_number(comp: MarketAnalysisCompRead, field: str) -> int | None:
    value = getattr(comp, field, None)
    return _integer(value)


def _comp_key(comp: MarketAnalysisCompRead) -> str:
    return comp.provider_id or comp.formatted_address or "unknown-comp"


def _weighted_quantile(values: list[tuple[int, float]], target: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values, key=lambda item: item[0])
    total = sum(max(weight, 0.01) for _, weight in ordered)
    threshold = total * target
    running = 0.0
    for value, weight in ordered:
        running += max(weight, 0.01)
        if running >= threshold:
            return value
    return ordered[-1][0]


def _relative_mad(values: list[float], center: float) -> float | None:
    if not values or center == 0:
        return None
    return abs(float(median([abs(value - center) for value in values])) / center)


def _stable_rates(
    values: list[float],
    center: float,
    *,
    relative_limit: float,
    zero_absolute_limit: float,
) -> bool:
    if not values:
        return False
    absolute_mad = float(median([abs(value - center) for value in values]))
    if abs(center) < zero_absolute_limit:
        return absolute_mad <= zero_absolute_limit
    relative_mad = _relative_mad(values, center)
    return relative_mad is not None and relative_mad <= relative_limit


def _correlation(pairs: list[tuple[int | float | None, int | float | None]]) -> float | None:
    usable = [
        (float(left), float(right))
        for left, right in pairs
        if left is not None and right is not None
    ]
    if len(usable) < 4:
        return None
    left_mean = sum(left for left, _ in usable) / len(usable)
    right_mean = sum(right for _, right in usable) / len(usable)
    numerator = sum((left - left_mean) * (right - right_mean) for left, right in usable)
    left_sum = sum((left - left_mean) ** 2 for left, _ in usable)
    right_sum = sum((right - right_mean) ** 2 for _, right in usable)
    denominator = sqrt(left_sum * right_sum)
    return numerator / denominator if denominator else None


def _relative_difference(left: int | None, right: int | None) -> float:
    if left is None or right is None or max(abs(left), abs(right)) == 0:
        return 0.0
    return abs(left - right) / max(abs(left), abs(right))


def _absolute_difference(left: int | None, right: int | None) -> int:
    if left is None or right is None:
        return 0
    return abs(left - right)


def _percentage_delta(value: int | None, baseline: int | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return round((value - baseline) / baseline * 100, 2)


def _integer(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _bool_number(value: bool | None) -> int | None:
    return int(value) if value is not None else None
