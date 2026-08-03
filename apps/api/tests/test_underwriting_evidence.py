from typing import Any

import pytest

from app.integrations.rentcast_client import (
    RentCastClientError,
    RentCastValueEstimate,
)
from app.models.foundation import Property
from app.services.underwriting_evidence import (
    address_candidates,
    merge_research_comparable_sales,
    research_comparable_sale_records,
    resolve_rentcast_subject,
    sanitize_grounded_evidence,
)
from app.services.underwriting_manual_comps import merge_verified_manual_sales


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


def test_grounded_evidence_promotes_only_complete_cited_closed_sales() -> None:
    parsed = {
        "status": "completed",
        "summary": "Two nearby sales were researched.",
        "address_match": "confirmed",
        "facts": [],
        "conflicts": [],
        "limitations": [],
        "comparable_candidates": [
            {
                "formatted_address": "710 Parkside Dr, Woodstock, GA 30188",
                "address_line1": "710 Parkside Dr",
                "city": "Woodstock",
                "state": "GA",
                "postal_code": "30188",
                "sale_price_dollars": 515000,
                "sale_date": "2026-03-15",
                "closed_sale_confirmed": True,
                "transaction_type": "Warranty Deed",
                "arms_length_status": "verified",
                "arms_length_evidence": (
                    "The cited MLS closed record and county deed identify an ordinary sale."
                ),
                "property_type": "Single Family",
                "bedrooms": 4,
                "bathrooms": 3,
                "square_footage": 2450,
                "year_built": 2001,
                "lot_size": 12000,
                "subdivision": "Parkside",
                "condition_classification": "renovated",
                "condition_evidence": "Updated listing photos and description.",
                "source_urls": [
                    "https://broker.example/710-parkside",
                    "https://records.example/710-parkside",
                ],
                "source_titles": ["Broker sale", "County record"],
                "research_summary": "Public sources report the same closed sale.",
            },
            {
                "formatted_address": "720 Parkside Dr, Woodstock, GA 30188",
                "address_line1": "720 Parkside Dr",
                "city": "Woodstock",
                "state": "GA",
                "postal_code": "30188",
                "sale_price_dollars": 530000,
                "sale_date": None,
                "closed_sale_confirmed": False,
                "transaction_type": None,
                "arms_length_status": "unverified",
                "arms_length_evidence": None,
                "property_type": "Single Family",
                "bedrooms": 4,
                "bathrooms": 3,
                "square_footage": 2500,
                "year_built": 2002,
                "lot_size": None,
                "subdivision": "Parkside",
                "condition_classification": "unknown",
                "condition_evidence": None,
                "source_urls": ["https://broker.example/720-parkside"],
                "source_titles": ["Broker listing"],
                "research_summary": "No closed sale was confirmed.",
            },
        ],
    }
    sources = [
        {"url": "https://broker.example/710-parkside", "title": "Broker sale"},
        {"url": "https://records.example/710-parkside", "title": "County record"},
        {"url": "https://broker.example/720-parkside", "title": "Broker listing"},
    ]

    evidence = sanitize_grounded_evidence(parsed, sources)
    records = research_comparable_sale_records(evidence)

    assert evidence["research_version"] == "ai_comp_discovery_v1"
    assert evidence["valuation_candidate_count"] == 1
    assert evidence["comparable_candidates"][0]["source_grade"] == "corroborated"
    assert records[0]["_stonegateVerificationStatus"] == "public_corroborated"
    assert records[0]["lastSalePrice"] == 515000
    assert records[0]["_stonegateConditionClassification"] == "unknown"


def test_public_foreclosure_is_retained_for_review_but_never_enters_valuation() -> None:
    url = "https://records.example/730-parkside"
    parsed = {
        "status": "completed",
        "summary": "One recorded transfer was researched.",
        "address_match": "confirmed",
        "facts": [],
        "conflicts": [],
        "limitations": [],
        "comparable_candidates": [
            {
                "formatted_address": "730 Parkside Dr, Woodstock, GA 30188",
                "address_line1": "730 Parkside Dr",
                "city": "Woodstock",
                "state": "GA",
                "postal_code": "30188",
                "sale_price_dollars": 315000,
                "sale_date": "2026-02-01",
                "closed_sale_confirmed": True,
                "transaction_type": "Foreclosure deed",
                "arms_length_status": "verified",
                "arms_length_evidence": "The cited deed identifies a foreclosure transfer.",
                "property_type": "Single Family",
                "bedrooms": 4,
                "bathrooms": 3,
                "square_footage": 2400,
                "year_built": 2001,
                "lot_size": 12000,
                "subdivision": "Parkside",
                "condition_classification": "unknown",
                "condition_evidence": None,
                "source_urls": [url],
                "source_titles": ["County deed"],
                "research_summary": "Recorded foreclosure transfer.",
            }
        ],
    }

    evidence = sanitize_grounded_evidence(
        parsed,
        [{"url": url, "title": "County deed"}],
    )

    assert evidence["valuation_candidate_count"] == 0
    assert evidence["comparable_candidates"][0]["valuation_eligible"] is False
    assert "non-market" in evidence["comparable_candidates"][0]["transfer_review_reason"]
    assert research_comparable_sale_records(evidence) == []


def test_provider_sale_wins_when_ai_research_finds_the_same_sale() -> None:
    provider = [
        {
            "formattedAddress": "710 Parkside Dr, Woodstock, GA 30188",
            "lastSaleDate": "2026-03-15",
        }
    ]
    research = [
        {
            "formattedAddress": "710 Parkside Dr, Woodstock, GA 30188",
            "lastSaleDate": "2026-03-15",
            "_stonegateEvidenceSource": "ai_web_research",
        }
    ]

    merged, duplicate_count = merge_research_comparable_sales(provider, research)

    assert merged == provider
    assert duplicate_count == 1


def test_provider_public_and_manual_variants_never_double_weight_same_transfer() -> None:
    provider = [
        {
            "formattedAddress": "123 Main Street, Atlanta, GA 30303",
            "lastSaleDate": "2026-03-15",
            "lastSalePrice": 250_000,
        }
    ]
    research = [
        {
            "formattedAddress": "123 Main St., Atlanta, GA 30303",
            "lastSaleDate": "2026-03-17",
            "lastSalePrice": 250_500,
            "_stonegateEvidenceSource": "ai_web_research",
        }
    ]
    manual = [
        {
            "formattedAddress": "123 Main St, Atlanta, GA 30303",
            "lastSaleDate": "2026-03-14",
            "lastSalePrice": 249_000,
            "_stonegateManualComparableId": "manual-1",
        }
    ]

    after_research, research_duplicates = merge_research_comparable_sales(provider, research)
    merged, manual_duplicates = merge_verified_manual_sales(after_research, manual)

    assert merged == provider
    assert research_duplicates == 1
    assert manual_duplicates == ["manual-1"]
