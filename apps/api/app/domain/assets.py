from __future__ import annotations

import re
from typing import Any, Literal

AssetClass = Literal["house", "land"]

HOUSE_ASSET_CLASS: AssetClass = "house"
LAND_ASSET_CLASS: AssetClass = "land"
ASSET_CLASSES = frozenset({HOUSE_ASSET_CLASS, LAND_ASSET_CLASS})

HOUSE_RESEARCH_PROFILE = "house_v1"
LAND_RESEARCH_PROFILE = "land_v1"
HOUSE_VALUATION_PROFILE = "house_v3"
LAND_VALUATION_PROFILE = "land_v1"

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")

LAND_PROPERTY_TYPE_KEYS = frozenset(
    {
        "land",
        "lot",
        "lots_land",
        "residential_land",
        "vacant_land",
        "vacant_lot",
    }
)


class AssetWorkflowUnavailableError(Exception):
    """Raised when an asset is intentionally blocked from an incompatible workflow."""


def require_house_workflow(
    asset_class: Any,
    *,
    workflow: str = "Residential valuation and offer",
) -> None:
    if normalize_asset_class(asset_class) == LAND_ASSET_CLASS:
        raise AssetWorkflowUnavailableError(
            f"{workflow} is not available for Land leads yet. "
            "Stonegate has blocked the residential workflow until the dedicated Land workflow "
            "is implemented and verified."
        )


def require_land_workflow_enabled(enabled: bool) -> None:
    if not enabled:
        raise AssetWorkflowUnavailableError(
            "Land workflows are disabled. Enable LAND_WORKFLOW_ENABLED only after the current "
            "Land phase has been verified for production."
        )


def normalize_asset_class(value: Any, *, default: AssetClass = HOUSE_ASSET_CLASS) -> AssetClass:
    normalized = normalize_key(value)
    if normalized in ASSET_CLASSES:
        return normalized
    return default


def asset_class_for_property_type(
    property_type: Any,
    *,
    explicit_asset_class: Any = None,
) -> AssetClass:
    explicit = normalize_key(explicit_asset_class)
    if explicit in ASSET_CLASSES:
        return explicit
    return (
        LAND_ASSET_CLASS
        if normalize_key(property_type) in LAND_PROPERTY_TYPE_KEYS
        else HOUSE_ASSET_CLASS
    )


def research_profile_for_asset(asset_class: Any) -> str:
    return (
        LAND_RESEARCH_PROFILE
        if normalize_asset_class(asset_class) == LAND_ASSET_CLASS
        else HOUSE_RESEARCH_PROFILE
    )


def valuation_profile_for_asset(asset_class: Any) -> str:
    return (
        LAND_VALUATION_PROFILE
        if normalize_asset_class(asset_class) == LAND_ASSET_CLASS
        else HOUSE_VALUATION_PROFILE
    )


def normalize_parcel_id(value: Any) -> str:
    """Normalize an assessor parcel number without discarding meaningful zeroes."""
    return _NON_ALPHANUMERIC.sub("", str(value or "").strip().upper())


def parcel_identity_key(
    parcel_id: Any,
    *,
    county: Any,
    state: Any,
) -> str | None:
    """Return a county-scoped parcel identity suitable for matching and cache keys."""
    normalized_parcel = normalize_parcel_id(parcel_id)
    normalized_county = _NON_ALPHANUMERIC.sub(
        "_", str(county or "").strip().upper()
    ).strip("_").lower()
    if normalized_county.endswith("_county"):
        normalized_county = normalized_county[: -len("_county")]
    normalized_state = str(state or "").strip().upper()
    if not normalized_parcel or not normalized_county or len(normalized_state) != 2:
        return None
    return f"{normalized_state}|{normalized_county}|{normalized_parcel}"


def property_identity_label(
    *,
    street_address: Any,
    city: Any,
    state: Any,
    postal_code: Any = None,
    parcel_id: Any = None,
    county: Any = None,
) -> str:
    """Format an addressed property or a parcel-only Land identity for staff UI."""
    street = str(street_address or "").strip()
    clean_city = str(city or "").strip()
    clean_state = str(state or "").strip()
    postal = str(postal_code or "").strip()
    parcel = str(parcel_id or "").strip()
    clean_county = str(county or "").strip()
    if street:
        locality = " ".join(value for value in (clean_state, postal) if value)
        return ", ".join(value for value in (street, clean_city, locality) if value)
    if parcel:
        return ", ".join(
            value for value in (f"APN {parcel}", clean_county, clean_state) if value
        )
    locality = " ".join(value for value in (clean_state, postal) if value)
    return ", ".join(value for value in (clean_city, locality) if value)


def normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return "_".join(str(value).strip().lower().replace("-", " ").split())
