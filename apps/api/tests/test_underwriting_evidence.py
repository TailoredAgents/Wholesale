from typing import Any

import pytest

from app.integrations.rentcast_client import (
    RentCastClientError,
    RentCastValueEstimate,
)
from app.models.foundation import Property
from app.services.underwriting_evidence import (
    address_candidates,
    resolve_rentcast_subject,
    sanitize_grounded_evidence,
)


def property_record() -> Property:
    return Property(
        street_address="134 Waterstone Trail",
        city="Canton",
        state="GA",
        postal_code="30114",
        property_type="single_family",
        address_validation_status="unverified",
    )


def provider_subject() -> dict[str, Any]:
    return {
        "id": "134-Waterstone-Trl,-Canton,-GA-30114",
        "formattedAddress": "134 Waterstone Trl, Canton, GA 30114",
        "addressLine1": "134 Waterstone Trl",
        "city": "Canton",
        "state": "GA",
        "zipCode": "30114",
        "propertyType": "Single Family",
        "bedrooms": 4,
        "bathrooms": 3,
        "squareFootage": 2400,
        "yearBuilt": 2002,
        "latitude": 34.245,
        "longitude": -84.49,
    }


def test_address_candidates_include_provider_format_and_suffix_variant() -> None:
    candidates = address_candidates(
        property_record(),
        "134 Waterstone Trail, Canton, GA 30114",
    )

    assert "134 Waterstone Trail, Canton, GA, 30114" in candidates
    assert "134 waterstone trl, Canton, GA, 30114" in candidates


def test_address_resolution_recovers_from_exact_avm_failure() -> None:
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def get_value_estimate(
            self,
            *,
            address: str,
            property_type: str | None,
        ) -> RentCastValueEstimate:
            calls.append(("avm", address))
            if len([call for call in calls if call[0] == "avm"]) == 1:
                raise RentCastClientError(
                    "No data found for address.",
                    operation="value estimate",
                    status_code=404,
                    error_code="resource/not-found",
                )
            subject = provider_subject()
            payload = {
                "price": 425000,
                "priceRangeLow": 405000,
                "priceRangeHigh": 445000,
                "subjectProperty": subject,
                "comparables": [],
            }
            return RentCastValueEstimate(
                price=425000,
                price_range_low=405000,
                price_range_high=445000,
                subject_property=subject,
                comparables=[],
                raw_response=payload,
            )

        def get_property_record(self, *, address: str) -> dict[str, Any]:
            calls.append(("record", address))
            return provider_subject()

    result = resolve_rentcast_subject(
        FakeClient(),  # type: ignore[arg-type]
        property_record(),
        requested_address="134 Waterstone Trail, Canton, GA 30114",
    )

    assert result.estimate.price == 425000
    assert result.subject_record["id"] == "134-Waterstone-Trl,-Canton,-GA-30114"
    assert result.resolved_address == "134 Waterstone Trl, Canton, GA 30114"
    assert result.address_evidence["resolution_method"] == "property_record_retry"
    assert result.address_evidence["status"] == "confirmed"
    assert result.avm_error == "No data found for address."


def test_address_resolution_uses_recorded_sales_fallback_when_avm_stays_down() -> None:
    class FakeClient:
        def get_value_estimate(self, **_: object) -> RentCastValueEstimate:
            raise RentCastClientError(
                "AVM unavailable.",
                operation="value estimate",
                status_code=404,
                error_code="resource/not-found",
            )

        def get_property_record(self, **_: object) -> dict[str, Any]:
            return provider_subject()

    result = resolve_rentcast_subject(
        FakeClient(),  # type: ignore[arg-type]
        property_record(),
        requested_address="134 Waterstone Trail, Canton, GA 30114",
    )

    assert result.estimate.price is None
    assert result.subject_record["squareFootage"] == 2400
    assert result.address_evidence["resolution_method"] == "recorded_sales_fallback"
    assert result.avm_error == "AVM unavailable."


def test_address_resolution_rejects_wrong_house_number() -> None:
    wrong_subject = {
        **provider_subject(),
        "formattedAddress": "136 Waterstone Trl, Canton, GA 30114",
        "addressLine1": "136 Waterstone Trl",
    }

    class FakeClient:
        def get_value_estimate(self, **_: object) -> RentCastValueEstimate:
            raise RentCastClientError(
                "Exact address unavailable.",
                operation="value estimate",
                status_code=404,
            )

        def get_property_record(self, **_: object) -> dict[str, Any]:
            return wrong_subject

    with pytest.raises(RentCastClientError, match="Exact address unavailable"):
        resolve_rentcast_subject(
            FakeClient(),  # type: ignore[arg-type]
            property_record(),
            requested_address="134 Waterstone Trail, Canton, GA 30114",
        )


def test_grounded_evidence_keeps_only_consulted_sources() -> None:
    parsed = {
        "status": "completed",
        "summary": "Public records support the subject facts.",
        "address_match": "confirmed",
        "facts": [
            {
                "fact_type": "property_record",
                "value": "2,400 square feet",
                "source_url": "https://assessor.example.gov/property/134#overview",
                "source_title": "County assessor",
            },
            {
                "fact_type": "market_context",
                "value": "Unsupported claim",
                "source_url": "https://unknown.example/value",
                "source_title": "Unknown",
            },
        ],
        "conflicts": [],
        "limitations": [],
    }
    evidence = sanitize_grounded_evidence(
        parsed,
        [
            {
                "url": "https://assessor.example.gov/property/134",
                "title": "County assessor",
            }
        ],
    )

    assert evidence["status"] == "completed"
    assert len(evidence["facts"]) == 1
    assert evidence["facts"][0]["value"] == "2,400 square feet"
    assert len(evidence["sources"]) == 1
