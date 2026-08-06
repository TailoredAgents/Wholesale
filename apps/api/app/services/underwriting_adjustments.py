from __future__ import annotations

from datetime import UTC, datetime
from math import sqrt
from statistics import median
from typing import Any

from app.schemas.leads import MarketAnalysisCompRead

METHODOLOGY_VERSION = "v3"
SHADOW_VERSION = "v3.0-adjustment-shadow"
CALCULATION_VERSION = "v3.1-adjusted-distribution"
MONEY = 100
RATE_EVIDENCE_MAX_COMPS = 12
MAX_ABSOLUTE_MONTHLY_MARKET_RATE = 0.03


def build_market_adjusted_conclusion(
    *,
    subject: dict[str, Any],
    selected_comps: list[MarketAnalysisCompRead],
    active_arv_point_cents: int | None,
    active_arv_low_cents: int | None,
    active_arv_high_cents: int | None,
) -> dict[str, Any]:
    """Build the reproducible market-adjusted closed-sale conclusion used by V3."""
    withheld_conflict_comps = [
        comp
        for comp in selected_comps
        if any(_material_source_conflict(conflict) for conflict in comp.source_conflicts)
    ]
    clean_comps = [comp for comp in selected_comps if comp not in withheld_conflict_comps]
    arv_comps = _arv_evidence(clean_comps)
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
        gla_evidence=None,
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
        gla_evidence=gla_evidence,
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
            lot_evidence=lot_evidence,
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
        withheld_conflict_comps=withheld_conflict_comps,
        evidence=evidence,
        comp_adjustments=comp_adjustments,
        expansion_count=expansion_count,
        low=low,
        point=point,
        high=high,
    )
    range_diagnostics = _range_diagnostics(
        comps=arv_comps,
        comp_adjustments=comp_adjustments,
        evidence=evidence,
        low=low,
        point=point,
        high=high,
        expansion_count=expansion_count,
        withheld_conflict_comps=withheld_conflict_comps,
    )
    blocking_evidence = any(item.get("blocking") is True for item in evidence)
    status = "unsupported"
    if not blocking_evidence and len(comp_adjustments) >= 3 and support_count >= 2:
        status = "supported"
    elif not blocking_evidence and comp_adjustments:
        status = "partial"
    warnings = _warnings(
        evidence=evidence,
        comp_adjustments=comp_adjustments,
        expansion_count=expansion_count,
        range_diagnostics=range_diagnostics,
    )
    return {
        "version": METHODOLOGY_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "status": status,
        "valuation_use": "live_human_reviewed_underwriting",
        "method": "market_supported_adjusted_closed_sales",
        "requires_manual_review": any(
            item.get("severity") == "high" for item in range_diagnostics["drivers"]
        ),
        "active_methodology_version": METHODOLOGY_VERSION,
        "policy_sources": [
            {
                "title": "Fannie Mae: Adjustments to Comparable Sales",
                "url": (
                    "https://selling-guide.fanniemae.com/sel/b4-1.3-09/adjustments-comparable-sales"
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
        "range_diagnostics": range_diagnostics,
        "range_drivers": range_diagnostics["drivers"],
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
                (left, right) if (left.days_old or 0) < (right.days_old or 0) else (right, left)
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
    participant_keys, connected = _pair_participant_keys(
        observations,
        left_key="left_comp_key",
        right_key="right_comp_key",
    )
    participants = [comp for comp in usable if _comp_key(comp) in participant_keys]
    rates = [float(item["monthly_rate"]) for item in observations]
    observed_span = (
        max((comp.days_old or 0) for comp in participants)
        - min((comp.days_old or 0) for comp in participants)
        if participants
        else 0
    )
    if len(participants) < 4 or len(rates) < 3 or observed_span < 120 or not connected:
        return _unsupported_evidence(
            key="market_time",
            label="Market conditions / time",
            reason=(
                "At least four physically similar sales, three time-pair observations, "
                "and 120 days of local coverage are required."
            ),
            sample_count=len(participants),
            observations=observations,
        )
    center = float(median(rates))
    if abs(center) > MAX_ABSOLUTE_MONTHLY_MARKET_RATE:
        return {
            **_unsupported_evidence(
                key="market_time",
                label="Market conditions / time",
                reason=(
                    "The inferred monthly market rate exceeds Stonegate's 3% plausibility "
                    "boundary and is withheld from valuation."
                ),
                sample_count=len(participants),
                observations=observations,
            ),
            "blocking": True,
        }
    if not _stable_rates(rates, center, relative_limit=1.0, zero_absolute_limit=0.005):
        return _unsupported_evidence(
            key="market_time",
            label="Market conditions / time",
            reason="Local time-pair observations are too inconsistent to support a rate.",
            sample_count=len(participants),
            observations=observations,
        )
    return {
        "key": "market_time",
        "label": "Market conditions / time",
        "status": "supported",
        "unit": "monthly_compound_rate",
        "rate": round(center, 6),
        "sample_count": len(participants),
        "pair_count": len(observations),
        "source_comp_keys": [_comp_key(comp) for comp in participants],
        "method": "median paired PPSF trend among physically similar closed sales",
        "observed_range": {
            "days": observed_span,
            "anchor_days_old": min((comp.days_old or 0) for comp in participants),
            "cohort": _cohort_descriptor(participants),
        },
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
    gla_evidence: dict[str, Any] | None,
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
    observations: list[dict[str, Any]] = []
    for index, left in enumerate(usable):
        for right in usable[index + 1 :]:
            time_applies_to_pair = _evidence_applies_to_pair(time_evidence, left, right)
            gla_applies_to_pair = gla_evidence is not None and _evidence_applies_to_pair(
                gla_evidence, left, right
            )
            left_value = _comp_number(left, field)
            right_value = _comp_number(right, field)
            if left_value is None or right_value is None:
                continue
            difference = left_value - right_value
            if abs(difference) < minimum_difference:
                continue
            if field == "lot_size" and not _matched_for_lot(
                left,
                right,
                time_supported=time_applies_to_pair,
                gla_supported=gla_applies_to_pair,
            ):
                continue
            if field not in {"square_footage", "lot_size"} and not _physically_similar(left, right):
                continue
            if field == "square_footage" and not _matched_for_gla(
                left,
                right,
                time_supported=time_applies_to_pair,
            ):
                continue
            left_price = _time_normalized_price(left, time_evidence)
            right_price = _time_normalized_price(right, time_evidence)
            if field == "lot_size" and gla_evidence is not None:
                left_price = _gla_normalized_price(left, time_evidence, gla_evidence)
                right_price = _gla_normalized_price(right, time_evidence, gla_evidence)
            rate = round((left_price - right_price) / difference)
            observations.append(
                {
                    "left_comp_key": _comp_key(left),
                    "right_comp_key": _comp_key(right),
                    "unit_difference": difference,
                    "rate_cents_per_unit": rate,
                }
            )
    rates = [int(item["rate_cents_per_unit"]) for item in observations]
    participant_keys, connected = _pair_participant_keys(
        observations,
        left_key="left_comp_key",
        right_key="right_comp_key",
    )
    participants = [comp for comp in usable if _comp_key(comp) in participant_keys]
    value_span = (
        max(_comp_number(comp, field) or 0 for comp in participants)
        - min(_comp_number(comp, field) or 0 for comp in participants)
        if participants
        else 0
    )
    required_span = minimum_difference * 2
    if (
        len(participants) < minimum_samples
        or len(rates) < 3
        or value_span < required_span
        or not connected
    ):
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                f"At least {minimum_samples} comparable sales, three matched-pair "
                "observations, and meaningful local variation are required. Matched pairs "
                "must control other physical differences to prevent double counting."
            ),
            sample_count=len(participants),
            observations=observations,
        )
    if require_low_collinearity_with:
        correlation = _correlation(
            [
                (
                    _comp_number(comp, field),
                    _comp_number(comp, require_low_collinearity_with),
                )
                for comp in participants
            ]
        )
        if correlation is not None and abs(correlation) >= 0.70:
            return _unsupported_evidence(
                key=key,
                label=label,
                reason=(
                    f"{label} is strongly correlated with living area in the matched-pair "
                    "cohort and is withheld to prevent double counting."
                ),
                sample_count=len(participants),
                observations=observations,
                collinearity=round(correlation, 3),
            )
    center = int(median(rates))
    positive_pair_count = sum(rate > 0 for rate in rates)
    positive_pair_share = positive_pair_count / len(rates)
    dispersion = _relative_mad([float(rate) for rate in rates], float(center))
    if center <= 0 or positive_pair_share < 0.75 or dispersion is None or dispersion > 0.75:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                "The complete signed matched-pair distribution does not show a stable, "
                "predominantly positive market contribution."
            ),
            sample_count=len(participants),
            observations=observations,
        )
    max_observed_difference = max(abs(int(item["unit_difference"])) for item in observations)
    return {
        "key": key,
        "label": label,
        "status": "supported",
        "unit": unit,
        "rate": center,
        "sample_count": len(participants),
        "pair_count": len(observations),
        "positive_pair_count": positive_pair_count,
        "nonpositive_pair_count": len(rates) - positive_pair_count,
        "source_comp_keys": [_comp_key(comp) for comp in participants],
        "method": "median local matched-pair marginal contribution",
        "observed_range": {
            "minimum": min(_comp_number(comp, field) or 0 for comp in participants),
            "maximum": max(_comp_number(comp, field) or 0 for comp in participants),
            "maximum_pair_difference": max_observed_difference,
            "normalization_target": int(
                median(
                    [
                        value
                        for comp in participants
                        if (value := _comp_number(comp, field)) is not None
                    ]
                )
            ),
            "cohort": _cohort_descriptor(participants),
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
    lot_evidence: dict[str, Any],
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
            time_applies_to_pair = _evidence_applies_to_pair(time_evidence, included, excluded)
            gla_applies_to_pair = _evidence_applies_to_pair(gla_evidence, included, excluded)
            lot_applies_to_pair = _evidence_applies_to_pair(lot_evidence, included, excluded)
            if not _matched_for_binary(
                included,
                excluded,
                ignored_feature=key,
                time_supported=time_applies_to_pair,
                gla_supported=gla_applies_to_pair,
                lot_supported=lot_applies_to_pair,
            ):
                continue
            included_value = _normalized_price(included, time_evidence, gla_evidence, lot_evidence)
            excluded_value = _normalized_price(excluded, time_evidence, gla_evidence, lot_evidence)
            observations.append(
                {
                    "with_feature_comp_key": _comp_key(included),
                    "without_feature_comp_key": _comp_key(excluded),
                    "adjustment_cents": included_value - excluded_value,
                }
            )
    rates = [int(item["adjustment_cents"]) for item in observations]
    participant_with = {str(item["with_feature_comp_key"]) for item in observations}
    participant_without = {str(item["without_feature_comp_key"]) for item in observations}
    participant_keys = participant_with | participant_without
    participants = [comp for comp in usable if _comp_key(comp) in participant_keys]
    if len(participant_with) < 3 or len(participant_without) < 3 or len(rates) < 3:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                "Three local sales with and three without this feature, plus matched "
                "pairs, are required."
            ),
            sample_count=len(participants),
            observations=observations,
        )
    center = int(median(rates))
    dispersion = _relative_mad([float(rate) for rate in rates], float(center))
    positive_pair_count = sum(rate > 0 for rate in rates)
    negative_pair_count = sum(rate < 0 for rate in rates)
    dominant_sign_share = max(positive_pair_count, negative_pair_count) / len(rates)
    if center == 0 or dominant_sign_share < 0.75 or dispersion is None or dispersion > 0.75:
        return _unsupported_evidence(
            key=key,
            label=label,
            reason=(
                "The complete signed feature-pair distribution does not show a stable, "
                "predominantly one-direction market reaction."
            ),
            sample_count=len(participants),
            observations=observations,
        )
    return {
        "key": key,
        "label": label,
        "status": "supported",
        "unit": "cents_per_feature",
        "rate": center,
        "sample_count": len(participants),
        "pair_count": len(observations),
        "positive_pair_count": positive_pair_count,
        "negative_pair_count": negative_pair_count,
        "zero_pair_count": len(rates) - positive_pair_count - negative_pair_count,
        "source_comp_keys": [_comp_key(comp) for comp in participants],
        "method": "median local matched-pair feature contribution",
        "observed_range": {
            "with_feature": len(participant_with),
            "without_feature": len(participant_without),
            "living_area": _participant_bounds(participants, "square_footage"),
            "lot_size": _participant_bounds(participants, "lot_size"),
            "year_built": _participant_bounds(participants, "year_built"),
            "days_old": _participant_bounds(participants, "days_old"),
            "cohort": _cohort_descriptor(participants),
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
        observed_range = time.get("observed_range") or {}
        observed_days = int(observed_range.get("days") or 0)
        anchor_days = int(observed_range.get("anchor_days_old") or 0)
        requested_days = max(0, comp.days_old - anchor_days)
        applied_days = min(requested_days, observed_days)
        rate = float(time["rate"])
        cohort_applicable = _comp_within_evidence_cohort(
            comp, time
        ) and _subject_within_evidence_cohort(subject, time)
        amount = (
            round(comp.price_cents * ((1 + rate) ** (applied_days / 30) - 1))
            if cohort_applicable
            else 0
        )
        components.append(
            _component(
                key="market_time",
                label="Market conditions / time",
                amount=amount,
                rate=rate,
                unit="monthly_compound_rate",
                difference=requested_days,
                applied_difference=applied_days if cohort_applicable else 0,
                extrapolation_limited=(not cohort_applicable or applied_days != requested_days),
            )
        )
        if not cohort_applicable:
            components[-1]["withheld_reason"] = (
                "Time rate withheld outside the observed matched-pair cohort."
            )
    subject_sqft = _integer(subject.get("squareFootage"))
    _append_numeric_component(
        components,
        comp=comp,
        subject=subject,
        evidence=evidence["living_area"],
        subject_value=subject_sqft,
        comp_value=comp.square_footage,
    )
    subject_lot = _integer(subject.get("lotSize"))
    _append_numeric_component(
        components,
        comp=comp,
        subject=subject,
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
        if not _binary_rate_applicable(
            comp=comp,
            subject=subject,
            evidence=rate_evidence,
        ):
            withheld = _component(
                key=key,
                label=str(rate_evidence["label"]),
                amount=0,
                rate=rate,
                unit="cents_per_feature",
                difference=1 if subject_value else -1,
                applied_difference=0,
                extrapolation_limited=True,
            )
            withheld["withheld_reason"] = (
                "Feature rate withheld outside the observed matched-pair cohort."
            )
            components.append(withheld)
            continue
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
        "verification_status": comp.verification_status,
        "evidence_source": comp.evidence_source,
        "weight": comp.weight or max(comp.score / 100, 0.01),
        "components": components,
        "total_adjustment_cents": total,
        "adjusted_indication_cents": adjusted,
        "gross_adjustment_percentage": round(adjustment_ratio * 100, 2),
        "requires_review": adjustment_ratio > 0.25
        or any(item["extrapolation_limited"] for item in components),
    }


def _append_numeric_component(
    components: list[dict[str, Any]],
    *,
    comp: MarketAnalysisCompRead,
    subject: dict[str, Any],
    evidence: dict[str, Any],
    subject_value: int | None,
    comp_value: int | None,
) -> None:
    if evidence["status"] != "supported" or subject_value is None or comp_value is None:
        return
    difference = subject_value - comp_value
    if not (
        _comp_within_evidence_cohort(comp, evidence)
        and _subject_within_evidence_cohort(subject, evidence)
    ):
        withheld = _component(
            key=str(evidence["key"]),
            label=str(evidence["label"]),
            amount=0,
            rate=int(evidence["rate"]),
            unit=str(evidence["unit"]),
            difference=difference,
            applied_difference=0,
            extrapolation_limited=True,
        )
        withheld["withheld_reason"] = (
            "Numeric rate withheld outside the observed matched-pair cohort."
        )
        components.append(withheld)
        return
    max_difference = int((evidence.get("observed_range") or {}).get("maximum_pair_difference") or 0)
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
    withheld_conflict_comps: list[MarketAnalysisCompRead],
    evidence: list[dict[str, Any]],
    comp_adjustments: list[dict[str, Any]],
    expansion_count: int,
    low: int | None,
    point: int | None,
    high: int | None,
) -> tuple[int, str, list[dict[str, Any]]]:
    count_score = min(30, len(comps) * 6)
    grade_score = min(20, sum(comp.comp_grade in {"A", "B"} for comp in comps) * 5)
    evidence_score = min(25, sum(item["status"] == "supported" for item in evidence) * 8)
    locality_score = max(0, 15 - expansion_count * 4)
    corroborated_count = sum(comp.corroborated for comp in comps)
    source_conflict_count = sum(
        _material_source_conflict(conflict)
        for comp in [*comps, *withheld_conflict_comps]
        for conflict in comp.source_conflicts
    )
    source_agreement_score = (
        5
        if corroborated_count >= 2 and source_conflict_count == 0
        else 3
        if corroborated_count
        else 0
    )
    source_conflict_penalty = min(10, source_conflict_count * 2)
    range_percentage = _range_percentage(low, point, high)
    range_score = (
        max(0, round(10 * (1 - min(range_percentage / 20, 1))))
        if range_percentage is not None
        else 0
    )
    review_penalty = min(20, sum(bool(item["requires_review"]) for item in comp_adjustments) * 5)
    score = max(
        10,
        min(
            90,
            10
            + count_score
            + grade_score
            + evidence_score
            + locality_score
            + range_score
            + source_agreement_score
            - review_penalty
            - source_conflict_penalty,
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
            "summary": f"{len(comps)} closed sale(s) support the adjusted-sale conclusion.",
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
                f"{expansion_count} comp(s) required expanded, extended, or manual sourcing."
            ),
        },
        {
            "key": "range_precision",
            "label": "Adjusted-range precision",
            "score": range_score,
            "maximum": 10,
            "summary": (
                f"The supported middle range spans {range_percentage:.1f}% of the ARV point."
                if range_percentage is not None
                else "The adjusted-sale range could not be measured."
            ),
        },
        {
            "key": "source_agreement",
            "label": "Cross-source agreement",
            "score": source_agreement_score - source_conflict_penalty,
            "maximum": 5,
            "summary": (
                f"{corroborated_count} sale(s) are corroborated across providers; "
                f"{source_conflict_count} material field conflict(s) remain."
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


def _material_source_conflict(conflict: dict[str, Any]) -> bool:
    """Treat legacy conflicts as material while honoring the new tolerance marker."""
    return conflict.get("material") is not False


def _range_diagnostics(
    *,
    comps: list[MarketAnalysisCompRead],
    comp_adjustments: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    low: int | None,
    point: int | None,
    high: int | None,
    expansion_count: int,
    withheld_conflict_comps: list[MarketAnalysisCompRead],
) -> dict[str, Any]:
    raw_values = [comp.price_cents for comp in comps if comp.price_cents is not None]
    adjusted_values = [
        int(item["adjusted_indication_cents"])
        for item in comp_adjustments
        if isinstance(item.get("adjusted_indication_cents"), int)
    ]
    raw_span = _value_span(raw_values)
    adjusted_span = _value_span(adjusted_values)
    supported_range_width = high - low if low is not None and high is not None else None
    supported_range_percentage = _range_percentage(low, point, high)
    total_weight = sum(max(float(item.get("weight") or 0), 0.01) for item in comp_adjustments)
    for item in comp_adjustments:
        indication = _integer(item.get("adjusted_indication_cents"))
        weight = max(float(item.get("weight") or 0), 0.01)
        item["relative_weight_percentage"] = round(weight / total_weight * 100, 2)
        item["distance_from_point_cents"] = (
            indication - point if indication is not None and point is not None else None
        )
        item["distance_from_point_percentage"] = _percentage_delta(indication, point)
        item["range_position"] = _range_position(indication, low=low, point=point, high=high)

    drivers: list[dict[str, Any]] = []
    if len(comp_adjustments) < 3:
        drivers.append(
            {
                "key": "closed_sale_depth",
                "label": "Limited closed-sale depth",
                "severity": "high",
                "impact_cents": supported_range_width,
                "comp_keys": [str(item["comp_key"]) for item in comp_adjustments],
                "summary": (
                    f"Only {len(comp_adjustments)} usable adjusted closed-sale indication(s) "
                    "are available; the result remains working guidance."
                ),
            }
        )
    if supported_range_percentage is not None:
        severity = (
            "high"
            if supported_range_percentage > 15
            else "review"
            if supported_range_percentage > 8
            else "info"
        )
        drivers.append(
            {
                "key": "adjusted_sale_dispersion",
                "label": "Adjusted-sale dispersion",
                "severity": severity,
                "impact_cents": supported_range_width,
                "comp_keys": _range_anchor_keys(comp_adjustments),
                "summary": (
                    f"The weighted middle 50% of adjusted indications spans "
                    f"{supported_range_percentage:.1f}% of the Stonegate ARV point."
                ),
            }
        )
    unsupported = [item for item in evidence if item.get("status") != "supported"]
    if unsupported:
        drivers.append(
            {
                "key": "withheld_adjustments",
                "label": "Withheld adjustments",
                "severity": "review",
                "impact_cents": None,
                "evidence_keys": [str(item["key"]) for item in unsupported],
                "summary": (
                    f"{len(unsupported)} potential adjustment(s) were withheld because "
                    "local paired-sale support was insufficient."
                ),
            }
        )
    unknown_condition = sum(comp.condition_classification == "unknown" for comp in comps)
    if unknown_condition:
        drivers.append(
            {
                "key": "condition_uncertainty",
                "label": "Condition uncertainty",
                "severity": "review",
                "impact_cents": None,
                "comp_keys": [
                    _comp_key(comp) for comp in comps if comp.condition_classification == "unknown"
                ],
                "summary": (
                    f"{unknown_condition} selected sale(s) still have unknown condition; "
                    "photo or listing review may materially tighten the conclusion."
                ),
            }
        )
    if expansion_count:
        drivers.append(
            {
                "key": "expanded_market_area",
                "label": "Expanded market area",
                "severity": "review",
                "impact_cents": None,
                "comp_keys": [
                    _comp_key(comp)
                    for comp in comps
                    if comp.search_level in {"expanded", "extended", "manual"}
                ],
                "summary": (
                    f"{expansion_count} sale(s) required expanded, extended, or manual "
                    "sourcing and need micro-market review."
                ),
            }
        )
    source_conflict_comps = [
        *withheld_conflict_comps,
        *[
            comp
            for comp in comps
            if any(_material_source_conflict(conflict) for conflict in comp.source_conflicts)
        ],
    ]
    source_conflict_comps = list({_comp_key(comp): comp for comp in source_conflict_comps}.values())
    if source_conflict_comps:
        material_conflicts = [
            conflict
            for comp in source_conflict_comps
            for conflict in comp.source_conflicts
            if _material_source_conflict(conflict)
        ]
        conflict_count = len(material_conflicts)
        conflict_severity = (
            "high"
            if any(conflict.get("severity", "high") == "high" for conflict in material_conflicts)
            else "review"
        )
        drivers.append(
            {
                "key": "provider_conflicts",
                "label": "Provider fact conflicts",
                "severity": conflict_severity,
                "impact_cents": None,
                "comp_keys": [_comp_key(comp) for comp in source_conflict_comps],
                "summary": (
                    f"{conflict_count} material sale fact conflict(s) remain across structured "
                    "providers and require human resolution."
                ),
            }
        )
    magnitude_review = [
        str(item["comp_key"]) for item in comp_adjustments if item.get("requires_review")
    ]
    if magnitude_review:
        drivers.append(
            {
                "key": "adjustment_magnitude",
                "label": "Adjustment magnitude",
                "severity": "high",
                "impact_cents": None,
                "comp_keys": magnitude_review,
                "summary": (
                    f"{len(magnitude_review)} adjusted indication(s) exceed the magnitude or "
                    "extrapolation review threshold."
                ),
            }
        )
    return {
        "version": "adjusted_range_diagnostics_v1",
        "policy": "weighted_interpolated_q25_q50_q75_of_adjusted_closed_sales",
        "artificial_padding_applied": False,
        "raw_sale_span_cents": raw_span,
        "adjusted_indication_span_cents": adjusted_span,
        "adjustment_span_change_cents": (
            adjusted_span - raw_span if adjusted_span is not None and raw_span is not None else None
        ),
        "supported_range_width_cents": supported_range_width,
        "supported_range_percentage": supported_range_percentage,
        "drivers": drivers,
    }


def _value_span(values: list[int]) -> int | None:
    return max(values) - min(values) if values else None


def _range_percentage(
    low: int | None,
    point: int | None,
    high: int | None,
) -> float | None:
    if low is None or point is None or high is None or point <= 0:
        return None
    return round((high - low) / point * 100, 2)


def _range_position(
    value: int | None,
    *,
    low: int | None,
    point: int | None,
    high: int | None,
) -> str | None:
    if value is None or point is None:
        return None
    if low is not None and value <= low:
        return "lower_anchor"
    if high is not None and value >= high:
        return "upper_anchor"
    if value < point:
        return "below_point"
    if value > point:
        return "above_point"
    return "point"


def _range_anchor_keys(comp_adjustments: list[dict[str, Any]]) -> list[str]:
    usable = [
        item for item in comp_adjustments if isinstance(item.get("adjusted_indication_cents"), int)
    ]
    if not usable:
        return []
    ordered = sorted(usable, key=lambda item: int(item["adjusted_indication_cents"]))
    return list(dict.fromkeys((str(ordered[0]["comp_key"]), str(ordered[-1]["comp_key"]))))


def _warnings(
    *,
    evidence: list[dict[str, Any]],
    comp_adjustments: list[dict[str, Any]],
    expansion_count: int,
    range_diagnostics: dict[str, Any],
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
    range_percentage = range_diagnostics.get("supported_range_percentage")
    if isinstance(range_percentage, (int, float)) and range_percentage > 15:
        warnings.append(
            "The adjusted closed-sale middle range exceeds 15% of the Stonegate ARV point; "
            "review the range drivers before approving an offer."
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


def _physically_similar(
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
    *,
    ignored_feature: str | None = None,
) -> bool:
    if (
        left.condition_classification not in {"renovated", "as_is"}
        or left.condition_classification != right.condition_classification
    ):
        return False
    size_difference = _relative_difference(left.square_footage, right.square_footage)
    year_difference = _absolute_difference(left.year_built, right.year_built)
    lot_difference = _relative_difference(left.lot_size, right.lot_size)
    bedroom_difference = _absolute_difference(left.bedrooms, right.bedrooms)
    bathroom_difference = _absolute_difference(left.bathrooms, right.bathrooms)
    return (
        size_difference is not None
        and size_difference <= 0.01
        and year_difference is not None
        and year_difference <= 3
        and lot_difference is not None
        and lot_difference <= 0.01
        and bedroom_difference is not None
        and bedroom_difference == 0
        and bathroom_difference is not None
        and bathroom_difference == 0
        and _controlled_feature_parity(
            left,
            right,
            ignored_feature=ignored_feature,
            require_known=True,
        )
    )


def _matched_for_gla(
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
    *,
    time_supported: bool,
) -> bool:
    if (
        left.condition_classification not in {"renovated", "as_is"}
        or left.condition_classification != right.condition_classification
    ):
        return False
    year_difference = _absolute_difference(left.year_built, right.year_built)
    lot_difference = _relative_difference(left.lot_size, right.lot_size)
    recency_difference = _absolute_difference(left.days_old, right.days_old)
    bedroom_difference = _absolute_difference(left.bedrooms, right.bedrooms)
    bathroom_difference = _absolute_difference(left.bathrooms, right.bathrooms)
    if year_difference is None or year_difference > 3:
        return False
    if lot_difference is None or lot_difference > 0.01:
        return False
    if bedroom_difference is None or bedroom_difference != 0:
        return False
    if bathroom_difference is None or bathroom_difference != 0:
        return False
    if not _controlled_feature_parity(left, right, require_known=True):
        return False
    return recency_difference is not None and recency_difference <= (180 if time_supported else 30)


def _matched_for_lot(
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
    *,
    time_supported: bool,
    gla_supported: bool,
) -> bool:
    if (
        left.condition_classification not in {"renovated", "as_is"}
        or left.condition_classification != right.condition_classification
    ):
        return False
    size_difference = _relative_difference(left.square_footage, right.square_footage)
    year_difference = _absolute_difference(left.year_built, right.year_built)
    recency_difference = _absolute_difference(left.days_old, right.days_old)
    bedroom_difference = _absolute_difference(left.bedrooms, right.bedrooms)
    bathroom_difference = _absolute_difference(left.bathrooms, right.bathrooms)
    return (
        size_difference is not None
        and size_difference <= (0.05 if gla_supported else 0.01)
        and year_difference is not None
        and year_difference <= 3
        and recency_difference is not None
        and recency_difference <= (180 if time_supported else 30)
        and bedroom_difference == 0
        and bathroom_difference == 0
        and _controlled_feature_parity(left, right, require_known=True)
    )


def _matched_for_binary(
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
    *,
    ignored_feature: str,
    time_supported: bool,
    gla_supported: bool,
    lot_supported: bool,
) -> bool:
    if (
        left.condition_classification not in {"renovated", "as_is"}
        or left.condition_classification != right.condition_classification
    ):
        return False
    size_difference = _relative_difference(left.square_footage, right.square_footage)
    lot_difference = _relative_difference(left.lot_size, right.lot_size)
    year_difference = _absolute_difference(left.year_built, right.year_built)
    recency_difference = _absolute_difference(left.days_old, right.days_old)
    return (
        size_difference is not None
        and size_difference <= (0.05 if gla_supported else 0.01)
        and lot_difference is not None
        and lot_difference <= (0.05 if lot_supported else 0.01)
        and year_difference is not None
        and year_difference <= 3
        and _absolute_difference(left.bedrooms, right.bedrooms) == 0
        and _absolute_difference(left.bathrooms, right.bathrooms) == 0
        and recency_difference is not None
        and recency_difference <= (180 if time_supported else 30)
        and _controlled_feature_parity(
            left,
            right,
            ignored_feature=ignored_feature,
            require_known=True,
        )
    )


def _time_normalized_price(comp: MarketAnalysisCompRead, evidence: dict[str, Any]) -> int:
    assert comp.price_cents is not None
    if (
        evidence["status"] != "supported"
        or comp.days_old is None
        or not _comp_within_evidence_cohort(comp, evidence)
    ):
        return comp.price_cents
    observed_range = evidence.get("observed_range") or {}
    observed_days = int(observed_range.get("days") or 0)
    anchor_days = int(observed_range.get("anchor_days_old") or 0)
    days = min(max(0, comp.days_old - anchor_days), observed_days)
    rate_value = evidence.get("rate")
    rate = float(rate_value) if isinstance(rate_value, (int, float)) else 0.0
    return int(round(comp.price_cents * (1 + rate) ** (days / 30)))


def _controlled_feature_parity(
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
    *,
    ignored_feature: str | None = None,
    require_known: bool = False,
) -> bool:
    for key in ("garage", "pool", "basement"):
        if key == ignored_feature:
            continue
        left_value = _comp_feature(left, key)
        right_value = _comp_feature(right, key)
        if require_known and (left_value is None or right_value is None):
            return False
        if left_value != right_value:
            return False
    return True


def _pair_participant_keys(
    observations: list[dict[str, Any]],
    *,
    left_key: str,
    right_key: str,
) -> tuple[set[str], bool]:
    adjacency: dict[str, set[str]] = {}
    for observation in observations:
        left = str(observation.get(left_key) or "")
        right = str(observation.get(right_key) or "")
        if not left or not right:
            continue
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    if not adjacency:
        return set(), False
    visited: set[str] = set()
    pending = [next(iter(adjacency))]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency[current] - visited)
    return set(adjacency), len(visited) == len(adjacency)


def _participant_bounds(
    participants: list[MarketAnalysisCompRead], field: str
) -> dict[str, int] | None:
    values = [value for comp in participants if (value := _comp_number(comp, field)) is not None]
    if not values:
        return None
    return {"minimum": min(values), "maximum": max(values)}


def _cohort_descriptor(
    participants: list[MarketAnalysisCompRead],
) -> dict[str, Any]:
    bounds: dict[str, dict[str, int | float]] = {}
    for field in (
        "square_footage",
        "lot_size",
        "year_built",
        "days_old",
        "bedrooms",
        "bathrooms",
    ):
        values = [
            value
            for comp in participants
            if (value := _numeric_value(getattr(comp, field, None))) is not None
        ]
        if len(values) == len(participants) and values:
            bounds[field] = {"minimum": min(values), "maximum": max(values)}
    feature_values: dict[str, list[bool]] = {}
    for key in ("garage", "pool", "basement"):
        observed_features = {_comp_feature(comp, key) for comp in participants}
        if None not in observed_features:
            feature_values[key] = sorted(value for value in observed_features if value is not None)
    return {
        "bounds": bounds,
        "feature_values": feature_values,
        "condition_values": sorted({comp.condition_classification for comp in participants}),
    }


def _comp_within_evidence_cohort(
    comp: MarketAnalysisCompRead,
    evidence: dict[str, Any],
) -> bool:
    cohort = (evidence.get("observed_range") or {}).get("cohort")
    if not isinstance(cohort, dict):
        return False
    bounds = cohort.get("bounds")
    if not isinstance(bounds, dict) or not bounds:
        return False
    for field, raw_bounds in bounds.items():
        if not isinstance(raw_bounds, dict):
            return False
        value = _numeric_value(getattr(comp, field, None))
        minimum = _numeric_value(raw_bounds.get("minimum"))
        maximum = _numeric_value(raw_bounds.get("maximum"))
        if value is None or minimum is None or maximum is None or not minimum <= value <= maximum:
            return False
    feature_values = cohort.get("feature_values")
    if not isinstance(feature_values, dict):
        return False
    for key in ("garage", "pool", "basement"):
        allowed = feature_values.get(key)
        value = _comp_feature(comp, key)
        if not isinstance(allowed, list) or value not in allowed:
            return False
    condition_values = cohort.get("condition_values")
    return isinstance(condition_values, list) and comp.condition_classification in (
        condition_values
    )


def _subject_within_evidence_cohort(
    subject: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    cohort = (evidence.get("observed_range") or {}).get("cohort")
    if not isinstance(cohort, dict):
        return False
    bounds = cohort.get("bounds")
    if not isinstance(bounds, dict):
        return False
    subject_fields = {
        "square_footage": subject.get("squareFootage"),
        "lot_size": subject.get("lotSize"),
        "year_built": subject.get("yearBuilt"),
        "bedrooms": subject.get("bedrooms"),
        "bathrooms": subject.get("bathrooms"),
    }
    for field, raw_value in subject_fields.items():
        raw_bounds = bounds.get(field)
        if not isinstance(raw_bounds, dict):
            return False
        value = _numeric_value(raw_value)
        minimum = _numeric_value(raw_bounds.get("minimum"))
        maximum = _numeric_value(raw_bounds.get("maximum"))
        if value is None or minimum is None or maximum is None or not minimum <= value <= maximum:
            return False
    feature_values = cohort.get("feature_values")
    if not isinstance(feature_values, dict):
        return False
    subject_features = _features(subject)
    for key in ("garage", "pool", "basement"):
        allowed = feature_values.get(key)
        if not isinstance(allowed, list) or subject_features.get(key) not in allowed:
            return False
    return True


def _evidence_applies_to_pair(
    evidence: dict[str, Any],
    left: MarketAnalysisCompRead,
    right: MarketAnalysisCompRead,
) -> bool:
    return (
        evidence.get("status") == "supported"
        and _comp_within_evidence_cohort(left, evidence)
        and _comp_within_evidence_cohort(right, evidence)
    )


def _binary_rate_applicable(
    *,
    comp: MarketAnalysisCompRead,
    subject: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    return _comp_within_evidence_cohort(comp, evidence) and _subject_within_evidence_cohort(
        subject, evidence
    )


def _normalized_price(
    comp: MarketAnalysisCompRead,
    time_evidence: dict[str, Any],
    gla_evidence: dict[str, Any],
    lot_evidence: dict[str, Any],
) -> int:
    value = _gla_normalized_price(comp, time_evidence, gla_evidence)
    if (
        lot_evidence["status"] == "supported"
        and comp.lot_size is not None
        and _comp_within_evidence_cohort(comp, lot_evidence)
    ):
        target = int(
            (lot_evidence.get("observed_range") or {}).get("normalization_target") or comp.lot_size
        )
        value += (target - comp.lot_size) * int(lot_evidence["rate"])
    return value


def _gla_normalized_price(
    comp: MarketAnalysisCompRead,
    time_evidence: dict[str, Any],
    gla_evidence: dict[str, Any],
) -> int:
    value = _time_normalized_price(comp, time_evidence)
    if (
        gla_evidence["status"] == "supported"
        and comp.square_footage is not None
        and _comp_within_evidence_cohort(comp, gla_evidence)
    ):
        target = int(
            (gla_evidence.get("observed_range") or {}).get("normalization_target")
            or comp.square_footage
        )
        value += (target - comp.square_footage) * int(gla_evidence["rate"])
    return value


def _features(record: dict[str, Any]) -> dict[str, bool | None]:
    raw_features = record.get("features")
    raw: dict[str, Any] = raw_features if isinstance(raw_features, dict) else {}
    foundation = raw.get("foundationType")
    explicit_basement = _boolean(raw.get("basement"))
    return {
        "garage": _boolean(raw.get("garage")),
        "pool": _boolean(raw.get("pool")),
        "basement": (
            explicit_basement if explicit_basement is not None else _foundation_basement(foundation)
        ),
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
    weights = [max(weight, 0.01) for _, weight in ordered]
    total = sum(weights)
    positions: list[float] = []
    running = 0.0
    for weight in weights:
        positions.append((running + weight / 2) / total)
        running += weight
    if target <= positions[0]:
        return ordered[0][0]
    if target >= positions[-1]:
        return ordered[-1][0]
    for index in range(1, len(ordered)):
        if target > positions[index]:
            continue
        left_value = ordered[index - 1][0]
        right_value = ordered[index][0]
        left_position = positions[index - 1]
        right_position = positions[index]
        span = right_position - left_position
        if span <= 0:
            return right_value
        fraction = (target - left_position) / span
        return round(left_value + (right_value - left_value) * fraction)
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


def _relative_difference(left: int | None, right: int | None) -> float | None:
    if left is None or right is None:
        return None
    if max(abs(left), abs(right)) == 0:
        return 0.0
    return abs(left - right) / max(abs(left), abs(right))


def _absolute_difference(
    left: int | float | None,
    right: int | float | None,
) -> int | float | None:
    if left is None or right is None:
        return None
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


def _numeric_value(value: object) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _foundation_basement(value: object) -> bool | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = " ".join(value.casefold().replace("/", " ").split())
    if normalized in {
        "unknown",
        "n a",
        "na",
        "not available",
        "unspecified",
        "not reported",
    }:
        return None
    if normalized.startswith(("no basement", "without basement")):
        return False
    return "basement" in normalized


def _bool_number(value: bool | None) -> int | None:
    return int(value) if value is not None else None
