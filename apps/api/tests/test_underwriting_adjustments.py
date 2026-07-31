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
    garage: bool | None = None,
    pool: bool | None = None,
    basement: bool | None = None,
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
        "features": {"garage": True, "pool": False, "foundationType": "Slab"},
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
        item["comp_key"]: item["adjusted_indication_cents"]
        for item in result["comp_adjustments"]
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


def test_collinear_lot_adjustment_is_withheld_to_prevent_double_counting() -> None:
    result = build(
        [
            comp("one", 28_000_000, square_footage=1_500, lot_size=6_000),
            comp("two", 30_000_000, square_footage=1_700, lot_size=7_000),
            comp("three", 32_000_000, square_footage=1_900, lot_size=8_000),
            comp("four", 34_000_000, square_footage=2_100, lot_size=9_000),
        ]
    )

    lot = evidence(result, "lot_size")
    assert lot["status"] == "unsupported"
    assert "double counting" in lot["reason"]
    assert lot["collinearity"] == 1.0


def test_thin_evidence_remains_usable_without_invented_adjustments() -> None:
    result = build(
        [
            comp("small", 28_000_000, square_footage=1_600),
            comp("large", 36_000_000, square_footage=2_000),
        ]
    )

    assert evidence(result, "living_area")["status"] == "unsupported"
    assert [
        item["adjusted_indication_cents"] for item in result["comp_adjustments"]
    ] == [28_000_000, 36_000_000]
    assert result["conclusion"]["arv_low_cents"] < result["conclusion"]["arv_point_cents"]
    assert result["conclusion"]["arv_high_cents"] > result["conclusion"]["arv_point_cents"]
    assert any("No supported adjustment" in warning for warning in result["warnings"])
