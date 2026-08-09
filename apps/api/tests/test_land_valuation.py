from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.land_underwriting import LandValuationCreate
from app.services.land_comparable_evidence import evaluate_land_sales
from app.services.land_valuation import analyze_land_valuation

ACTIVE_POLICY = {
    "quick_sale_discount_low_basis_points": 1500,
    "quick_sale_discount_high_basis_points": 2500,
    "opening_reserve_basis_points": 1000,
    "assignment_fee_cents": 1_500_000,
    "closing_title_reserve_cents": 300_000,
    "curative_reserve_cents": 500_000,
    "uncertainty_reserve_cents": 500_000,
    "maximum_dispersion_basis_points": 5000,
    "minimum_comparable_count": 3,
}


def comparable(
    indication_cents: int,
    *,
    tier: str = "preferred",
    use: str | None = "residential land",
    weight: float = 1 / 3,
) -> dict[str, object]:
    return {
        "subject_indication_cents": indication_cents,
        "evidence_tier": tier,
        "property_use": use,
        "weight": weight,
    }


def analyze(
    comps: list[dict[str, object]],
    **overrides: object,
) -> dict[str, object]:
    inputs: dict[str, object] = {
        "selected_comps": comps,
        "subject_acres": Decimal("2.0000"),
        "subject_lot_count": None,
        "valuation_basis": "per_acre",
        "subject_parcel_id": "12-345-678",
        "subject_use": "residential land",
        "subject_coordinates_available": True,
        "access_evidence_status": "verified",
        "access_evidence_reference": "County GIS road-frontage review",
        "snapshot_is_fresh": True,
        "subject_identity_conflicted": False,
        "active_policy": ACTIVE_POLICY,
    }
    inputs.update(overrides)
    return analyze_land_valuation(**inputs)  # type: ignore[arg-type]


def test_land_value_and_offer_guidance_are_deterministic() -> None:
    comps = [
        comparable(10_000_000),
        comparable(12_000_000),
        comparable(14_000_000),
    ]

    result = analyze(comps)
    reordered = analyze(list(reversed(comps)))

    assert result == reordered
    assert result["status"] == "ready"
    assert result["guidance_status"] == "available"
    assert result["supported_value_low_cents"] == 10_000_000
    assert result["supported_value_cents"] == 12_000_000
    assert result["supported_value_high_cents"] == 14_000_000
    assert result["quick_sale_low_cents"] == 7_500_000
    assert result["quick_sale_high_cents"] == 10_200_000
    assert result["seller_contract_ceiling_cents"] == 4_700_000
    assert result["opening_offer_cents"] == 4_230_000


def test_land_value_range_can_exist_while_offer_guidance_is_withheld() -> None:
    result = analyze(
        [
            comparable(10_000_000),
            comparable(12_000_000),
            comparable(14_000_000),
        ],
        access_evidence_status="reported",
        access_evidence_reference="Seller says there is a driveway",
        active_policy=None,
    )

    assert result["supported_value_cents"] == 12_000_000
    assert result["guidance_status"] == "withheld"
    assert result["opening_offer_cents"] is None
    assert result["seller_contract_ceiling_cents"] is None
    assert "No owner-approved Land offer policy is active." in result["guidance_blockers"]
    assert (
        "Legal access has not been human-verified with evidence."
        in result["guidance_blockers"]
    )


def test_extended_or_unknown_use_evidence_cannot_produce_offer_guidance() -> None:
    result = analyze(
        [
            comparable(10_000_000, tier="extended"),
            comparable(12_000_000),
            comparable(14_000_000, use=None),
        ]
    )

    assert result["status"] == "needs_review"
    assert result["guidance_status"] == "withheld"
    assert result["opening_offer_cents"] is None
    assert any("Extended-tier" in item for item in result["guidance_blockers"])
    assert any("identified Land use" in item for item in result["guidance_blockers"])


def test_insufficient_or_dispersed_sales_fail_closed() -> None:
    insufficient = analyze([comparable(10_000_000), comparable(11_000_000)])
    dispersed = analyze(
        [
            comparable(5_000_000),
            comparable(10_000_000),
            comparable(20_000_000),
        ]
    )

    assert insufficient["status"] == "insufficient_evidence"
    assert insufficient["supported_value_cents"] is None
    assert insufficient["guidance_status"] == "withheld"
    assert dispersed["supported_value_cents"] == 10_000_000
    assert dispersed["guidance_status"] == "withheld"
    assert any("dispersion" in item.lower() for item in dispersed["guidance_blockers"])


def test_unmapped_subject_zoning_is_not_treated_as_verified_land_use() -> None:
    result = analyze(
        [
            comparable(10_000_000),
            comparable(12_000_000),
            comparable(14_000_000),
        ],
        subject_use="R-1",
    )

    assert result["supported_value_cents"] == 12_000_000
    assert result["guidance_status"] == "withheld"
    assert any("supported use group" in item for item in result["guidance_blockers"])


def test_human_land_use_override_requires_an_evidence_reference() -> None:
    with pytest.raises(ValidationError, match="Land use group requires an evidence reference"):
        LandValuationCreate(subject_use_override="residential")

    payload = LandValuationCreate(
        subject_use_override="residential",
        subject_use_evidence_reference="County zoning map reviewed by owner",
    )
    assert payload.subject_use_override == "residential"


def test_comparable_with_unmapped_land_use_is_rejected() -> None:
    selected, rejected = evaluate_land_sales(
        [
            {
                "key": "GA|fulton|COMP1",
                "property_type": "LAND",
                "property_use": "VACANT LAND",
                "sale_price_cents": 10_000_000,
                "sale_date": "2026-01-01",
                "days_old": 100,
                "subject_indication_cents": 10_000_000,
                "evidence_tier": "preferred",
                "score": 90,
            }
        ],
        subject_parcel_id="SUBJECT",
        subject_county="Fulton",
        subject_state="GA",
        subject_use="residential",
        selected_keys=None,
    )

    assert selected == []
    assert rejected[0]["selection_reason"] == "The comparable Land use is unknown."
