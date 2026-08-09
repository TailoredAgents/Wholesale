from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.assets import (
    LAND_ASSET_CLASS,
    normalize_asset_class,
    normalize_parcel_id,
    parcel_identity_key,
)
from app.models.foundation import Property
from app.services.property_validation import (
    canonical_address_key,
    normalize_postal_code,
    normalize_street,
    normalize_words,
)

PROPERTY_IDENTITY_CONFLICT_MESSAGE = (
    "The supplied address and APN conflict with the existing property record. "
    "Review the property identity before continuing."
)


def has_complete_address(
    *,
    street_address: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None,
) -> bool:
    if not all(
        value and value.strip()
        for value in (street_address, city, state, postal_code)
    ):
        return False
    return bool(
        street_address
        and not street_address.strip().lower().startswith("address pending")
        and city
        and city.strip().lower() != "unknown"
        and postal_code
        and postal_code.strip().lower() != "unknown"
    )


def normalized_address_key_or_none(
    *,
    street_address: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None,
) -> str | None:
    if not has_complete_address(
        street_address=street_address,
        city=city,
        state=state,
        postal_code=postal_code,
    ):
        return None
    return canonical_address_key(
        street_address or "",
        city or "",
        state or "",
        postal_code or "",
    )


def refresh_property_identity_keys(property_record: Property) -> None:
    property_record.normalized_address_key = normalized_address_key_or_none(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state,
        postal_code=property_record.postal_code,
    )
    property_record.normalized_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )


def require_valid_property_identity(property_record: Property, *, asset_class: str) -> None:
    refresh_property_identity_keys(property_record)
    if normalize_asset_class(asset_class) == LAND_ASSET_CLASS:
        if property_record.normalized_address_key or property_record.normalized_parcel_key:
            return
        raise ValueError(
            "Land leads require either a complete address or APN with county and state."
        )
    if property_record.normalized_address_key is None:
        raise ValueError("House leads require a complete street address, city, state, and ZIP.")


def find_property_by_identity(
    db: Session,
    *,
    organization_id: UUID,
    street_address: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None,
    parcel_id: str | None,
    county: str | None,
) -> tuple[Property | None, str | None, str | None]:
    address_key = normalized_address_key_or_none(
        street_address=street_address,
        city=city,
        state=state,
        postal_code=postal_code,
    )
    parcel_key = parcel_identity_key(parcel_id, county=county, state=state)
    parcel_matches = (
        db.scalars(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.normalized_parcel_key == parcel_key,
            ).limit(2)
        ).all()
        if parcel_key
        else []
    )
    address_matches = (
        db.scalars(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.normalized_address_key == address_key,
            ).limit(2)
        ).all()
        if address_key
        else []
    )
    if len(parcel_matches) > 1 or len(address_matches) > 1:
        raise ValueError(
            "Multiple property records share this identity. Review and merge the duplicate "
            "properties before continuing."
        )
    parcel_match = parcel_matches[0] if parcel_matches else None
    address_match = address_matches[0] if address_matches else None
    if (
        parcel_match is not None
        and address_match is not None
        and parcel_match.id != address_match.id
    ):
        raise ValueError(
            "The APN and address match different property records. Review the property identity "
            "before continuing."
        )
    match = parcel_match or address_match
    if match is not None and address_key is not None and parcel_key is not None:
        require_compatible_supplied_identities(
            match,
            street_address=street_address or "",
            city=city or "",
            state=state or "",
            postal_code=postal_code or "",
            parcel_id=parcel_id or "",
            county=county or "",
            address_key=address_key,
            parcel_key=parcel_key,
        )
        enrich_missing_property_identity(
            match,
            street_address=street_address or "",
            city=city or "",
            state=state or "",
            postal_code=postal_code or "",
            parcel_id=parcel_id or "",
            county=county or "",
            address_key=address_key,
            parcel_key=parcel_key,
        )
    return match, address_key, parcel_key


def require_compatible_supplied_identities(
    property_record: Property,
    *,
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
    parcel_id: str,
    county: str,
    address_key: str,
    parcel_key: str,
) -> None:
    """Fail closed when a dual identity contradicts the matched property."""
    stored_address_key = normalized_address_key_or_none(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state,
        postal_code=property_record.postal_code,
    )
    stored_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )
    if stored_address_key is not None and stored_address_key != address_key:
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)
    if stored_parcel_key is not None and stored_parcel_key != parcel_key:
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)
    if stored_address_key is None and partial_address_conflicts(
        property_record,
        street_address=street_address,
        city=city,
        state=state,
        postal_code=postal_code,
    ):
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)
    if stored_parcel_key is None and partial_parcel_identity_conflicts(
        property_record,
        parcel_id=parcel_id,
        county=county,
        state=state,
        parcel_key=parcel_key,
    ):
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)


def enrich_missing_property_identity(
    property_record: Property,
    *,
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
    parcel_id: str,
    county: str,
    address_key: str,
    parcel_key: str,
) -> None:
    """Add a missing counterpart only after the dual identity passes conflict checks."""
    stored_address_key = normalized_address_key_or_none(
        street_address=property_record.street_address,
        city=property_record.city,
        state=property_record.state,
        postal_code=property_record.postal_code,
    )
    stored_parcel_key = parcel_identity_key(
        property_record.parcel_id,
        county=property_record.county,
        state=property_record.state,
    )
    if stored_address_key is None:
        property_record.street_address = street_address.strip()
        property_record.city = city.strip()
        property_record.state = state.strip().upper()
        property_record.postal_code = postal_code.strip()
    if stored_parcel_key is None:
        if not normalize_parcel_id(property_record.parcel_id):
            property_record.parcel_id = parcel_id.strip()
        if not (property_record.county and property_record.county.strip()):
            property_record.county = county.strip()
    refresh_property_identity_keys(property_record)
    if property_record.normalized_address_key != address_key:
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)
    if property_record.normalized_parcel_key != parcel_key:
        raise ValueError(PROPERTY_IDENTITY_CONFLICT_MESSAGE)


def partial_address_conflicts(
    property_record: Property,
    *,
    street_address: str,
    city: str,
    state: str,
    postal_code: str,
) -> bool:
    stored_street = meaningful_street(property_record.street_address)
    stored_city = meaningful_component(property_record.city)
    stored_state = meaningful_component(property_record.state)
    stored_postal = meaningful_postal_code(property_record.postal_code)
    return bool(
        (stored_street and normalize_street(stored_street) != normalize_street(street_address))
        or (stored_city and normalize_words(stored_city) != normalize_words(city))
        or (stored_state and normalize_words(stored_state) != normalize_words(state))
        or (stored_postal and stored_postal != normalize_postal_code(postal_code))
    )


def partial_parcel_identity_conflicts(
    property_record: Property,
    *,
    parcel_id: str,
    county: str,
    state: str,
    parcel_key: str,
) -> bool:
    stored_parcel = normalize_parcel_id(property_record.parcel_id)
    if stored_parcel and stored_parcel != normalize_parcel_id(parcel_id):
        return True
    if property_record.county and property_record.county.strip():
        stored_scope_with_supplied_parcel = parcel_identity_key(
            parcel_id,
            county=property_record.county,
            state=property_record.state or state,
        )
        if stored_scope_with_supplied_parcel != parcel_key:
            return True
    return False


def meaningful_street(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned or cleaned.lower().startswith("address pending"):
        return None
    return cleaned


def meaningful_component(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return None if not cleaned or cleaned.lower() == "unknown" else cleaned


def meaningful_postal_code(value: str | None) -> str | None:
    cleaned = meaningful_component(value)
    return normalize_postal_code(cleaned) if cleaned else None
