import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from app.core.config import Settings, get_settings
from app.integrations.rentcast_client import RentCastRentEstimate, RentCastValueEstimate
from app.services.underwriting_v2 import (
    UnderwritingV2Result,
    analyze_underwriting_v2,
    repair_assumptions,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "underwriting_v2_2_golden.json"


@pytest.fixture
def underwriting_settings(monkeypatch: MonkeyPatch) -> Generator[Settings, None, None]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("UNDERWRITING_ACTIVE_METHODOLOGY_VERSION", "v2.2")
    monkeypatch.setenv("UNDERWRITING_V3_SHADOW_ENABLED", "false")
    monkeypatch.setenv("UNDERWRITING_DEFAULT_ASSIGNMENT_FEE_CENTS", "1500000")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


def subject(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "subject-1",
        "formattedAddress": "123 Peachtree St, Atlanta, GA 30303",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1800,
        "yearBuilt": 1980,
        "lotSize": 8000,
        "latitude": 33.749,
        "longitude": -84.388,
        "propertyTaxes": {"2025": 3600},
        **overrides,
    }


def sale(
    provider_id: str,
    price: int | None,
    *,
    days_ago: int = 30,
    **overrides: Any,
) -> dict[str, Any]:
    return {
        "id": provider_id,
        "formattedAddress": f"{provider_id} Peachtree St, Atlanta, GA 30303",
        "propertyType": "Single Family",
        "lastSalePrice": price,
        "lastSaleDate": (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(),
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1800,
        "yearBuilt": 1980,
        "lotSize": 8000,
        "distance": 0.3,
        **overrides,
    }


def run_analysis(
    settings: Settings,
    sales: list[dict[str, Any]],
    *,
    subject_record: dict[str, Any] | None = None,
    estimate_subject: dict[str, Any] | None = None,
    condition_overrides: dict[str, str] | None = None,
    repair_level: str = "moderate",
    base_rehab_override_cents: int | None = None,
    repair_items: list[dict[str, Any]] | None = None,
    contingency_override_percentage: int | None = None,
    holding_period_months: int = 6,
) -> UnderwritingV2Result:
    estimate_facts = estimate_subject or subject()
    estimate = RentCastValueEstimate(
        price=300000,
        price_range_low=275000,
        price_range_high=325000,
        subject_property=estimate_facts,
        comparables=[],
        raw_response={},
    )
    rent = RentCastRentEstimate(
        rent=2400,
        rent_range_low=2200,
        rent_range_high=2600,
        comparables=[],
        raw_response={},
    )
    return analyze_underwriting_v2(
        estimate=estimate,
        subject_record=subject_record or subject(),
        sale_records=sales,
        rent_estimate=rent,
        local_property_type="single_family",
        lead_condition="needs_repairs",
        current_condition_override="dated_livable",
        target_condition="standard_flip",
        repair_level_override=repair_level,
        base_rehab_override_cents=base_rehab_override_cents,
        repair_items=repair_items or [],
        contingency_override_percentage=contingency_override_percentage,
        holding_period_months=holding_period_months,
        condition_overrides=condition_overrides or {},
        provider_warnings=[],
        comp_review_decisions=[],
        address_validation_status="provider_confirmed",
        address_match_score=100,
        secondary_evidence={"status": "unavailable", "sources": [], "conflicts": []},
        settings=settings,
    )


def standard_sales() -> list[dict[str, Any]]:
    return [
        sale("comp-1", 280000, squareFootage=1700, yearBuilt=1982, lotSize=7000, distance=0.2),
        sale("comp-2", 300000, distance=0.4),
        sale("comp-3", 320000, squareFootage=1900, yearBuilt=1978, lotSize=8500, distance=0.6),
        sale("comp-4", 230000, squareFootage=1750, yearBuilt=1981, lotSize=7800),
        sale("comp-5", 240000, squareFootage=1850, yearBuilt=1979, lotSize=8200, distance=0.5),
        sale("reject-size", 400000, bedrooms=4, bathrooms=3, squareFootage=2400),
        sale("reject-price-outlier", 650000, distance=0.4),
    ]


def test_verified_standard_v2_2_result_matches_golden_fixture(
    underwriting_settings: Settings,
) -> None:
    result = run_analysis(
        underwriting_settings,
        standard_sales(),
        condition_overrides={
            "comp-1": "renovated",
            "comp-2": "renovated",
            "comp-3": "renovated",
            "comp-4": "as_is",
            "comp-5": "as_is",
            "reject-price-outlier": "renovated",
        },
        repair_items=[
            {"category": "roof", "estimated_cost_cents": 1500000},
            {"category": "kitchen", "estimated_cost_cents": 2500000},
            {"category": "hvac", "estimated_cost_cents": 1000000},
        ],
        contingency_override_percentage=20,
        holding_period_months=9,
    )
    expected = json.loads(FIXTURE_PATH.read_text())["verified_standard"]
    actual = {
        "as_is_low_cents": result.as_is_low_cents,
        "as_is_value_cents": result.as_is_value_cents,
        "as_is_high_cents": result.as_is_high_cents,
        "arv_low_cents": result.arv_low_cents,
        "arv_point_cents": result.arv_point_cents,
        "arv_high_cents": result.arv_high_cents,
        "conservative_arv_cents": result.conservative_arv_cents,
        "base_rehab_cents": result.base_rehab_cents,
        "total_rehab_cents": result.total_rehab_cents,
        "flip_buyer_max_cents": result.flip_buyer_max_cents,
        "rental_buyer_max_cents": result.rental_buyer_max_cents,
        "seller_contract_ceiling_cents": result.seller_contract_ceiling_cents,
        "recommended_opening_offer_cents": result.recommended_opening_offer_cents,
        "selected_comp_count": len(result.selected_comps),
        "rejected_comp_count": len(result.rejected_comps),
        "manual_review_required": result.manual_review_required,
        "arv_value_basis": result.assumptions["arv_value_basis"],
        "comp_value_method": result.assumptions["comp_value_method"],
    }
    assert actual == expected


def test_thin_market_remains_usable_but_preliminary(
    underwriting_settings: Settings,
) -> None:
    result = run_analysis(
        underwriting_settings,
        [sale("only-comp", 285000)],
        condition_overrides={"only-comp": "renovated"},
    )

    assert len(result.selected_comps) == 1
    assert result.arv_point_cents == 28500000
    assert result.conservative_arv_cents is not None
    assert result.seller_contract_ceiling_cents is not None
    assert result.confidence_score <= 59
    assert result.manual_review_required is True
    assert result.assumptions["arv_value_basis"] == "provisional_unverified_recorded_sales"
    assert any("Fewer than three" in reason for reason in result.review_reasons)


def test_rural_older_sales_are_retained_with_visible_penalties(
    underwriting_settings: Settings,
) -> None:
    sales = [
        sale("rural-1", 270000, days_ago=300, distance=3.2, squareFootage=1700),
        sale("rural-2", 290000, days_ago=420, distance=4.1),
        sale("rural-3", 310000, days_ago=500, distance=4.8, squareFootage=1900),
    ]
    result = run_analysis(
        underwriting_settings,
        sales,
        condition_overrides={item["id"]: "renovated" for item in sales},
    )

    assert len(result.selected_comps) == 3
    assert result.arv_point_cents is not None
    assert all(comp.score < 100 for comp in result.selected_comps)
    assert all("outside initial 0.5-mile area" in comp.selection_reason for comp in result.selected_comps)
    assert all("older than 180 days" in comp.selection_reason for comp in result.selected_comps)


def test_unique_or_adversarial_sales_do_not_create_an_arv(
    underwriting_settings: Settings,
) -> None:
    facts = subject()
    sales = [
        {**facts, "lastSalePrice": 300000, "lastSaleDate": datetime.now(UTC).isoformat()},
        sale("wrong-type", 400000, propertyType="Condo"),
        sale("wrong-size", 450000, squareFootage=2600),
        sale("wrong-rooms", 350000, bedrooms=5),
        sale("missing-date", 325000, lastSaleDate=None),
        sale("missing-price", None),
    ]
    result = run_analysis(underwriting_settings, sales)

    assert result.selected_comps == []
    assert len(result.rejected_comps) == 6
    assert result.arv_point_cents is None
    assert result.seller_contract_ceiling_cents is None
    assert result.recommended_opening_offer_cents is None
    assert result.as_is_value_cents == 30000000
    assert result.manual_review_required is True
    reasons = {comp.selection_reason for comp in result.rejected_comps}
    assert "Subject property sale; excluded from comparable set." in reasons
    assert "Different property type." in reasons
    assert "Living area differs by more than 20%." in reasons
    assert "Bedroom count differs by more than one." in reasons
    assert "Missing recorded sale date." in reasons
    assert "Missing recorded sale price." in reasons


def test_conflicting_subject_sources_are_visible_and_require_review(
    underwriting_settings: Settings,
) -> None:
    estimate_facts = subject(propertyType="Condo", squareFootage=2300, bedrooms=4)
    result = run_analysis(
        underwriting_settings,
        [sale("comp-1", 290000), sale("comp-2", 300000), sale("comp-3", 310000)],
        subject_record=subject(),
        estimate_subject=estimate_facts,
        condition_overrides={
            "comp-1": "renovated",
            "comp-2": "renovated",
            "comp-3": "renovated",
        },
    )

    assert "Property type differs between seller/CRM and provider records." in result.data_disagreements
    assert "Provider sources disagree on living area." in result.data_disagreements
    assert "Provider sources disagree on bedroom count." in result.data_disagreements
    assert result.manual_review_required is True
    assert any("source disagreements" in reason for reason in result.review_reasons)


def test_repair_entry_modes_remain_stable() -> None:
    system = repair_assumptions(
        "moderate",
        1800,
        base_rehab_override_cents=None,
        repair_items=[],
        contingency_override_percentage=None,
    )
    direct_total = repair_assumptions(
        "moderate",
        1800,
        base_rehab_override_cents=5000000,
        repair_items=[],
        contingency_override_percentage=20,
    )
    itemized = repair_assumptions(
        "moderate",
        1800,
        base_rehab_override_cents=10000000,
        repair_items=[
            {"category": "roof", "estimated_cost_cents": 2000000},
            {"category": "kitchen", "estimated_cost_cents": 3000000},
        ],
        contingency_override_percentage=10,
    )

    assert system["repair_estimate_source"] == "system_estimate"
    assert system["system_repair_low_cents"] == 5400000
    assert system["system_repair_high_cents"] == 9000000
    assert system["base_rehab_cents"] == 7200000
    assert system["total_rehab_cents"] == 8280000
    assert direct_total["repair_estimate_source"] == "user_total"
    assert direct_total["base_rehab_cents"] == 5000000
    assert direct_total["total_rehab_cents"] == 6000000
    assert itemized["repair_estimate_source"] == "itemized"
    assert itemized["base_rehab_cents"] == 5000000
    assert itemized["total_rehab_cents"] == 5500000
