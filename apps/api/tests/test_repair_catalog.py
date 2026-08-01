import pytest

from app.services.repair_catalog import (
    CATALOG_VERSION,
    evaluate_repair_scope,
    prepare_new_scope_items,
)


def test_guided_replacement_uses_quantity_and_versioned_georgia_range() -> None:
    result = evaluate_repair_scope(
        [
            {
                "category": "roof",
                "scope_status": "replace",
                "severity": "standard",
                "quantity": 20,
                "pricing_method": "catalog",
            }
        ],
        contingency_percentage=10,
    )

    item = result["items"][0]
    assert item["catalog_version"] == CATALOG_VERSION
    assert item["unit"] == "roof_square"
    assert item["system_low_cents"] == 900_000
    assert item["estimated_cost_cents"] == 1_250_000
    assert item["system_high_cents"] == 1_700_000
    assert result["total_expected_cents"] == 1_375_000


def test_unknown_high_risk_component_adds_reserve_and_specialist_warning() -> None:
    result = evaluate_repair_scope(
        [
            {
                "category": "foundation",
                "scope_status": "unknown",
                "quantity": 1,
                "pricing_method": "catalog",
            }
        ],
        contingency_percentage=20,
    )

    assert result["unknown_reserve_cents"] == 1_800_000
    assert result["total_low_cents"] == 0
    assert result["total_high_cents"] == 10_200_000
    assert result["unknown_item_count"] == 1
    assert any("specialist review" in warning for warning in result["warnings"])


def test_catalog_manual_override_requires_reason_and_preserves_system_context() -> None:
    item = {
        "category": "hvac",
        "scope_status": "replace",
        "quantity": 1,
        "pricing_method": "catalog",
        "manual_override_cents": 9_250_00,
    }
    with pytest.raises(ValueError, match="reason"):
        evaluate_repair_scope([item], contingency_percentage=15)

    result = evaluate_repair_scope(
        [{**item, "override_reason": "Written local installer allowance."}],
        contingency_percentage=15,
    )
    normalized = result["items"][0]
    assert normalized["pricing_method"] == "manual"
    assert normalized["estimated_cost_cents"] == 9_250_00
    assert normalized["system_expected_cents"] == 8_500_00


def test_legacy_manual_item_remains_exact_and_no_work_remains_zero() -> None:
    result = evaluate_repair_scope(
        [
            {"category": "kitchen", "estimated_cost_cents": 2_500_000},
            {
                "category": "roof",
                "scope_status": "no_work",
                "pricing_method": "catalog",
                "quantity": 20,
            },
        ],
        contingency_percentage=20,
    )

    assert result["subtotal_low_cents"] == 2_500_000
    assert result["subtotal_expected_cents"] == 2_500_000
    assert result["subtotal_high_cents"] == 2_500_000
    assert result["total_expected_cents"] == 3_000_000


def test_saved_catalog_scope_keeps_its_original_version_and_range() -> None:
    result = evaluate_repair_scope(
        [
            {
                "category": "roof",
                "scope_status": "replace",
                "severity": "standard",
                "quantity": 20,
                "pricing_method": "catalog",
                "catalog_version": "ga-2026.06-v0",
                "system_low_cents": 800_000,
                "system_expected_cents": 1_100_000,
                "system_high_cents": 1_500_000,
                "estimated_cost_cents": 1_100_000,
            }
        ],
        contingency_percentage=10,
    )

    assert result["version"] == "ga-2026.06-v0"
    assert result["subtotal_low_cents"] == 800_000
    assert result["subtotal_expected_cents"] == 1_100_000
    assert result["subtotal_high_cents"] == 1_500_000


def test_new_scope_discards_client_supplied_catalog_prices() -> None:
    prepared = prepare_new_scope_items(
        [
            {
                "category": "roof",
                "pricing_method": "catalog",
                "catalog_version": "invented-version",
                "system_low_cents": 1,
                "system_expected_cents": 2,
                "system_high_cents": 3,
            }
        ]
    )

    assert prepared[0]["catalog_version"] is None
    assert prepared[0]["system_low_cents"] is None
    assert prepared[0]["system_expected_cents"] is None
    assert prepared[0]["system_high_cents"] is None
