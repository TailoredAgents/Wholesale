from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.integrations.dealmachine_client import (
    DealMachineComparableSearch,
    DealMachinePropertyLookup,
)
from app.integrations.realestateapi_client import RealEstateAPIPropertyDetail
from app.integrations.rentcast_client import RentCastValueEstimate
from app.services.leads import comp_intelligence_valuation_warnings
from app.services.underwriting_provider_pipeline import (
    ComparableIntelligenceResult,
    build_cached_rentcast_intelligence,
    build_comparable_intelligence,
    reuse_cached_comparable_intelligence,
)
from app.services.underwriting_v2 import UnderwritingV2Result, analyze_underwriting_v2


def _settings(
    mode: str,
    *,
    credit_cap: int = 2,
    api_key: str | None = "dm_test",
) -> Settings:
    return Settings.model_validate(
        {
            "UNDERWRITING_DEALMACHINE_COMPS_MODE": mode,
            "UNDERWRITING_DEALMACHINE_MAX_CREDITS_PER_ANALYSIS": credit_cap,
            "DEALMACHINE_API_KEY": api_key,
        }
    )


def _rentcast_records() -> list[dict[str, Any]]:
    return [
        {
            "id": "rent-1",
            "formattedAddress": "101 Main Street, Dayton, OH 45402",
            "lastSalePrice": 200_000,
            "lastSaleDate": "2026-05-10",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_400,
            "_stonegateSearchLevel": "preferred",
        }
    ]


class FakeDealMachineClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.lookup_calls = 0
        self.comp_calls: list[dict[str, Any]] = []

    def lookup_underwriting_property(self, *, address: str) -> DealMachinePropertyLookup:
        self.lookup_calls += 1
        if self.fail:
            raise RuntimeError("provider timeout")
        return DealMachinePropertyLookup(
            matched=True,
            property={
                "dm_property_id": "prop_subject",
                "full_address": address,
                "owner_name": "must not persist",
                "phone_numbers": ["555-0100"],
            },
            credits={"used": 1, "properties": 1, "people": 0},
            match_warning=None,
            match_failure=None,
            raw_response={},
        )

    def get_underwriting_comparables(
        self,
        *,
        property_id: str,
        radius_miles: float = 1,
        timeframe: str = "6months",
        limit: int = 25,
        sort_by: str = "match",
        sort_direction: str = "desc",
    ) -> DealMachineComparableSearch:
        self.comp_calls.append(
            {
                "property_id": property_id,
                "radius_miles": radius_miles,
                "timeframe": timeframe,
                "limit": limit,
                "sort_by": sort_by,
                "sort_direction": sort_direction,
            }
        )
        comparables = [
            {
                "dm_property_id": "prop_overlap",
                "type": "sale",
                "full_address": "101 Main St, Dayton, OH 45402",
                "sale_price": 200_000,
                "sale_date": "2026-05-10",
                "property_type": "Single Family",
                "sqft": 1_400,
                "bedrooms": 3,
                "bathrooms": 2,
                "year_built": 1980,
                "owner": {"name": "must not persist"},
            },
            {
                "dm_property_id": "prop_unique",
                "type": "sale",
                "full_address": "202 Oak Ave, Dayton, OH 45402",
                "sale_price": 225_000,
                "sale_date": "2026-04-15",
                "property_type": "Single Family",
                "sqft": 1_500,
                "bedrooms": 3,
                "bathrooms": 2,
                "year_built": 1980,
                "contact_email": "must-not-persist@example.test",
            },
        ]
        return DealMachineComparableSearch(
            subject_property_id=property_id,
            found=True,
            subject_property={"dm_property_id": property_id},
            comparables=comparables,
            summary={"count": 2},
            provider_value_estimation={"estimated_value": 215_000},
            total_comps_found=2,
            credits={"used": 1, "properties": 1, "people": 0},
            request={},
            raw_response={},
        )


def _run(
    mode: str,
    client: FakeDealMachineClient,
    *,
    credit_cap: int = 2,
    final_level: str = "preferred",
) -> ComparableIntelligenceResult:
    return build_comparable_intelligence(
        _settings(mode, credit_cap=credit_cap),
        address="500 Subject St, Dayton, OH 45402",
        rentcast_records=_rentcast_records(),
        comp_search_summary={"final_level": final_level},
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
        subject_facts={
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1_400,
            "yearBuilt": 1980,
        },
        client=client,
    )


def test_realestateapi_candidate_merges_and_deduplicates_comps(
    monkeypatch,
) -> None:
    class FakeRealEstateAPIClient:
        def __init__(self, _settings: Settings) -> None:
            pass

        def get_property_detail(
            self, *, address: str, include_comps: bool = True
        ) -> RealEstateAPIPropertyDetail:
            assert include_comps is True
            return RealEstateAPIPropertyDetail(
                found=True,
                property={
                    "id": "subject-1",
                    "estimatedValue": 215_000,
                    "propertyInfo": {
                        "address": {
                            "address": "500 Subject St",
                            "city": "Dayton",
                            "state": "OH",
                            "zip": "45402",
                        }
                    },
                },
                comparables=[
                    {
                        "id": "re-overlap",
                        "address": {
                            "address": "101 Main St",
                            "city": "Dayton",
                            "state": "OH",
                            "zip": "45402",
                        },
                        "lastSaleAmount": 200_000,
                        "lastSaleDate": "2026-05-10",
                        "propertyType": "SFR",
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "squareFeet": 1_400,
                    },
                    {
                        "id": "re-unique",
                        "address": {
                            "address": "202 Oak Ave",
                            "city": "Dayton",
                            "state": "OH",
                            "zip": "45402",
                        },
                        "lastSaleAmount": 225_000,
                        "lastSaleDate": "2026-04-15",
                        "propertyType": "SFR",
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "squareFeet": 1_500,
                    },
                ],
                status_code=200,
                status_message=None,
                raw_response={},
            )

    monkeypatch.setattr(
        "app.services.underwriting_provider_pipeline.RealEstateAPIClient",
        FakeRealEstateAPIClient,
    )
    settings = Settings.model_validate(
        {
            "REALESTATEAPI_API_KEY": "re_test",
            "UNDERWRITING_REALESTATEAPI_COMPS_MODE": "candidate",
            "UNDERWRITING_DEALMACHINE_COMPS_MODE": "disabled",
        }
    )
    result = build_comparable_intelligence(
        settings,
        address="500 Subject St, Dayton, OH 45402",
        rentcast_records=_rentcast_records(),
        comp_search_summary={"final_level": "preferred"},
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
    )

    assert len(result.analysis_records) == 2
    overlap = next(
        record for record in result.analysis_records if "101 Main" in record["formattedAddress"]
    )
    assert set(overlap["source_providers"]) == {"rentcast", "realestateapi"}
    provider = next(
        item for item in result.metadata["providers"] if item["provider"] == "realestateapi"
    )
    assert provider["status"] == "completed"
    assert provider["net_new_count"] == 1
    assert result.metadata["mode"] == "candidate"
    assert result.metadata["external_benchmarks"][-1]["provider"] == "realestateapi"
    assert result.provider_payload["property"]["id"] == "subject-1"


def _underwrite(
    records: list[dict[str, Any]],
    *,
    provider_warnings: list[str],
) -> UnderwritingV2Result:
    subject = {
        "id": "subject",
        "formattedAddress": "500 Subject St, Dayton, OH 45402",
        "propertyType": "Single Family",
        "bedrooms": 3,
        "bathrooms": 2,
        "squareFootage": 1_400,
        "yearBuilt": 1980,
    }
    return analyze_underwriting_v2(
        estimate=RentCastValueEstimate(
            price=210_000,
            price_range_low=200_000,
            price_range_high=220_000,
            subject_property=subject,
            comparables=[],
            raw_response={},
        ),
        subject_record=subject,
        sale_records=records,
        rent_estimate=None,
        local_property_type="Single Family",
        lead_condition="needs_repairs",
        current_condition_override="dated_livable",
        target_condition="standard_flip",
        repair_level_override="moderate",
        base_rehab_override_cents=None,
        repair_items=[],
        contingency_override_percentage=None,
        holding_period_months=6,
        condition_overrides={"rent-1": "renovated"},
        provider_warnings=provider_warnings,
        address_validation_status="verified",
        address_match_score=100,
        secondary_evidence={},
        settings=_settings("disabled"),
    )


def test_disabled_mode_does_not_call_dealmachine() -> None:
    client = FakeDealMachineClient()
    result = _run("disabled", client)

    assert client.lookup_calls == 0
    assert client.comp_calls == []
    assert len(result.analysis_records) == 1
    assert result.metadata["providers"][1]["status"] == "disabled"
    assert result.metadata["external_benchmarks"][0]["valuation_use"] == (
        "excluded_from_arv_and_offer_math"
    )


def test_shadow_mode_compares_sources_without_changing_analysis_records() -> None:
    client = FakeDealMachineClient()
    result = _run("shadow", client)

    assert len(result.analysis_records) == 1
    assert len(result.metadata["shadow_comps"]) == 2
    assert result.metadata["corroborated_sale_count"] == 1
    assert result.metadata["duplicate_count"] == 1
    dealmachine = result.metadata["providers"][1]
    assert dealmachine["credits_used"] == 2
    assert dealmachine["usable_count"] == 2
    assert dealmachine["net_new_count"] == 1
    assert dealmachine["unique_count"] == 1
    assert dealmachine["overlap_count"] == 1
    assert dealmachine["property_credits"] == 2
    assert dealmachine["people_credits"] == 0
    assert dealmachine["property_only_credit_status"] == "verified_zero_people"
    assert result.metadata["external_benchmarks"][1] == {
        "provider": "dealmachine",
        "label": "DealMachine provider estimate",
        "point_cents": 21_500_000,
        "low_cents": None,
        "high_cents": None,
        "status": "available",
        "source_url": None,
        "valuation_use": "excluded_from_arv_and_offer_math",
    }
    assert client.comp_calls[0]["radius_miles"] == 0.5
    assert client.comp_calls[0]["timeframe"] == "6months"


def test_shadow_provider_failure_is_economically_identical_to_disabled_mode() -> None:
    disabled = _run("disabled", FakeDealMachineClient())
    failed_shadow = _run("shadow", FakeDealMachineClient(fail=True))

    assert failed_shadow.metadata["warnings"]
    assert comp_intelligence_valuation_warnings(failed_shadow.metadata) == []
    assert disabled.analysis_records == failed_shadow.analysis_records
    assert _underwrite(
        disabled.analysis_records,
        provider_warnings=comp_intelligence_valuation_warnings(disabled.metadata),
    ) == _underwrite(
        failed_shadow.analysis_records,
        provider_warnings=comp_intelligence_valuation_warnings(failed_shadow.metadata),
    )


def test_candidate_mode_feeds_merged_provenance_into_stonegate_screening() -> None:
    result = _run("candidate", FakeDealMachineClient())

    assert len(result.analysis_records) == 2
    overlap = next(
        record
        for record in result.analysis_records
        if record["formattedAddress"] == "101 Main Street, Dayton, OH 45402"
    )
    assert overlap["source_providers"] == ["rentcast", "dealmachine"]
    assert overlap["corroborated"] is True
    assert result.metadata["shadow_comps"] == []


def test_dealmachine_rows_must_fit_the_active_preferred_profile() -> None:
    class LooseMatchClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            loose = {
                **result.comparables[1],
                "sqft": 1_666,
                "bedrooms": 4,
                "bathrooms": 3,
                "year_built": 2000,
            }
            return replace(result, comparables=[result.comparables[0], loose])

    result = _run("candidate", LooseMatchClient())
    dealmachine = result.metadata["providers"][1]

    assert len(result.analysis_records) == 1
    assert dealmachine["returned_count"] == 2
    assert dealmachine["usable_count"] == 1
    assert dealmachine["dropped_count"] == 1
    assert dealmachine["duplicate_count"] == 0
    assert any("preferred profile" in warning for warning in dealmachine["warnings"])


def test_dealmachine_property_type_must_match_the_subject_profile() -> None:
    class WrongTypeClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            wrong_type = {**result.comparables[1], "property_type": "Condo"}
            return replace(result, comparables=[result.comparables[0], wrong_type])

    result = _run("candidate", WrongTypeClient())
    dealmachine = result.metadata["providers"][1]

    assert len(result.analysis_records) == 1
    assert dealmachine["dropped_count"] == 1
    assert any("property type does not match" in warning for warning in dealmachine["warnings"])


def test_dealmachine_subject_property_id_is_never_admitted_as_a_comp() -> None:
    class SubjectSaleClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            subject_sale = {
                **result.comparables[0],
                "dm_property_id": result.subject_property_id,
                "full_address": "500 Subject St, Dayton, OH 45402",
            }
            return replace(result, comparables=[subject_sale, result.comparables[1]])

    result = _run("candidate", SubjectSaleClient())

    assert all(
        record["formattedAddress"] != "500 Subject St, Dayton, OH 45402"
        for record in result.analysis_records
    )
    assert any(
        "subject property" in warning for warning in result.metadata["providers"][1]["warnings"]
    )


def test_manual_ladder_state_keeps_dealmachine_evidence_extended_and_time_bounded() -> None:
    result = _run("candidate", FakeDealMachineClient(), final_level="manual")
    unique = next(
        record
        for record in result.analysis_records
        if record["formattedAddress"] == "202 Oak Ave, Dayton, OH 45402"
    )

    assert unique["_stonegateSearchLevel"] == "extended"
    assert unique["_stonegateVerificationStatus"] == "recorded"

    class StaleClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            return replace(
                result,
                comparables=[
                    {**record, "sale_date": "2020-01-01"} for record in result.comparables
                ],
            )

    stale = _run("candidate", StaleClient(), final_level="manual")
    dealmachine = stale.metadata["providers"][1]
    assert len(stale.analysis_records) == 1
    assert dealmachine["status"] == "degraded_no_usable_comps"
    assert dealmachine["dropped_count"] == 2


def test_credit_cap_prevents_partial_paid_lookup() -> None:
    client = FakeDealMachineClient()
    result = _run("candidate", client, credit_cap=1)

    assert client.lookup_calls == 0
    assert result.metadata["providers"][1]["status"] == "skipped_credit_cap"
    assert result.metadata["providers"][1]["credits_used"] == 0
    assert len(result.analysis_records) == 1


def test_people_credit_violation_blocks_dealmachine_evidence() -> None:
    class PeopleCreditClient(FakeDealMachineClient):
        def lookup_underwriting_property(self, *, address: str) -> DealMachinePropertyLookup:
            result = super().lookup_underwriting_property(address=address)
            return DealMachinePropertyLookup(
                matched=result.matched,
                property=result.property,
                credits={"used": 1, "properties": 1, "people": 1},
                match_warning=result.match_warning,
                match_failure=result.match_failure,
                raw_response=result.raw_response,
            )

    client = PeopleCreditClient()
    result = _run("candidate", client)
    dealmachine = result.metadata["providers"][1]

    assert client.comp_calls == []
    assert dealmachine["status"] == "credit_boundary_violation"
    assert dealmachine["people_credits"] == 1
    assert dealmachine["property_only_credit_status"] == "violation"
    assert len(result.analysis_records) == 1
    assert result.metadata["warnings"][0].startswith("HIGH:")


def test_missing_lookup_people_credit_telemetry_blocks_dealmachine_evidence() -> None:
    class MissingLookupTelemetryClient(FakeDealMachineClient):
        def lookup_underwriting_property(self, *, address: str) -> DealMachinePropertyLookup:
            result = super().lookup_underwriting_property(address=address)
            return replace(result, credits={"used": 1, "properties": 1})

    client = MissingLookupTelemetryClient()
    result = _run("candidate", client)
    dealmachine = result.metadata["providers"][1]

    assert client.comp_calls == []
    assert dealmachine["status"] == "credit_boundary_unverified"
    assert dealmachine["property_only_credit_status"] == "unverified"
    assert len(result.analysis_records) == 1


def test_documented_comps_credit_shape_needs_no_people_field() -> None:
    class DocumentedCompsCreditsClient(FakeDealMachineClient):
        def get_underwriting_comparables(
            self,
            **kwargs: Any,
        ) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            return replace(
                result,
                credits={"used": 1, "properties": 1, "deduplicated": 0},
            )

    result = _run("candidate", DocumentedCompsCreditsClient())
    dealmachine = result.metadata["providers"][1]

    assert dealmachine["status"] == "completed"
    assert dealmachine["people_credits"] == 0
    assert dealmachine["property_only_credit_status"] == "verified_zero_people"
    assert len(result.analysis_records) == 2


def test_missing_comps_cost_telemetry_is_safe_but_visibly_estimated() -> None:
    class MissingCompsCostClient(FakeDealMachineClient):
        def get_underwriting_comparables(
            self,
            **kwargs: Any,
        ) -> DealMachineComparableSearch:
            return replace(super().get_underwriting_comparables(**kwargs), credits={})

    original = _run("candidate", MissingCompsCostClient())
    dealmachine = original.metadata["providers"][1]

    assert dealmachine["status"] == "completed"
    assert dealmachine["credits_used"] == 2
    assert dealmachine["credits_estimated"] is True
    assert dealmachine["credit_cost_status"] == "estimated"
    assert dealmachine["property_only_credit_status"] == "verified_zero_people"

    reused = reuse_cached_comparable_intelligence(
        configured_mode="candidate",
        rentcast_records=_rentcast_records(),
        normalized_provider_records=original.analysis_records,
        cached_metadata=original.metadata,
        cached_provider_payload=original.provider_payload,
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
    )
    reused_dealmachine = reused.metadata["providers"][1]
    assert reused_dealmachine["credits_used"] == 0
    assert reused_dealmachine["credits_estimated"] is False
    assert reused_dealmachine["credit_cost_status"] == "not_run"
    assert reused_dealmachine["source_credits_estimated"] is True
    assert reused_dealmachine["source_credit_cost_status"] == "estimated"


def test_subject_identity_mismatch_never_reaches_paid_comp_search() -> None:
    class WrongSubjectClient(FakeDealMachineClient):
        def lookup_underwriting_property(
            self,
            *,
            address: str,
        ) -> DealMachinePropertyLookup:
            self.lookup_calls += 1
            return DealMachinePropertyLookup(
                matched=True,
                property={
                    "dm_property_id": "prop_wrong",
                    "full_address": "999 Different St, Dayton, OH 45402",
                },
                credits={"used": 1, "properties": 1, "people": 0},
                match_warning=None,
                match_failure=None,
                raw_response={},
            )

    client = WrongSubjectClient()
    result = _run("candidate", client)

    assert client.lookup_calls == 1
    assert client.comp_calls == []
    assert result.metadata["providers"][1]["status"] == "identity_mismatch"
    assert "different subject address" in result.metadata["warnings"][0]
    assert len(result.analysis_records) == 1


def test_fuzzy_subject_match_warning_never_reaches_paid_comp_search() -> None:
    class FuzzySubjectClient(FakeDealMachineClient):
        def lookup_underwriting_property(
            self,
            *,
            address: str,
        ) -> DealMachinePropertyLookup:
            self.lookup_calls += 1
            return DealMachinePropertyLookup(
                matched=True,
                property={
                    "dm_property_id": "prop_fuzzy",
                    "full_address": address,
                },
                credits={"used": 1, "properties": 1, "people": 0},
                match_warning={"code": "unit_not_confirmed"},
                match_failure=None,
                raw_response={},
            )

    client = FuzzySubjectClient()
    result = _run("shadow", client)

    assert client.comp_calls == []
    assert result.metadata["providers"][1]["status"] == "identity_mismatch"
    assert "fuzzy subject match warning" in result.metadata["warnings"][0]


def test_provider_failure_isolated_and_payload_removes_contact_data() -> None:
    failed_client = FakeDealMachineClient(fail=True)
    failed = _run("candidate", failed_client)
    assert len(failed.analysis_records) == 1
    assert failed.metadata["providers"][1]["status"] == "failed"
    assert failed.metadata["providers"][1]["error"] == "provider timeout"
    assert failed.metadata["providers"][1]["credits_used"] == 1
    assert failed.metadata["providers"][1]["credits_estimated"] is True
    assert failed.metadata["providers"][1]["credit_cost_status"] == "estimated"
    assert failed.metadata["providers"][1]["property_only_credit_status"] == ("unverified")

    completed = _run("shadow", FakeDealMachineClient())
    serialized = str(completed.provider_payload).lower()
    assert "owner" not in serialized
    assert "contact" not in serialized
    assert "phone" not in serialized
    assert "email" not in serialized
    assert "people" not in serialized


def test_failed_comparable_call_reports_worst_case_estimated_credit_cost() -> None:
    class FailedComparableClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **_kwargs: Any) -> DealMachineComparableSearch:
            raise RuntimeError("comparable timeout")

    result = _run("candidate", FailedComparableClient())
    dealmachine = result.metadata["providers"][1]

    assert dealmachine["status"] == "failed"
    assert dealmachine["credits_used"] == 2
    assert dealmachine["property_credits"] == 2
    assert dealmachine["credits_estimated"] is True
    assert dealmachine["credit_cost_status"] == "estimated"
    assert dealmachine["property_only_credit_status"] == "verified_zero_people"


def test_all_unnormalizable_dealmachine_rows_are_visibly_degraded() -> None:
    class ListingsOnlyClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            return replace(
                result,
                comparables=[{**record, "type": "active_listing"} for record in result.comparables],
            )

    result = _run("candidate", ListingsOnlyClient())
    dealmachine = result.metadata["providers"][1]

    assert len(result.analysis_records) == 1
    assert dealmachine["status"] == "degraded_no_usable_comps"
    assert dealmachine["returned_count"] == 2
    assert dealmachine["normalized_count"] == 0
    assert dealmachine["usable_count"] == 0
    assert dealmachine["dropped_count"] == 2
    assert dealmachine["duplicate_count"] == 0
    assert dealmachine["warnings"]


def test_non_market_dealmachine_rows_are_auditable_but_not_reported_usable() -> None:
    class QuitclaimOnlyClient(FakeDealMachineClient):
        def get_underwriting_comparables(self, **kwargs: Any) -> DealMachineComparableSearch:
            result = super().get_underwriting_comparables(**kwargs)
            return replace(
                result,
                comparables=[
                    {**record, "sale_doc_type": "Quit Claim Deed"} for record in result.comparables
                ],
            )

    result = _run("candidate", QuitclaimOnlyClient())
    dealmachine = result.metadata["providers"][1]

    assert dealmachine["status"] == "degraded_no_usable_comps"
    assert dealmachine["retained_count"] == 2
    assert dealmachine["usable_count"] == 0
    assert dealmachine["valuation_eligible_count"] == 0
    assert dealmachine["ineligible_transfer_count"] == 2
    assert dealmachine["net_new_count"] == 0
    assert any("excluded from valuation" in warning for warning in result.metadata["warnings"])


def test_cached_legacy_normalization_never_runs_optional_provider() -> None:
    result = build_cached_rentcast_intelligence(
        rentcast_records=_rentcast_records(),
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
    )

    assert len(result.analysis_records) == 1
    assert result.metadata["providers"][1]["status"] == "not_run_cached_analysis"
    assert result.metadata["providers"][1]["credits_used"] == 0


def test_candidate_cache_is_removed_from_math_after_mode_rollback() -> None:
    candidate = _run("candidate", FakeDealMachineClient())
    reused = reuse_cached_comparable_intelligence(
        configured_mode="disabled",
        rentcast_records=_rentcast_records(),
        normalized_provider_records=candidate.analysis_records,
        cached_metadata=candidate.metadata,
        cached_provider_payload=candidate.provider_payload,
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
    )

    assert len(candidate.analysis_records) == 2
    assert len(reused.analysis_records) == 1
    assert reused.analysis_records[0]["source_providers"] == ["rentcast"]
    assert reused.metadata["mode"] == "disabled"
    assert reused.metadata["configured_mode"] == "disabled"
    assert reused.metadata["cached_mode"] == "candidate"
    assert reused.provider_payload == {}
    assert "reused RentCast-only sales" in reused.metadata["warnings"][0]


def test_candidate_cache_is_reused_only_while_candidate_mode_remains_enabled() -> None:
    candidate = _run("candidate", FakeDealMachineClient())
    reused = reuse_cached_comparable_intelligence(
        configured_mode="candidate",
        rentcast_records=_rentcast_records(),
        normalized_provider_records=candidate.analysis_records,
        cached_metadata=candidate.metadata,
        cached_provider_payload=candidate.provider_payload,
        rentcast_estimated_value_cents=21_000_000,
        rentcast_estimated_value_low_cents=20_000_000,
        rentcast_estimated_value_high_cents=22_000_000,
    )

    assert len(reused.analysis_records) == 2
    assert reused.metadata["mode"] == "candidate"
    dealmachine = reused.metadata["providers"][1]
    assert dealmachine["credits_used"] == 0
    assert dealmachine["source_credits_used"] == 2
    assert dealmachine["latency_ms"] == 0
    assert dealmachine["evidence_reused"] is True
    assert reused.metadata["evidence_reused"] is True
    assert reused.provider_payload
