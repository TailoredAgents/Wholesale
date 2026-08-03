from typing import Any

import pytest

from app.integrations.dealmachine_client import DealMachineError
from app.services.underwriting_comparable_evidence import (
    ComparableProviderBatch,
    ComparableProviderResponse,
    capture_provider_batch,
    credit_metadata_from_dealmachine,
    merge_comparable_batches,
    normalize_address_key,
    normalize_dealmachine_comparable,
    normalize_rentcast_comparable,
    provider_batch_from_response,
)
from app.services.underwriting_v2 import (
    analyze_recorded_sales,
    apply_comp_review,
    score_recorded_sale,
)


@pytest.fixture
def rentcast_sale() -> dict[str, Any]:
    return {
        "id": "rentcast-comp-1",
        "formattedAddress": "101 North Main Street, Atlanta, GA 30303",
        "lastSalePrice": 250000,
        "lastSaleDate": "2026-05-15T00:00:00Z",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1600,
        "yearBuilt": 1985,
        "latitude": 33.75,
        "longitude": -84.39,
        "lotSize": 8712,
        "features": {"garage": True, "garageSpaces": 1, "pool": False},
        "_stonegateSearchLevel": "preferred",
    }


@pytest.fixture
def dealmachine_sale() -> dict[str, Any]:
    return {
        "dm_property_id": "prop_comp_1",
        "type": "sale",
        "full_address": "101 N Main St., Atlanta, GA 30303",
        "sale_price": 250000,
        "sale_date": "2026-05-15",
        "property_type": ["Single Family"],
        "bedrooms": 3,
        "bathrooms": 2,
        "sqft": 1600,
        "year_built": 1985,
        "latitude": 33.75,
        "longitude": -84.39,
        "lot_size_acres": 0.2,
        "garage_type": ["Attached"],
        "pool": ["No"],
        "basement": "None",
        "distance": 0.3,
        "match_score": {"overall": 94},
        "owner_1_full_name": "Private Owner",
        "contacts": [{"phone": "4045550100"}],
    }


def _rentcast_batch(record: dict[str, Any]) -> ComparableProviderBatch:
    return provider_batch_from_response(
        provider="rentcast",
        response=ComparableProviderResponse(records=[record]),
        normalizer=normalize_rentcast_comparable,
    )


def _dealmachine_batch(record: dict[str, Any]) -> ComparableProviderBatch:
    return provider_batch_from_response(
        provider="dealmachine",
        response=ComparableProviderResponse(records=[record]),
        normalizer=normalize_dealmachine_comparable,
    )


def test_same_sale_is_merged_without_double_counting(
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    evidence = merge_comparable_batches(
        [_rentcast_batch(rentcast_sale), _dealmachine_batch(dealmachine_sale)]
    )

    assert len(evidence.comparables) == 1
    assert evidence.source_observation_count == 2
    assert evidence.duplicate_observation_count == 1
    record = evidence.to_underwriting_records()[0]
    assert record["id"] == "rentcast-comp-1"
    assert record["formattedAddress"] == rentcast_sale["formattedAddress"]
    assert record["lastSalePrice"] == 250000
    assert record["lastSaleDate"] == "2026-05-15"
    assert record["source_providers"] == ["rentcast", "dealmachine"]
    assert record["corroborated"] is True
    assert record["field_conflicts"] == []
    assert record["_stonegateProviderIds"] == {
        "rentcast": ["rentcast-comp-1"],
        "dealmachine": ["prop_comp_1"],
    }
    assert evidence.metadata()["provider_duplicate_count"] == 1


def test_conflicting_provider_facts_are_visible_and_resolved_deterministically(
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["sale_price"] = 275000
    dealmachine_sale["sqft"] = 1650
    evidence = merge_comparable_batches(
        [_dealmachine_batch(dealmachine_sale), _rentcast_batch(rentcast_sale)]
    )

    assert len(evidence.comparables) == 1
    record = evidence.to_underwriting_records()[0]
    assert record["lastSalePrice"] == 250000
    assert record["squareFootage"] == 1600
    conflicts = {item["field"]: item for item in record["field_conflicts"]}
    assert conflicts["sale_price"]["selected_value"] == 250000
    assert conflicts["square_footage"]["selected_value"] == 1600
    assert {item["provider"] for item in conflicts["sale_price"]["observations"]} == {
        "rentcast",
        "dealmachine",
    }
    assert record["source_overlap_count"] == 2
    assert record["corroborated"] is False
    assert evidence.metadata()["provider_conflict_count"] == 2


def test_minor_recording_date_difference_is_merged_and_reported(
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["sale_date"] = "2026-05-17"
    evidence = merge_comparable_batches(
        [_rentcast_batch(rentcast_sale), _dealmachine_batch(dealmachine_sale)]
    )

    assert len(evidence.comparables) == 1
    record = evidence.to_underwriting_records()[0]
    assert record["lastSaleDate"] == "2026-05-15"
    conflicts = {item["field"]: item for item in record["field_conflicts"]}
    assert conflicts["sale_date"]["material"] is False
    assert conflicts["sale_date"]["severity"] == "review"
    assert evidence.metadata()["provider_conflict_count"] == 0


@pytest.mark.parametrize(
    ("sale_date", "sale_price", "conflict_field"),
    [
        ("2026-05-26", 250000, "sale_date"),
        ("2026-05-19", 270000, "sale_price"),
    ],
)
def test_probable_same_transfer_material_disagreements_merge_for_review(
    sale_date: str,
    sale_price: int,
    conflict_field: str,
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["sale_date"] = sale_date
    dealmachine_sale["sale_price"] = sale_price

    evidence = merge_comparable_batches(
        [_rentcast_batch(rentcast_sale), _dealmachine_batch(dealmachine_sale)]
    )

    assert len(evidence.comparables) == 1
    record = evidence.to_underwriting_records()[0]
    conflicts = {item["field"]: item for item in record["field_conflicts"]}
    assert conflicts[conflict_field]["material"] is True
    assert record["corroborated"] is False
    assert evidence.metadata()["provider_conflict_count"] >= 1


def test_minor_physical_and_coordinate_differences_remain_auditable_not_material(
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["sqft"] = 1_601
    dealmachine_sale["latitude"] = 33.7502
    dealmachine_sale["longitude"] = -84.3902
    evidence = merge_comparable_batches(
        [_rentcast_batch(rentcast_sale), _dealmachine_batch(dealmachine_sale)]
    )

    conflicts = {
        item["field"]: item for item in evidence.to_underwriting_records()[0]["field_conflicts"]
    }
    assert {"square_footage", "latitude", "longitude"}.issubset(conflicts)
    assert all(conflicts[field]["material"] is False for field in conflicts)
    assert evidence.metadata()["provider_conflict_count"] == 0


def test_distinct_sales_at_same_address_are_not_merged(
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["sale_date"] = "2024-01-15"
    dealmachine_sale["sale_price"] = 180000

    evidence = merge_comparable_batches(
        [_rentcast_batch(rentcast_sale), _dealmachine_batch(dealmachine_sale)]
    )

    assert len(evidence.comparables) == 2
    assert evidence.duplicate_observation_count == 0


def test_provider_failure_is_isolated_from_other_evidence(
    rentcast_sale: dict[str, Any],
) -> None:
    def unavailable() -> ComparableProviderResponse:
        raise DealMachineError("DealMachine is temporarily unavailable.")

    failed = capture_provider_batch(
        provider="dealmachine",
        fetch=unavailable,
        normalizer=normalize_dealmachine_comparable,
    )
    evidence = merge_comparable_batches([_rentcast_batch(rentcast_sale), failed])

    assert failed.status == "failed"
    assert failed.error == "DealMachine is temporarily unavailable."
    assert len(evidence.to_underwriting_records()) == 1
    provider_metadata = evidence.metadata()["providers"]
    assert provider_metadata[1]["status"] == "failed"


def test_dealmachine_normalizer_excludes_listings_and_maps_property_facts(
    dealmachine_sale: dict[str, Any],
) -> None:
    observation = normalize_dealmachine_comparable(dealmachine_sale)
    assert observation is not None
    assert observation.values["sale_price"] == 250000
    assert observation.values["sale_date"] == "2026-05-15"
    assert observation.values["lot_size"] == 8712
    assert observation.values["garage"] is True
    assert observation.values["pool"] is False
    assert observation.values["basement"] is False
    assert observation.values["match_score"] == 94
    evidence = merge_comparable_batches([_dealmachine_batch(dealmachine_sale)])
    output = evidence.to_underwriting_records()[0]
    assert "contacts" not in output
    assert "owner_1_full_name" not in output

    dealmachine_sale["type"] = "active_listing"
    assert normalize_dealmachine_comparable(dealmachine_sale) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("No Garage", False),
        ("No Basement", False),
        ("No Pool", False),
        ("0 Car", False),
        ("Unknown", None),
        ("N/A", None),
        ("Attached Garage", True),
    ],
)
def test_dealmachine_feature_labels_are_parsed_without_false_positives(
    dealmachine_sale: dict[str, Any],
    value: str,
    expected: bool | None,
) -> None:
    dealmachine_sale["garage_type"] = value

    observation = normalize_dealmachine_comparable(dealmachine_sale)

    assert observation is not None
    assert observation.values["garage"] is expected


def test_explicit_no_basement_survives_normalization_and_underwriting_round_trip(
    dealmachine_sale: dict[str, Any],
) -> None:
    dealmachine_sale["basement"] = "No Basement"
    evidence = merge_comparable_batches([_dealmachine_batch(dealmachine_sale)])
    record = evidence.to_underwriting_records()[0]

    scored = score_recorded_sale(
        {
            "formattedAddress": "100 Subject St, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_600,
            "yearBuilt": 1985,
            "lotSize": 8_700,
            "features": {"garage": True, "pool": False, "basement": False},
        },
        record,
        condition_overrides={},
    )

    assert record["features"]["basement"] is False
    assert scored.basement is False


def test_provider_batch_separates_dropped_rows_from_true_duplicates(
    dealmachine_sale: dict[str, Any],
) -> None:
    active_listing = {**dealmachine_sale, "dm_property_id": "listing", "type": "listing"}
    batch = provider_batch_from_response(
        provider="dealmachine",
        response=ComparableProviderResponse(
            records=[dealmachine_sale, dict(dealmachine_sale), active_listing]
        ),
        normalizer=normalize_dealmachine_comparable,
    )

    assert batch.raw_count == 3
    assert batch.normalized_count == 2
    assert batch.retained_count == 1
    assert batch.usable_count == 1
    assert batch.dropped_count == 1
    assert batch.duplicate_count == 1
    assert batch.valuation_eligible_count == 1
    assert batch.ineligible_transfer_count == 0
    assert batch.warnings


def test_dealmachine_street_display_line_is_assembled_with_locality() -> None:
    observation = normalize_dealmachine_comparable(
        {
            "dm_property_id": "subject-variant",
            "type": "sale",
            "display_line_1": "500 Subject Street",
            "city": "Atlanta",
            "state": "GA",
            "zip": "30303-1234",
            "sale_price": 300000,
            "sale_date": "2026-05-01",
            "property_type": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "sqft": 1600,
            "year_built": 1985,
        }
    )

    assert observation is not None
    assert normalize_address_key(observation.values["formatted_address"]) == (
        normalize_address_key("500 Subject St, Atlanta, GA 30303")
    )


@pytest.mark.parametrize(
    ("provider", "transaction_updates", "reason_fragment"),
    [
        (
            "rentcast",
            {"lastSaleDocumentType": "Quit Claim Deed"},
            "non-market transfer",
        ),
        (
            "dealmachine",
            {"foreclosure": True, "sale_doc_type": "Foreclosure Sale"},
            "foreclosure",
        ),
    ],
)
def test_non_market_transfers_are_retained_for_audit_but_rejected_from_arv(
    provider: str,
    transaction_updates: dict[str, Any],
    reason_fragment: str,
    rentcast_sale: dict[str, Any],
    dealmachine_sale: dict[str, Any],
) -> None:
    if provider == "rentcast":
        rentcast_sale.update(transaction_updates)
        evidence = merge_comparable_batches([_rentcast_batch(rentcast_sale)])
    else:
        dealmachine_sale.update(transaction_updates)
        evidence = merge_comparable_batches([_dealmachine_batch(dealmachine_sale)])
    records = evidence.to_underwriting_records()
    selected, rejected = analyze_recorded_sales(
        {
            "formattedAddress": "500 Subject St, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_600,
            "yearBuilt": 1985,
        },
        records,
        condition_overrides={},
    )

    assert records[0]["_stonegateTransactionEligibility"] == "ineligible"
    assert selected == []
    assert len(rejected) == 1
    assert reason_fragment in rejected[0].selection_reason.lower()


def test_nominal_consideration_is_rejected_even_without_document_type(
    rentcast_sale: dict[str, Any],
) -> None:
    rentcast_sale["lastSalePrice"] = 500
    evidence = merge_comparable_batches([_rentcast_batch(rentcast_sale)])
    selected, rejected = analyze_recorded_sales(
        {
            "formattedAddress": "500 Subject St, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_600,
            "yearBuilt": 1985,
        },
        evidence.to_underwriting_records(),
        condition_overrides={},
    )

    assert selected == []
    assert "nominal" in rejected[0].selection_reason.lower()


def test_human_review_cannot_override_non_market_transfer_exclusion(
    rentcast_sale: dict[str, Any],
) -> None:
    ordinary_sale = dict(rentcast_sale)
    ordinary_sale["id"] = "ordinary-sale"
    ordinary_sale["formattedAddress"] = "102 North Main Street, Atlanta, GA 30303"
    non_market_sale = dict(rentcast_sale)
    non_market_sale["id"] = "quitclaim-sale"
    non_market_sale["formattedAddress"] = "103 North Main Street, Atlanta, GA 30303"
    non_market_sale["lastSaleDocumentType"] = "Quit Claim Deed"
    evidence = merge_comparable_batches(
        [_rentcast_batch(ordinary_sale), _rentcast_batch(non_market_sale)]
    )
    selected, rejected = analyze_recorded_sales(
        {
            "formattedAddress": "500 Subject St, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_600,
            "yearBuilt": 1985,
        },
        evidence.to_underwriting_records(),
        condition_overrides={},
    )
    decisions = [
        {
            "comp_key": comp.provider_id or comp.formatted_address,
            "included": True,
            "reason": "Attempted reviewer inclusion",
            "weight_percentage": 100,
        }
        for comp in [*selected, *rejected]
    ]

    with pytest.raises(ValueError, match="non-market or nominal transfer"):
        apply_comp_review(selected, rejected, decisions=decisions)


def test_dealmachine_credit_metadata_preserves_zero_deduplication() -> None:
    metadata = credit_metadata_from_dealmachine(
        {"used": 1, "properties": 1, "people": 0, "deduplicated": 0},
        operation="underwriting_comps",
    )

    assert metadata.used == 1
    assert metadata.properties == 1
    assert metadata.people == 0
    assert metadata.deduplicated == 0
    assert metadata.to_dict()["raw"]["used"] == 1


def test_address_key_normalizes_common_direction_and_suffix_variants() -> None:
    assert normalize_address_key("101 North Main Street, Atlanta, GA 30303-1234") == (
        normalize_address_key("101 N. Main St., Atlanta, GA 30303")
    )
