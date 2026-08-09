from app.domain.assets import (
    asset_class_for_property_type,
    normalize_asset_class,
    normalize_parcel_id,
    parcel_identity_key,
    property_identity_label,
    research_profile_for_asset,
    valuation_profile_for_asset,
)


def test_asset_class_uses_explicit_value_before_property_type() -> None:
    assert asset_class_for_property_type("single_family", explicit_asset_class="land") == "land"
    assert asset_class_for_property_type("land", explicit_asset_class="house") == "house"


def test_land_property_type_aliases_resolve_to_land() -> None:
    assert asset_class_for_property_type("Vacant Land") == "land"
    assert asset_class_for_property_type("residential-land") == "land"
    assert asset_class_for_property_type("single_family") == "house"


def test_unknown_asset_class_fails_safe_to_house_compatibility() -> None:
    assert normalize_asset_class(None) == "house"
    assert normalize_asset_class("commercial") == "house"


def test_asset_profiles_are_isolated() -> None:
    assert research_profile_for_asset("house") == "house_v1"
    assert research_profile_for_asset("land") == "land_v1"
    assert valuation_profile_for_asset("house") == "house_v3"
    assert valuation_profile_for_asset("land") == "land_v1"


def test_parcel_identity_normalizes_format_without_losing_zeroes() -> None:
    assert normalize_parcel_id(" 0012-03-A.004 ") == "001203A004"
    assert parcel_identity_key(
        " 0012-03-A.004 ", county="Fulton County", state="ga"
    ) == "GA|fulton|001203A004"
    assert parcel_identity_key(
        "001203A004", county="Fulton", state="GA"
    ) == "GA|fulton|001203A004"


def test_parcel_identity_is_county_scoped_and_requires_complete_scope() -> None:
    fulton = parcel_identity_key("001-002", county="Fulton", state="GA")
    cobb = parcel_identity_key("001-002", county="Cobb", state="GA")

    assert fulton == "GA|fulton|001002"
    assert cobb == "GA|cobb|001002"
    assert fulton != cobb
    assert parcel_identity_key("001-002", county=None, state="GA") is None
    assert parcel_identity_key("001-002", county="Fulton", state="Georgia") is None


def test_property_identity_label_preserves_house_address_format() -> None:
    assert property_identity_label(
        street_address="123 Peachtree St",
        city="Atlanta",
        state="GA",
        postal_code="30303",
    ) == "123 Peachtree St, Atlanta, GA 30303"


def test_property_identity_label_supports_parcel_only_land() -> None:
    assert property_identity_label(
        street_address=None,
        city=None,
        state="GA",
        parcel_id="APN-45-100",
        county="Pickens County",
    ) == "APN APN-45-100, Pickens County, GA"
