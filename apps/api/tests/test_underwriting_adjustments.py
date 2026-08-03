from typing import Any

from app.schemas.leads import MarketAnalysisCompRead
from app.services.underwriting_adjustments import build_adjustment_shadow


def comp(
    key: str,
    price_cents: int,
    *,
    square_footage: int,
    days_old: int = 90,
    lot_size: int = 8_000,
    garage: bool | None = False,
    pool: bool | None = False,
    basement: bool | None = False,
) -> MarketAnalysisCompRead:
    return MarketAnalysisCompRead(
        provider_id=key,
        formatted_address=f"{key} Main St, Atlanta, GA 30303",
        status="Recorded sale",
        listing_type="Property record",
        property_type="Single Family",
        price_cents=price_cents,
        bedrooms=3,
        bathrooms=2,
        square_footage=square_footage,
        year_built=1980,
        distance_miles=0.3,
        days_old=days_old,
        correlation=None,
        listed_date=None,
        removed_date=None,
        last_seen_date=None,
        sale_date="2026-01-01",
        price_source="recorded_sale",
        verification_status="recorded",
        condition_classification="renovated",
        condition_evidence="human_classification",
        lot_size=lot_size,
        garage=garage,
        pool=pool,
        basement=basement,
        adjusted_value_cents=round(price_cents * 1_800 / square_footage),
        price_per_square_foot_cents=round(price_cents / square_footage),
        weight=0.9,
        subdivision="PEACHTREE",
        subdivision_match=True,
        search_level="preferred",
        comp_grade="A",
        selection_status="selected",
        selection_reason="local recorded sale",
        score=90,
    )


def subject(**overrides: Any) -> dict[str, Any]:
    return {
        "squareFootage": 1_800,
        "lotSize": 8_000,
        "yearBuilt": 1980,
        "bedrooms": 3,
        "bathrooms": 2,
        "features": {"garage": False, "pool": False, "foundationType": "Slab"},
        **overrides,
    }


def build(comps: list[MarketAnalysisCompRead], **subject_overrides: Any) -> dict[str, Any]:
    return build_adjustment_shadow(
        subject=subject(**subject_overrides),
        selected_comps=comps,
        active_arv_low_cents=29_000_000,
        active_arv_point_cents=32_000_000,
        active_arv_high_cents=35_000_000,
    )


def evidence(result: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in result["rate_evidence"] if item["key"] == key)


def test_market_supported_living_area_rate_replaces_full_ppsf_scaling() -> None:
    result = build(
        [
            comp("small", 28_000_000, square_footage=1_600),
            comp("subject-size", 32_000_000, square_footage=1_800),
            comp("large", 36_000_000, square_footage=2_000),
        ]
    )

    gla = evidence(result, "living_area")
    assert gla["status"] == "supported"
    assert gla["rate"] == 20_000
    indications = {
        item["comp_key"]: item["adjusted_indication_cents"] for item in result["comp_adjustments"]
    }
    assert indications == {
        "small": 32_000_000,
        "subject-size": 32_000_000,
        "large": 32_000_000,
    }
    assert result["baseline"]["arv_point_cents"] == 32_000_000
    assert result["valuation_use"] == "shadow_only_excluded_from_offer_math"


def test_time_adjustment_requires_and_records_local_pair_support() -> None:
    monthly_growth = 1.01
    comps = []
    for index, days_old in enumerate((30, 120, 210, 300), start=1):
        price = round(36_000_000 / (monthly_growth ** (days_old / 30)))
        comps.append(
            comp(
                f"time-{index}",
                price,
                square_footage=1_800,
                days_old=days_old,
            )
        )

    result = build(comps)
    time = evidence(result, "market_time")

    assert time["status"] == "supported"
    assert 0.009 <= time["rate"] <= 0.011
    assert time["pair_count"] >= 3
    assert all(item["left_comp_key"] for item in time["observations"])


def test_time_normalization_uses_one_common_newest_sale_anchor() -> None:
    monthly_growth = 1.01
    anchor_days = 365
    anchor_value = 36_000_000
    comps = [
        comp(
            f"older-{index}",
            round(anchor_value / (monthly_growth ** ((days_old - anchor_days) / 30))),
            square_footage=1_800,
            days_old=days_old,
        )
        for index, days_old in enumerate((365, 455, 545, 635), start=1)
    ]

    result = build(comps)
    time = evidence(result, "market_time")
    indications = [item["adjusted_indication_cents"] for item in result["comp_adjustments"]]

    assert time["status"] == "supported"
    assert time["observed_range"]["anchor_days_old"] == anchor_days
    assert max(indications) - min(indications) < 5_000


def test_implausible_time_rate_blocks_v3_value_promotion() -> None:
    result = build(
        [
            comp("now", 80_000_000, square_footage=1_800, days_old=0),
            comp("two-months", 40_000_000, square_footage=1_800, days_old=60),
            comp("four-months", 20_000_000, square_footage=1_800, days_old=120),
            comp("six-months", 10_000_000, square_footage=1_800, days_old=180),
        ]
    )

    time = evidence(result, "market_time")
    assert time["status"] == "unsupported"
    assert time["blocking"] is True
    assert "3% plausibility" in time["reason"]
    assert result["status"] == "unsupported"


def test_feature_cohorts_cannot_masquerade_as_a_time_trend() -> None:
    comps = [
        comp(
            f"garage-{index}",
            33_000_000,
            square_footage=1_800,
            days_old=days,
            garage=True,
        )
        for index, days in enumerate((0, 30, 60), start=1)
    ] + [
        comp(
            f"no-garage-{index}",
            30_000_000,
            square_footage=1_800,
            days_old=days,
            garage=False,
        )
        for index, days in enumerate((180, 210, 240), start=1)
    ]

    result = build(comps)

    assert evidence(result, "market_time")["status"] == "unsupported"


def test_lot_size_cohorts_cannot_masquerade_as_a_time_trend() -> None:
    comps = [
        comp(
            f"lot-time-{index}",
            round((300 / (1.01**period)) * 1_800 * 100),
            square_footage=1_800,
            days_old=days_old,
            lot_size=lot_size,
        )
        for index, (days_old, lot_size, period) in enumerate(
            ((30, 10_000, 0), (120, 9_500, 3), (210, 9_000, 6), (300, 8_500, 9)),
            start=1,
        )
    ]

    result = build(comps, lotSize=9_250)

    assert evidence(result, "market_time")["status"] == "unsupported"


def test_time_cohorts_cannot_masquerade_as_a_living_area_rate() -> None:
    monthly_growth = 1.01
    comps = [
        comp(
            f"older-small-{index}",
            round(30_000_000 / (monthly_growth**6)),
            square_footage=1_500,
            days_old=180,
        )
        for index in range(3)
    ] + [
        comp(
            f"new-large-{index}",
            30_000_000,
            square_footage=1_800,
            days_old=0,
        )
        for index in range(3)
    ]

    result = build(comps)

    assert evidence(result, "market_time")["status"] == "unsupported"
    assert evidence(result, "living_area")["status"] == "unsupported"


def test_year_built_cohorts_cannot_masquerade_as_a_living_area_rate() -> None:
    comps = [
        comp(
            f"year-size-{index}",
            price,
            square_footage=square_footage,
            days_old=60,
        ).model_copy(update={"year_built": year_built})
        for index, (square_footage, year_built, price) in enumerate(
            (
                (1_500, 1950, 27_000_000),
                (1_700, 1960, 31_000_000),
                (1_900, 1970, 35_000_000),
                (2_100, 1980, 39_000_000),
            ),
            start=1,
        )
    ]

    result = build(comps)

    assert evidence(result, "living_area")["status"] == "unsupported"


def test_missing_control_facts_never_create_matched_pair_support() -> None:
    sparse = [
        comp("missing-lot", 29_000_000, square_footage=1_500).model_copy(update={"lot_size": None}),
        comp("missing-year", 31_000_000, square_footage=1_650).model_copy(
            update={"year_built": None}
        ),
        comp("missing-size", 33_000_000, square_footage=1_800).model_copy(
            update={"square_footage": None}
        ),
        comp("complete", 35_000_000, square_footage=1_950),
    ]

    result = build(sparse)

    assert evidence(result, "market_time")["observations"] == []
    assert evidence(result, "living_area")["observations"] == []
    assert evidence(result, "market_time")["status"] == "unsupported"
    assert evidence(result, "living_area")["status"] == "unsupported"


def test_unknown_feature_facts_never_count_as_controlled_pair_support() -> None:
    unknown_features = [
        comp(
            f"unknown-{index}",
            price,
            square_footage=square_footage,
            days_old=days_old,
        ).model_copy(update={"garage": None, "pool": None, "basement": None})
        for index, (price, square_footage, days_old) in enumerate(
            (
                (28_000_000, 1_600, 30),
                (32_000_000, 1_800, 120),
                (36_000_000, 2_000, 210),
                (40_000_000, 2_200, 300),
            ),
            start=1,
        )
    ]

    result = build(unknown_features)

    assert evidence(result, "market_time")["status"] == "unsupported"
    assert evidence(result, "living_area")["status"] == "unsupported"
    assert evidence(result, "lot_size")["status"] == "unsupported"


def test_stable_market_can_support_a_zero_time_adjustment() -> None:
    result = build(
        [
            comp(f"stable-{index}", 32_000_000, square_footage=1_800, days_old=days)
            for index, days in enumerate((30, 120, 210, 300), start=1)
        ]
    )

    time = evidence(result, "market_time")
    assert time["status"] == "supported"
    assert time["rate"] == 0.0


def test_collinear_size_and_lot_cohorts_are_withheld_before_rate_learning() -> None:
    result = build(
        [
            comp("one", 28_000_000, square_footage=1_750, lot_size=6_000),
            comp("two", 30_000_000, square_footage=1_800, lot_size=7_000),
            comp("three", 32_000_000, square_footage=1_850, lot_size=8_000),
            comp("four", 34_000_000, square_footage=1_900, lot_size=9_000),
        ]
    )

    lot = evidence(result, "lot_size")
    assert lot["status"] == "unsupported"
    assert "double counting" in lot["reason"]
    assert lot["observations"] == []


def test_unmatched_lot_outlier_cannot_create_a_second_rate_on_pure_gla_prices() -> None:
    core = [
        comp(
            f"core-{index}",
            square_footage * 20_000,
            square_footage=square_footage,
            lot_size=lot_size,
        )
        for index, (square_footage, lot_size) in enumerate(
            ((1_600, 8_000), (1_800, 8_000), (2_000, 8_000), (2_200, 8_000)),
            start=1,
        )
    ]
    outlier = comp(
        "unmatched-outlier",
        44_000_000,
        square_footage=2_200,
        lot_size=7_000,
    ).model_copy(update={"year_built": 1940})

    result = build([*core, outlier], lotSize=8_500)

    assert evidence(result, "living_area")["status"] == "supported"
    assert evidence(result, "lot_size")["status"] == "unsupported"


def test_lot_size_cohort_cannot_create_a_fake_garage_rate() -> None:
    comps = [
        comp(
            f"lot-{index}",
            15_000_000 + lot_size * 2_000,
            square_footage=1_800,
            lot_size=lot_size,
            garage=index >= 3,
        )
        for index, lot_size in enumerate((7_000, 7_500, 8_000, 9_000, 9_500, 10_000))
    ]

    result = build(comps, lotSize=8_500, features={"garage": False})

    assert evidence(result, "garage")["status"] == "unsupported"


def test_binary_features_cannot_absorb_unsupported_time_or_lot_cohorts() -> None:
    comps: list[MarketAnalysisCompRead] = []
    for garage in (False, True):
        for pool in (False, True):
            for index in range(3):
                days_old = 0 if garage else 180
                lot_size = 10_400 + index * 20 if pool else 10_000 + index * 20
                price = 30_000_000 + (2_000_000 if garage else 0)
                price += 800_000 if pool else 0
                comps.append(
                    comp(
                        f"g{int(garage)}-p{int(pool)}-{index}",
                        price,
                        square_footage=1_800,
                        days_old=days_old,
                        lot_size=lot_size,
                        garage=garage,
                        pool=pool,
                        basement=False,
                    )
                )

    result = build(
        comps,
        lotSize=10_200,
        features={"garage": False, "pool": False, "basement": False},
    )

    assert evidence(result, "market_time")["status"] == "unsupported"
    assert evidence(result, "lot_size")["status"] == "unsupported"
    assert evidence(result, "garage")["status"] == "unsupported"
    assert evidence(result, "pool")["status"] == "unsupported"


def test_binary_feature_pairs_require_known_non_target_feature_controls() -> None:
    comps = [
        comp(
            f"garage-{index}",
            32_000_000 + (1_000_000 if garage else 0),
            square_footage=1_800,
            garage=garage,
            pool=None,
            basement=None,
        )
        for index, garage in enumerate((False, False, False, True, True, True), start=1)
    ]

    result = build(comps, features={"garage": False, "pool": False, "basement": False})

    assert evidence(result, "garage")["status"] == "unsupported"
    assert evidence(result, "garage")["observations"] == []


def test_stable_negative_pool_reaction_is_supported_and_applied_by_direction() -> None:
    comps = [
        comp(
            f"pool-{index}",
            29_000_000 if pool else 30_000_000,
            square_footage=1_800,
            garage=False,
            pool=pool,
            basement=False,
        )
        for index, pool in enumerate((False, False, False, True, True, True), start=1)
    ]

    result = build(
        comps,
        features={"garage": False, "pool": False, "basement": False},
    )
    pool = evidence(result, "pool")
    indications = {
        item["comp_key"]: item["adjusted_indication_cents"] for item in result["comp_adjustments"]
    }

    assert pool["status"] == "supported"
    assert pool["rate"] == -1_000_000
    assert set(indications.values()) == {30_000_000}


def test_binary_rate_is_withheld_outside_its_observed_cohort() -> None:
    training = [
        comp(
            f"training-{index}",
            31_000_000 if garage else 30_000_000,
            square_footage=1_800,
            garage=garage,
            pool=False,
            basement=False,
        )
        for index, garage in enumerate((False, False, False, True, True, True), start=1)
    ]
    outlier = comp(
        "outlier",
        60_000_000,
        square_footage=4_000,
        lot_size=20_000,
        garage=False,
        pool=False,
        basement=False,
    )

    result = build(
        [*training, outlier],
        features={"garage": True, "pool": False, "basement": False},
    )
    outlier_adjustment = next(
        item for item in result["comp_adjustments"] if item["comp_key"] == "outlier"
    )
    garage_component = next(
        item for item in outlier_adjustment["components"] if item["key"] == "garage"
    )

    assert evidence(result, "garage")["status"] == "supported"
    assert garage_component["amount_cents"] == 0
    assert garage_component["extrapolation_limited"] is True
    assert outlier_adjustment["requires_review"] is True


def test_numeric_rate_is_withheld_outside_its_observed_cohort() -> None:
    training = [
        comp(
            f"training-{index}",
            price,
            square_footage=square_footage,
        )
        for index, (square_footage, price) in enumerate(
            ((1_500, 28_000_000), (1_700, 32_000_000), (1_900, 36_000_000)),
            start=1,
        )
    ]
    outlier = comp(
        "modern-outlier",
        60_000_000,
        square_footage=4_000,
        lot_size=20_000,
    ).model_copy(update={"year_built": 2020})

    result = build(
        [*training, outlier],
        squareFootage=3_800,
        lotSize=20_000,
        yearBuilt=2020,
    )
    adjustment = next(
        item for item in result["comp_adjustments"] if item["comp_key"] == "modern-outlier"
    )
    component = next(item for item in adjustment["components"] if item["key"] == "living_area")

    assert evidence(result, "living_area")["status"] == "supported"
    assert component["amount_cents"] == 0
    assert component["extrapolation_limited"] is True
    assert adjustment["requires_review"] is True


def test_time_rate_is_withheld_for_an_out_of_cohort_subject_and_comp() -> None:
    monthly_growth = 1.01
    training = [
        comp(
            f"time-{index}",
            round(36_000_000 / (monthly_growth ** (days_old / 30))),
            square_footage=1_800,
            days_old=days_old,
        )
        for index, days_old in enumerate((30, 120, 210, 300), start=1)
    ]
    outlier = comp(
        "modern-outlier",
        60_000_000,
        square_footage=4_000,
        lot_size=20_000,
        days_old=150,
    ).model_copy(update={"year_built": 2020})

    result = build(
        [*training, outlier],
        squareFootage=4_000,
        lotSize=20_000,
        yearBuilt=2020,
    )
    adjustment = next(
        item for item in result["comp_adjustments"] if item["comp_key"] == "modern-outlier"
    )
    component = next(item for item in adjustment["components"] if item["key"] == "market_time")

    assert evidence(result, "market_time")["status"] == "supported"
    assert component["amount_cents"] == 0
    assert component["extrapolation_limited"] is True
    assert adjustment["requires_review"] is True


def test_explicit_subject_basement_fact_is_used_before_foundation_fallback() -> None:
    comps = [
        comp(
            f"basement-{index}",
            31_000_000 if basement else 30_000_000,
            square_footage=1_800,
            garage=False,
            pool=False,
            basement=basement,
        )
        for index, basement in enumerate((False, False, False, True, True, True), start=1)
    ]

    result = build(
        comps,
        features={
            "garage": False,
            "pool": False,
            "basement": True,
            "foundationType": "Slab",
        },
    )

    assert evidence(result, "basement")["status"] == "supported"


def test_negative_or_unknown_subject_foundation_never_implies_a_basement() -> None:
    comps = [
        comp(
            f"basement-{index}",
            31_000_000 if basement else 30_000_000,
            square_footage=1_800,
            garage=False,
            pool=False,
            basement=basement,
        )
        for index, basement in enumerate((False, False, False, True, True, True), start=1)
    ]

    no_basement = build(
        comps,
        features={"garage": False, "pool": False, "foundationType": "No Basement"},
    )
    unknown = build(
        comps,
        features={"garage": False, "pool": False, "foundationType": "Unknown"},
    )

    assert evidence(no_basement, "basement")["status"] == "supported"
    assert evidence(unknown, "basement")["status"] == "unsupported"


def test_mixed_sign_matched_pairs_are_retained_and_withhold_gla_rate() -> None:
    result = build(
        [
            comp("one", 30_000_000, square_footage=1_500),
            comp("two", 35_000_000, square_footage=1_600),
            comp("three", 29_000_000, square_footage=1_700),
            comp("four", 36_000_000, square_footage=1_800),
        ]
    )

    gla = evidence(result, "living_area")
    signed_rates = [item["rate_cents_per_unit"] for item in gla["observations"]]

    assert gla["status"] == "unsupported"
    assert any(rate < 0 for rate in signed_rates)
    assert any(rate > 0 for rate in signed_rates)
    assert "complete signed matched-pair distribution" in gla["reason"]


def test_thin_evidence_remains_usable_without_invented_adjustments() -> None:
    result = build(
        [
            comp("small", 28_000_000, square_footage=1_600),
            comp("large", 36_000_000, square_footage=2_000),
        ]
    )

    assert evidence(result, "living_area")["status"] == "unsupported"
    assert [item["adjusted_indication_cents"] for item in result["comp_adjustments"]] == [
        28_000_000,
        36_000_000,
    ]
    assert result["conclusion"]["arv_low_cents"] < result["conclusion"]["arv_point_cents"]
    assert result["conclusion"]["arv_high_cents"] > result["conclusion"]["arv_point_cents"]
    assert any("No supported adjustment" in warning for warning in result["warnings"])


def test_supported_range_uses_interpolated_adjusted_sale_quartiles_without_padding() -> None:
    result = build(
        [
            comp("low", 28_000_000, square_footage=1_800),
            comp("middle", 32_000_000, square_footage=1_800),
            comp("high", 36_000_000, square_footage=1_800),
        ]
    )

    assert result["calculation_version"] == "v3.1-adjusted-distribution"
    assert result["conclusion"] == {
        **result["conclusion"],
        "arv_low_cents": 29_000_000,
        "arv_point_cents": 32_000_000,
        "arv_high_cents": 35_000_000,
    }
    diagnostics = result["range_diagnostics"]
    assert diagnostics["artificial_padding_applied"] is False
    assert diagnostics["supported_range_width_cents"] == 6_000_000
    assert diagnostics["policy"] == ("weighted_interpolated_q25_q50_q75_of_adjusted_closed_sales")
    assert result["range_drivers"] == diagnostics["drivers"]


def test_range_diagnostics_identify_condition_and_evidence_review_work() -> None:
    comps = [
        comp("known-low", 30_000_000, square_footage=1_800),
        comp("known-high", 34_000_000, square_footage=1_800),
        comp("unknown", 38_000_000, square_footage=1_800).model_copy(
            update={"condition_classification": "unknown"}
        ),
    ]

    result = build(comps)
    drivers = {item["key"]: item for item in result["range_drivers"]}

    assert "adjusted_sale_dispersion" in drivers
    assert drivers["condition_uncertainty"]["comp_keys"] == ["unknown"]
    assert "withheld_adjustments" in drivers
    assert all(item["distance_from_point_cents"] is not None for item in result["comp_adjustments"])


def test_cross_provider_agreement_is_visible_and_conflicts_force_review() -> None:
    corroborated = [
        comp(f"corroborated-{index}", price, square_footage=1_800).model_copy(
            update={
                "evidence_sources": ["rentcast", "dealmachine"],
                "corroboration_count": 2,
                "corroborated": True,
            }
        )
        for index, price in enumerate((30_000_000, 32_000_000), start=1)
    ]
    conflicting = comp("conflicting", 34_000_000, square_footage=1_800).model_copy(
        update={
            "evidence_sources": ["rentcast", "dealmachine"],
            "corroboration_count": 2,
            "source_conflicts": [
                {
                    "field": "lastSalePrice",
                    "values": {"rentcast": 340_000, "dealmachine": 345_000},
                }
            ],
        }
    )

    result = build([*corroborated, conflicting])
    source_factor = next(
        item for item in result["confidence_factors"] if item["key"] == "source_agreement"
    )
    drivers = {item["key"]: item for item in result["range_drivers"]}

    assert source_factor["score"] == 1
    assert result["requires_manual_review"] is True
    assert drivers["provider_conflicts"]["comp_keys"] == ["conflicting"]
    assert "conflicting" not in {item["comp_key"] for item in result["comp_adjustments"]}


def test_nonmaterial_provider_variance_does_not_reduce_confidence_or_force_review() -> None:
    baseline = [
        comp(f"comp-{index}", price, square_footage=1_800)
        for index, price in enumerate((30_000_000, 32_000_000, 34_000_000), start=1)
    ]
    with_minor_variance = baseline[0].model_copy(
        update={
            "evidence_sources": ["rentcast", "dealmachine"],
            "corroboration_count": 2,
            "corroborated": True,
            "source_conflicts": [
                {
                    "field": "latitude",
                    "material": False,
                    "severity": "info",
                    "summary": "Coordinates differ only within tolerance.",
                }
            ],
        }
    )
    baseline_result = build(baseline)
    result = build([with_minor_variance, *baseline[1:]])

    assert (
        result["conclusion"]["confidence_score"]
        >= baseline_result["conclusion"]["confidence_score"]
    )
    assert "provider_conflicts" not in {item["key"] for item in result["range_drivers"]}
    assert result["requires_manual_review"] == baseline_result["requires_manual_review"]


def test_materially_conflicting_second_source_never_earns_agreement_credit() -> None:
    plain = [
        comp(f"plain-{index}", price, square_footage=1_800)
        for index, price in enumerate((30_000_000, 32_000_000, 34_000_000), start=1)
    ]
    conflicting = plain[0].model_copy(
        update={
            "evidence_sources": ["rentcast", "dealmachine"],
            "corroboration_count": 1,
            "source_overlap_count": 2,
            "corroborated": False,
            "source_conflicts": [
                {
                    "field": "sale_price",
                    "material": True,
                    "severity": "high",
                    "summary": "Sale prices materially disagree.",
                }
            ],
        }
    )

    result = build([conflicting, *plain[1:]])
    source_factor = next(
        item for item in result["confidence_factors"] if item["key"] == "source_agreement"
    )

    assert source_factor["score"] == -2
    assert "0 sale(s) are corroborated" in source_factor["summary"]
