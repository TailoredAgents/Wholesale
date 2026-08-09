from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models.foundation import Property
from app.services.bootstrap import bootstrap_foundation
from app.services.property_identity import (
    find_property_by_identity,
    refresh_property_identity_keys,
)


def seed_organization_id(db_session: Session) -> UUID:
    result = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    assert result.organization is not None
    return result.organization.id


def test_property_lookup_matches_equivalent_apn_and_county_formatting(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    property_record = Property(
        organization_id=organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        county="Fulton County",
        parcel_id="0012-03-A.004",
    )
    refresh_property_identity_keys(property_record)
    db_session.add(property_record)
    db_session.flush()

    match, address_key, parcel_key = find_property_by_identity(
        db_session,
        organization_id=organization_id,
        street_address="",
        city="",
        state="ga",
        postal_code="",
        parcel_id="001203A004",
        county="Fulton",
    )

    assert match is property_record
    assert address_key is None
    assert parcel_key == "GA|fulton|001203A004"


def test_property_lookup_does_not_cross_counties_for_same_apn(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    fulton_property = Property(
        organization_id=organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        county="Fulton",
        parcel_id="001-002",
    )
    refresh_property_identity_keys(fulton_property)
    db_session.add(fulton_property)
    db_session.flush()

    match, _, parcel_key = find_property_by_identity(
        db_session,
        organization_id=organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        parcel_id="001-002",
        county="Cobb",
    )

    assert match is None
    assert parcel_key == "GA|cobb|001002"


def test_property_lookup_rejects_address_and_apn_that_resolve_to_different_records(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    parcel_property = Property(
        organization_id=organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        county="Fulton",
        parcel_id="001-002",
    )
    address_property = Property(
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        parcel_id=None,
    )
    refresh_property_identity_keys(parcel_property)
    refresh_property_identity_keys(address_property)
    db_session.add_all([parcel_property, address_property])
    db_session.flush()

    with pytest.raises(ValueError, match="match different property records"):
        find_property_by_identity(
            db_session,
            organization_id=organization_id,
            street_address="123 Main Street",
            city="Atlanta",
            state="GA",
            postal_code="30303",
            parcel_id="001-002",
            county="Fulton",
        )


def test_parcel_match_rejects_a_different_supplied_complete_address(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    property_record = Property(
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        parcel_id="001-002",
    )
    refresh_property_identity_keys(property_record)
    db_session.add(property_record)
    db_session.flush()

    with pytest.raises(ValueError, match="address and APN conflict"):
        find_property_by_identity(
            db_session,
            organization_id=organization_id,
            street_address="999 Different Street",
            city="Atlanta",
            state="GA",
            postal_code="30303",
            parcel_id="001-002",
            county="Fulton",
        )


def test_address_match_rejects_a_different_supplied_parcel(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    property_record = Property(
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county="Fulton",
        parcel_id="001-002",
    )
    refresh_property_identity_keys(property_record)
    db_session.add(property_record)
    db_session.flush()

    with pytest.raises(ValueError, match="address and APN conflict"):
        find_property_by_identity(
            db_session,
            organization_id=organization_id,
            street_address="123 Main Street",
            city="Atlanta",
            state="GA",
            postal_code="30303",
            parcel_id="DIFFERENT-APN",
            county="Fulton",
        )


def test_dual_identity_safely_enriches_a_parcel_only_property_with_address(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    property_record = Property(
        organization_id=organization_id,
        street_address="",
        city="",
        state="GA",
        postal_code="",
        county="Fulton County",
        parcel_id="001-002",
    )
    refresh_property_identity_keys(property_record)
    db_session.add(property_record)
    db_session.flush()

    match, address_key, parcel_key = find_property_by_identity(
        db_session,
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        parcel_id="001002",
        county="Fulton",
    )

    assert match is property_record
    assert address_key == "123 main st|atlanta|GA|30303"
    assert parcel_key == "GA|fulton|001002"
    assert property_record.street_address == "123 Main Street"
    assert property_record.city == "Atlanta"
    assert property_record.postal_code == "30303"
    assert property_record.normalized_address_key == address_key


def test_dual_identity_safely_enriches_an_address_only_property_with_parcel(
    db_session: Session,
) -> None:
    organization_id = seed_organization_id(db_session)
    property_record = Property(
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        county=None,
        parcel_id=None,
    )
    refresh_property_identity_keys(property_record)
    db_session.add(property_record)
    db_session.flush()

    match, address_key, parcel_key = find_property_by_identity(
        db_session,
        organization_id=organization_id,
        street_address="123 Main Street",
        city="Atlanta",
        state="GA",
        postal_code="30303",
        parcel_id="001-002",
        county="Fulton",
    )

    assert match is property_record
    assert address_key == "123 main st|atlanta|GA|30303"
    assert parcel_key == "GA|fulton|001002"
    assert property_record.parcel_id == "001-002"
    assert property_record.county == "Fulton"
    assert property_record.normalized_parcel_key == parcel_key
