from copy import deepcopy

from app.services.disposition_buyer_pool import _land_asset_match


def _criteria() -> dict[str, object]:
    return {
        "asset_class": "land",
        "min_acres": 5,
        "max_acres": 20,
        "intended_uses": ["residential"],
        "zoning_codes": ["R-1"],
        "access_preferences": ["legal_access"],
        "utility_preferences": ["public_water", "septic"],
        "terrain_preferences": [],
        "flood_zone_tolerance": "accepted",
        "wetlands_tolerance": "accepted",
        "exclusions": [],
    }


def _subject() -> dict[str, object]:
    return {
        "identity": {
            "parcel_id": "LAND-MATCH-1",
            "normalized_parcel_key": "GA|FULTON|LANDMATCH1",
            "county": "Fulton",
            "state": "GA",
        },
        "property_intelligence": {
            "is_fresh": True,
            "conflict_fields": [],
            "facts": {
                "zoning": {"value": "R-1"},
                "water": {"value": "Public water"},
                "sewer": {"value": "Septic"},
            },
        },
        "valuation": {
            "uses_current_fresh_property_snapshot": True,
            "subject_acres": 10,
            "land_use": "Residential vacant land",
            "access_evidence_status": "verified",
        },
    }


def test_land_asset_match_uses_frozen_acreage_use_and_diligence_evidence() -> None:
    eligible, reasons, checks = _land_asset_match(_criteria(), _subject())

    assert eligible is True
    assert reasons == []
    assert checks["acreage"]["status"] == "matched"
    assert checks["intended_use"]["status"] == "matched"
    assert checks["zoning"]["status"] == "matched"
    assert checks["access"]["status"] == "matched"
    assert checks["utilities"]["status"] == "matched"


def test_land_asset_match_fails_closed_for_mismatch_or_untrusted_evidence() -> None:
    acreage_mismatch = _subject()
    acreage_mismatch["valuation"]["subject_acres"] = 50  # type: ignore[index]
    eligible, reasons, checks = _land_asset_match(_criteria(), acreage_mismatch)
    assert eligible is False
    assert checks["acreage"]["status"] == "mismatch"
    assert any("outside" in reason.lower() for reason in reasons)

    untrusted = deepcopy(_subject())
    untrusted["valuation"]["uses_current_fresh_property_snapshot"] = False  # type: ignore[index]
    untrusted["property_intelligence"]["is_fresh"] = False  # type: ignore[index]
    eligible, reasons, checks = _land_asset_match(_criteria(), untrusted)
    assert eligible is False
    assert checks["acreage"]["status"] == "review_required"
    assert checks["zoning"]["status"] == "review_required"
    assert any("unavailable" in reason.lower() for reason in reasons)


def test_land_asset_match_requires_human_review_for_unsupported_preferences() -> None:
    criteria = _criteria()
    criteria["terrain_preferences"] = ["wooded"]
    criteria["flood_zone_tolerance"] = "avoid"
    criteria["wetlands_tolerance"] = "review"

    eligible, reasons, checks = _land_asset_match(criteria, _subject())

    assert eligible is False
    assert checks["terrain"]["status"] == "review_required"
    assert checks["flood_zone"]["status"] == "review_required"
    assert checks["wetlands"]["status"] == "review_required"
    assert len(reasons) == 3
