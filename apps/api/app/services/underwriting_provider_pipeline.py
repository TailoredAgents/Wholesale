from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from functools import partial
from time import perf_counter
from typing import Any, Literal, Protocol, cast

from app.core.config import Settings
from app.integrations.dealmachine_client import (
    DealMachineClient,
    DealMachineComparableSearch,
    DealMachinePropertyLookup,
)
from app.integrations.realestateapi_client import (
    RealEstateAPIClient,
    RealEstateAPIError,
    RealEstateAPIPropertyDetail,
)
from app.services.underwriting_comparable_evidence import (
    ComparableEvidenceSet,
    ComparableProviderBatch,
    ComparableProviderResponse,
    credit_metadata_from_dealmachine,
    merge_comparable_batches,
    normalize_address_key,
    normalize_dealmachine_comparable,
    normalize_realestateapi_comparable,
    normalize_rentcast_comparable,
    provider_batch_from_response,
)

CompProviderMode = Literal["disabled", "shadow", "candidate"]
SearchLevel = Literal["preferred", "expanded", "extended", "manual"]
DealMachineTimeframe = Literal["3months", "6months", "12months", "all"]

COMP_INTELLIGENCE_VERSION = "comp_intelligence_v2"
EXCLUDED_FROM_VALUATION = "excluded_from_arv_and_offer_math"
CORE_CLOSED_SALE_EVIDENCE = "core_closed_sale_evidence"
CANDIDATE_CLOSED_SALE_EVIDENCE = "candidate_closed_sale_evidence_subject_to_stonegate_screening"
SHADOW_CLOSED_SALE_EVIDENCE = "shadow_only_excluded_from_arv_and_offer_math"


class DealMachineComparableProvider(Protocol):
    def lookup_underwriting_property(
        self,
        *,
        address: str,
    ) -> DealMachinePropertyLookup: ...

    def get_underwriting_comparables(
        self,
        *,
        property_id: str,
        radius_miles: float = 1,
        timeframe: DealMachineTimeframe = "6months",
        limit: int = 25,
        sort_by: Literal["distance", "price", "date", "match"] = "match",
        sort_direction: Literal["asc", "desc"] = "desc",
    ) -> DealMachineComparableSearch: ...


@dataclass(frozen=True)
class ComparableIntelligenceResult:
    analysis_records: list[dict[str, Any]]
    metadata: dict[str, Any]
    provider_payload: dict[str, Any]


def build_comparable_intelligence(
    settings: Settings,
    *,
    address: str,
    rentcast_records: Sequence[dict[str, Any]],
    comp_search_summary: Mapping[str, Any] | None,
    rentcast_estimated_value_cents: int | None,
    rentcast_estimated_value_low_cents: int | None,
    rentcast_estimated_value_high_cents: int | None,
    subject_facts: Mapping[str, Any] | None = None,
    client: DealMachineComparableProvider | None = None,
) -> ComparableIntelligenceResult:
    """Build property-only comparable evidence without letting an optional source fail.

    RealEstateAPI is preferred when enabled; DealMachine remains a disabled-by-default legacy
    fallback. Shadow mode records secondary-provider coverage and conflicts but returns
    RentCast-only records. Candidate mode returns the merged, provenance-preserving evidence set.
    Provider AVMs are retained only as explicitly excluded external benchmarks.
    """
    mode: CompProviderMode = settings.underwriting_dealmachine_comps_mode
    search_level = _search_level(comp_search_summary)
    provider_search_level = _provider_search_level(search_level)
    rentcast_batch = provider_batch_from_response(
        provider="rentcast",
        response=ComparableProviderResponse(records=list(rentcast_records)),
        normalizer=normalize_rentcast_comparable,
    )
    rentcast_evidence = merge_comparable_batches([rentcast_batch])
    benchmarks = _rentcast_benchmarks(
        rentcast_estimated_value_cents,
        rentcast_estimated_value_low_cents,
        rentcast_estimated_value_high_cents,
    )

    realestateapi_mode: CompProviderMode = settings.underwriting_realestateapi_comps_mode
    if realestateapi_mode != "disabled":
        return _build_realestateapi_intelligence(
            settings,
            mode=realestateapi_mode,
            address=address,
            search_level=provider_search_level,
            rentcast_batch=rentcast_batch,
            rentcast_evidence=rentcast_evidence,
            benchmarks=benchmarks,
        )

    if mode == "disabled":
        return _result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            dealmachine_batch=None,
            dealmachine_status="disabled",
            dealmachine_error=None,
            dealmachine_latency_ms=None,
            credits_used=None,
            benchmarks=benchmarks,
            provider_payload={},
            warnings=[],
        )


    if not settings.dealmachine_api_key:
        return _result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            dealmachine_batch=None,
            dealmachine_status="unavailable",
            dealmachine_error="DEALMACHINE_API_KEY is not configured.",
            dealmachine_latency_ms=None,
            credits_used=None,
            benchmarks=benchmarks,
            provider_payload={},
            warnings=[
                "DealMachine comp evidence was unavailable; RentCast closed sales remain the "
                "only provider evidence."
            ],
        )

    credit_cap = settings.underwriting_dealmachine_max_credits_per_analysis
    if credit_cap < 2:
        return _result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            dealmachine_batch=None,
            dealmachine_status="skipped_credit_cap",
            dealmachine_error=None,
            dealmachine_latency_ms=None,
            credits_used=0,
            benchmarks=benchmarks,
            provider_payload={},
            warnings=[
                "DealMachine comp lookup was skipped because the per-analysis credit cap "
                "does not cover the two-credit worst case."
            ],
        )

    provider = client or DealMachineClient(settings)
    started = perf_counter()
    credits_used = 0
    credit_payloads: list[Mapping[str, Any]] = []
    provider_payload: dict[str, Any] = {}
    warnings: list[str] = []
    paid_operations_attempted = 0
    try:
        paid_operations_attempted += 1
        lookup = provider.lookup_underwriting_property(address=address)
        credit_payloads.append(lookup.credits)
        lookup_credits = _credits_used(lookup.credits, fallback=1)
        credits_used += lookup_credits
        provider_payload["lookup"] = _safe_lookup_payload(lookup)
        credit_audit = _property_only_credit_audit(credit_payloads)
        credit_warning = _property_only_credit_warning(credit_audit)
        if credit_warning:
            warnings.append(credit_warning)
        if credit_audit["property_only_credit_status"] in {"violation", "unverified"}:
            credit_status = str(credit_audit["property_only_credit_status"])
            return _result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                dealmachine_batch=None,
                dealmachine_status=f"credit_boundary_{credit_status}",
                dealmachine_error=None,
                dealmachine_latency_ms=_elapsed_ms(started),
                credits_used=credits_used,
                benchmarks=benchmarks,
                provider_payload=provider_payload,
                warnings=warnings,
                credit_audit=credit_audit,
            )
        property_id = _property_id(lookup.property)
        identity_error = _lookup_identity_error(lookup, requested_address=address)
        if not lookup.matched or property_id is None or identity_error is not None:
            latency_ms = _elapsed_ms(started)
            warning = identity_error or (
                "DealMachine could not match the subject address for comp research."
            )
            warnings.append(warning)
            return _result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                dealmachine_batch=None,
                dealmachine_status=(
                    "identity_mismatch" if identity_error is not None else "no_match"
                ),
                dealmachine_error=None,
                dealmachine_latency_ms=latency_ms,
                credits_used=credits_used,
                benchmarks=benchmarks,
                provider_payload=provider_payload,
                warnings=warnings,
                credit_audit=credit_audit,
            )
        if credits_used + 1 > credit_cap:
            latency_ms = _elapsed_ms(started)
            warnings.append(
                "DealMachine comp retrieval was skipped after subject lookup reached the "
                "per-analysis credit cap."
            )
            return _result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                dealmachine_batch=None,
                dealmachine_status="skipped_credit_cap",
                dealmachine_error=None,
                dealmachine_latency_ms=latency_ms,
                credits_used=credits_used,
                benchmarks=benchmarks,
                provider_payload=provider_payload,
                warnings=warnings,
                credit_audit=credit_audit,
            )

        radius_miles, timeframe = _dealmachine_profile(provider_search_level)
        paid_operations_attempted += 1
        comparable_search = provider.get_underwriting_comparables(
            property_id=property_id,
            radius_miles=radius_miles,
            timeframe=timeframe,
            limit=25,
            sort_by="match",
            sort_direction="desc",
        )
        credit_payloads.append(comparable_search.credits)
        credits_used += _credits_used(comparable_search.credits, fallback=1)
        provider_payload["comparables"] = _safe_comparable_payload(comparable_search)
        credit_audit = _property_only_credit_audit(credit_payloads)
        credit_warning = _property_only_credit_warning(credit_audit)
        if credit_warning and credit_warning not in warnings:
            warnings.append(credit_warning)
        if credit_audit["property_only_credit_status"] == "violation":
            return _result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                dealmachine_batch=None,
                dealmachine_status="credit_boundary_violation",
                dealmachine_error=None,
                dealmachine_latency_ms=_elapsed_ms(started),
                credits_used=credits_used,
                benchmarks=benchmarks,
                provider_payload=provider_payload,
                warnings=warnings,
                credit_audit=credit_audit,
            )
        credit_metadata = credit_metadata_from_dealmachine(
            comparable_search.credits,
            operation="underwriting_comparable_search",
            estimated=not bool(comparable_search.credits),
        )
        profile_records, profile_warnings = _filter_dealmachine_profile_records(
            comparable_search.comparables,
            subject_facts=subject_facts,
            search_level=provider_search_level,
            subject_property_id=property_id,
        )
        dealmachine_batch = provider_batch_from_response(
            provider="dealmachine",
            response=ComparableProviderResponse(
                records=profile_records,
                credit_metadata=credit_metadata,
            ),
            normalizer=partial(
                normalize_dealmachine_comparable,
                search_level=provider_search_level,
            ),
        )
        if profile_warnings:
            dealmachine_batch = replace(
                dealmachine_batch,
                raw_count=len(comparable_search.comparables),
                dropped_count=dealmachine_batch.dropped_count + len(profile_warnings),
                warnings=(*dealmachine_batch.warnings, *profile_warnings),
            )
        dealmachine_status = (
            "degraded_no_usable_comps"
            if dealmachine_batch.raw_count > 0 and dealmachine_batch.usable_count == 0
            else "completed"
        )
        if dealmachine_batch.dropped_count:
            warnings.append(
                "DealMachine returned "
                f"{dealmachine_batch.dropped_count} row(s) that could not be admitted as "
                "usable closed-sale evidence."
            )
        if dealmachine_batch.ineligible_transfer_count:
            warnings.append(
                "DealMachine returned "
                f"{dealmachine_batch.ineligible_transfer_count} non-market or nominal "
                "transfer row(s); they remain auditable but are excluded from valuation."
            )
        comparison_evidence = merge_comparable_batches([rentcast_batch, dealmachine_batch])
        analysis_evidence = comparison_evidence if mode == "candidate" else rentcast_evidence
        benchmark = _dealmachine_benchmark(comparable_search.provider_value_estimation)
        if benchmark is not None:
            benchmarks.append(benchmark)
        return _result(
            mode=mode,
            analysis_evidence=analysis_evidence,
            comparison_evidence=comparison_evidence,
            rentcast_batch=rentcast_batch,
            dealmachine_batch=dealmachine_batch,
            dealmachine_status=dealmachine_status,
            dealmachine_error=None,
            dealmachine_latency_ms=_elapsed_ms(started),
            credits_used=credits_used,
            benchmarks=benchmarks,
            provider_payload=provider_payload,
            warnings=warnings,
            credit_audit=credit_audit,
        )
    except Exception as exc:  # noqa: BLE001 - optional provider must not abort underwriting.
        message = (str(exc).strip() or exc.__class__.__name__)[:500]
        failed_credit_audit = _failed_credit_audit(
            credit_payloads,
            attempted_call_count=paid_operations_attempted,
        )
        credit_warning = _property_only_credit_warning(failed_credit_audit)
        if credit_warning:
            warnings.append(credit_warning)
        warnings.append(
            "DealMachine comp evidence failed without interrupting the RentCast analysis."
        )
        return _result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            dealmachine_batch=None,
            dealmachine_status="failed",
            dealmachine_error=message,
            dealmachine_latency_ms=_elapsed_ms(started),
            credits_used=max(credits_used, paid_operations_attempted),
            benchmarks=benchmarks,
            provider_payload=provider_payload,
            warnings=warnings,
            credit_audit=failed_credit_audit,
        )


def _build_realestateapi_intelligence(
    settings: Settings,
    *,
    mode: CompProviderMode,
    address: str,
    search_level: SearchLevel,
    rentcast_batch: ComparableProviderBatch,
    rentcast_evidence: ComparableEvidenceSet,
    benchmarks: list[dict[str, Any]],
) -> ComparableIntelligenceResult:
    if not settings.realestateapi_api_key:
        return _realestateapi_result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            provider_batch=None,
            provider_status="unavailable",
            provider_error="REALESTATEAPI_API_KEY is not configured.",
            provider_latency_ms=None,
            credits_used=0,
            benchmarks=benchmarks,
            provider_payload={},
            warnings=[
                "RealEstateAPI comp evidence was unavailable; RentCast closed sales remain "
                "the only provider evidence."
            ],
        )
    started = perf_counter()
    try:
        detail = RealEstateAPIClient(settings).get_property_detail(
            address=address,
            include_comps=True,
        )
        safe_payload = _safe_realestateapi_payload(detail)
        if not detail.found:
            return _realestateapi_result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                provider_batch=None,
                provider_status="no_match",
                provider_error=None,
                provider_latency_ms=_elapsed_ms(started),
                credits_used=1,
                benchmarks=benchmarks,
                provider_payload=safe_payload,
                warnings=["RealEstateAPI found no exact subject-property match."],
            )
        identity_error = _realestateapi_identity_error(detail.property, address)
        if identity_error:
            return _realestateapi_result(
                mode=mode,
                analysis_evidence=rentcast_evidence,
                comparison_evidence=rentcast_evidence,
                rentcast_batch=rentcast_batch,
                provider_batch=None,
                provider_status="identity_mismatch",
                provider_error=None,
                provider_latency_ms=_elapsed_ms(started),
                credits_used=1,
                benchmarks=benchmarks,
                provider_payload=safe_payload,
                warnings=[identity_error],
            )
        requested_key = normalize_address_key(address)
        filtered_comps = [
            record
            for record in detail.comparables
            if normalize_address_key(_realestateapi_record_address(record) or "")
            != requested_key
        ]
        provider_batch = provider_batch_from_response(
            provider="realestateapi",
            response=ComparableProviderResponse(records=filtered_comps),
            normalizer=partial(
                normalize_realestateapi_comparable,
                search_level=search_level,
            ),
        )
        comparison_evidence = merge_comparable_batches([rentcast_batch, provider_batch])
        analysis_evidence = comparison_evidence if mode == "candidate" else rentcast_evidence
        benchmark = _realestateapi_benchmark(detail.property)
        if benchmark is not None:
            benchmarks.append(benchmark)
        warnings: list[str] = []
        if provider_batch.dropped_count:
            warnings.append(
                "RealEstateAPI returned "
                f"{provider_batch.dropped_count} row(s) that were not usable closed sales."
            )
        return _realestateapi_result(
            mode=mode,
            analysis_evidence=analysis_evidence,
            comparison_evidence=comparison_evidence,
            rentcast_batch=rentcast_batch,
            provider_batch=provider_batch,
            provider_status=(
                "degraded_no_usable_comps"
                if provider_batch.raw_count > 0 and provider_batch.usable_count == 0
                else "completed"
            ),
            provider_error=None,
            provider_latency_ms=_elapsed_ms(started),
            credits_used=1,
            benchmarks=benchmarks,
            provider_payload=safe_payload,
            warnings=warnings,
        )
    except RealEstateAPIError as exc:
        return _realestateapi_result(
            mode=mode,
            analysis_evidence=rentcast_evidence,
            comparison_evidence=rentcast_evidence,
            rentcast_batch=rentcast_batch,
            provider_batch=None,
            provider_status="failed",
            provider_error=str(exc)[:500],
            provider_latency_ms=_elapsed_ms(started),
            credits_used=1,
            benchmarks=benchmarks,
            provider_payload={},
            warnings=[
                "RealEstateAPI evidence failed without interrupting the RentCast analysis."
            ],
        )


def build_cached_rentcast_intelligence(
    *,
    rentcast_records: Sequence[dict[str, Any]],
    rentcast_estimated_value_cents: int | None,
    rentcast_estimated_value_low_cents: int | None,
    rentcast_estimated_value_high_cents: int | None,
    warning: str | None = None,
) -> ComparableIntelligenceResult:
    """Normalize a legacy cached analysis without making a new paid provider request."""
    batch = provider_batch_from_response(
        provider="rentcast",
        response=ComparableProviderResponse(records=list(rentcast_records)),
        normalizer=normalize_rentcast_comparable,
    )
    evidence = merge_comparable_batches([batch])
    return _result(
        mode="disabled",
        analysis_evidence=evidence,
        comparison_evidence=evidence,
        rentcast_batch=batch,
        dealmachine_batch=None,
        dealmachine_status="not_run_cached_analysis",
        dealmachine_error=None,
        dealmachine_latency_ms=None,
        credits_used=0,
        benchmarks=_rentcast_benchmarks(
            rentcast_estimated_value_cents,
            rentcast_estimated_value_low_cents,
            rentcast_estimated_value_high_cents,
        ),
        provider_payload={},
        warnings=[
            warning
            or (
                "This cached analysis predates multi-source comp evidence; refresh market data "
                "to run the configured secondary-provider mode."
            )
        ],
    )


def reuse_cached_comparable_intelligence(
    *,
    configured_mode: CompProviderMode,
    rentcast_records: Sequence[dict[str, Any]],
    normalized_provider_records: Sequence[dict[str, Any]] | None,
    cached_metadata: Mapping[str, Any] | None,
    cached_provider_payload: Mapping[str, Any] | None,
    rentcast_estimated_value_cents: int | None,
    rentcast_estimated_value_low_cents: int | None,
    rentcast_estimated_value_high_cents: int | None,
) -> ComparableIntelligenceResult:
    """Reuse paid evidence only while its saved admission mode is still authorized."""
    cached_mode_value = cached_metadata.get("mode") if cached_metadata is not None else None
    cached_mode = (
        cast(CompProviderMode, cached_mode_value)
        if cached_mode_value in {"disabled", "shadow", "candidate"}
        else None
    )
    normalized = (
        [dict(record) for record in normalized_provider_records]
        if normalized_provider_records is not None
        else None
    )
    if cached_mode == configured_mode and cached_metadata is not None and normalized is not None:
        metadata = dict(cached_metadata)
        providers: list[dict[str, Any]] = []
        for raw_provider in cached_metadata.get("providers", []):
            if not isinstance(raw_provider, Mapping):
                continue
            provider = dict(raw_provider)
            if provider.get("provider") in {"dealmachine", "realestateapi"}:
                provider["source_credits_used"] = provider.get(
                    "source_credits_used", provider.get("credits_used")
                )
                provider["source_latency_ms"] = provider.get(
                    "source_latency_ms", provider.get("latency_ms")
                )
                provider["source_credits_estimated"] = provider.get(
                    "source_credits_estimated", provider.get("credits_estimated")
                )
                provider["source_credit_cost_status"] = provider.get(
                    "source_credit_cost_status", provider.get("credit_cost_status")
                )
                provider["source_property_credits"] = provider.get(
                    "source_property_credits", provider.get("property_credits")
                )
                provider["source_people_credits"] = provider.get(
                    "source_people_credits", provider.get("people_credits")
                )
                provider["credits_used"] = 0
                provider["latency_ms"] = 0
                provider["credits_estimated"] = False
                provider["credit_cost_status"] = "not_run"
                provider["property_credits"] = 0
                provider["people_credits"] = 0
                provider["property_only_credit_status"] = "not_run"
                provider["evidence_reused"] = True
            providers.append(provider)
        metadata["providers"] = providers
        metadata["evidence_reused"] = True
        return ComparableIntelligenceResult(
            analysis_records=normalized,
            metadata=metadata,
            provider_payload=(
                dict(cached_provider_payload) if cached_provider_payload is not None else {}
            ),
        )

    prior_mode = cached_mode or "legacy"
    warning = (
        f"The configured DealMachine comp mode is {configured_mode}, but the cached evidence "
        f"was produced in {prior_mode} mode. Stonegate reused RentCast-only sales and made no "
        "paid provider call; refresh market data to run the configured mode."
    )
    fallback = build_cached_rentcast_intelligence(
        rentcast_records=rentcast_records,
        rentcast_estimated_value_cents=rentcast_estimated_value_cents,
        rentcast_estimated_value_low_cents=rentcast_estimated_value_low_cents,
        rentcast_estimated_value_high_cents=rentcast_estimated_value_high_cents,
        warning=warning,
    )
    return ComparableIntelligenceResult(
        analysis_records=fallback.analysis_records,
        metadata={
            **fallback.metadata,
            "configured_mode": configured_mode,
            "cached_mode": cached_mode,
        },
        provider_payload={},
    )


def _realestateapi_result(
    *,
    mode: CompProviderMode,
    analysis_evidence: ComparableEvidenceSet,
    comparison_evidence: ComparableEvidenceSet,
    rentcast_batch: ComparableProviderBatch,
    provider_batch: ComparableProviderBatch | None,
    provider_status: str,
    provider_error: str | None,
    provider_latency_ms: int | None,
    credits_used: int | None,
    benchmarks: list[dict[str, Any]],
    provider_payload: dict[str, Any],
    warnings: list[str],
) -> ComparableIntelligenceResult:
    comparison_records = comparison_evidence.to_underwriting_records()
    provider_records = [
        record
        for record in comparison_records
        if "realestateapi" in _string_list(record.get("_stonegateSourceProviders"))
    ]
    eligible_records = [
        record
        for record in provider_records
        if record.get("_stonegateTransactionEligibility") != "ineligible"
    ]
    net_new_count = sum(
        "rentcast" not in _string_list(record.get("_stonegateSourceProviders"))
        for record in eligible_records
    )
    overlap_count = len(eligible_records) - net_new_count
    internal_duplicates = provider_batch.duplicate_count if provider_batch else 0
    cross_provider_duplicates = comparison_evidence.duplicate_observation_count
    provider_use = (
        CANDIDATE_CLOSED_SALE_EVIDENCE if mode == "candidate" else SHADOW_CLOSED_SALE_EVIDENCE
    )
    metadata = {
        "version": COMP_INTELLIGENCE_VERSION,
        "mode": mode,
        "provider_strategy": "rentcast_plus_realestateapi_stonegate_math",
        "valuation_use": CORE_CLOSED_SALE_EVIDENCE,
        "providers": [
            {
                "provider": "rentcast",
                "status": rentcast_batch.status,
                "valuation_use": CORE_CLOSED_SALE_EVIDENCE,
                "returned_count": rentcast_batch.raw_count,
                "normalized_count": rentcast_batch.normalized_count,
                "retained_count": rentcast_batch.retained_count,
                "unique_count": rentcast_batch.usable_count,
                "usable_count": rentcast_batch.usable_count,
                "dropped_count": rentcast_batch.dropped_count,
                "valuation_eligible_count": rentcast_batch.valuation_eligible_count,
                "ineligible_transfer_count": rentcast_batch.ineligible_transfer_count,
                "net_new_count": rentcast_batch.usable_count,
                "overlap_count": cross_provider_duplicates,
                "duplicate_count": rentcast_batch.duplicate_count,
                "conflict_count": 0,
                "credits_used": None,
                "latency_ms": None,
                "error": rentcast_batch.error,
                "warnings": list(rentcast_batch.warnings),
            },
            {
                "provider": "realestateapi",
                "status": provider_status,
                "valuation_use": provider_use,
                "returned_count": provider_batch.raw_count if provider_batch else 0,
                "normalized_count": provider_batch.normalized_count if provider_batch else 0,
                "retained_count": provider_batch.retained_count if provider_batch else 0,
                "unique_count": net_new_count,
                "usable_count": provider_batch.usable_count if provider_batch else 0,
                "dropped_count": provider_batch.dropped_count if provider_batch else 0,
                "valuation_eligible_count": (
                    provider_batch.valuation_eligible_count if provider_batch else 0
                ),
                "ineligible_transfer_count": (
                    provider_batch.ineligible_transfer_count if provider_batch else 0
                ),
                "net_new_count": net_new_count,
                "overlap_count": overlap_count,
                "duplicate_count": internal_duplicates,
                "conflict_count": comparison_evidence.field_conflict_count,
                "credits_used": credits_used,
                "credits_estimated": credits_used is not None,
                "credit_cost_status": "estimated" if credits_used is not None else "not_run",
                "latency_ms": provider_latency_ms,
                "error": provider_error,
                "warnings": list(provider_batch.warnings) if provider_batch else [],
            },
        ],
        "corroborated_sale_count": sum(
            record.get("_stonegateCorroborated") is True for record in comparison_records
        ),
        "cross_sourced_sale_count": sum(
            len(_string_list(record.get("_stonegateSourceProviders"))) > 1
            for record in comparison_records
        ),
        "duplicate_count": (
            rentcast_batch.duplicate_count
            + internal_duplicates
            + cross_provider_duplicates
        ),
        "conflict_count": comparison_evidence.field_conflict_count,
        "source_conflicts": _source_conflicts(comparison_records),
        "external_benchmarks": benchmarks,
        "shadow_comps": provider_records if mode == "shadow" else [],
        "warnings": warnings,
    }
    return ComparableIntelligenceResult(
        analysis_records=analysis_evidence.to_underwriting_records(),
        metadata=metadata,
        provider_payload=provider_payload,
    )


def _realestateapi_benchmark(property_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    point = _dollars_to_cents(property_payload.get("estimatedValue"))
    if point is None:
        return None
    return {
        "provider": "realestateapi",
        "label": "RealEstateAPI estimated value",
        "point_cents": point,
        "low_cents": None,
        "high_cents": None,
        "status": "available",
        "source_url": None,
        "valuation_use": EXCLUDED_FROM_VALUATION,
    }


def _safe_realestateapi_payload(detail: RealEstateAPIPropertyDetail) -> dict[str, Any]:
    return {
        "found": detail.found,
        "status_code": detail.status_code,
        "status_message": detail.status_message,
        "property": _remove_direct_contact_data(detail.property),
        "comparables": _remove_direct_contact_data(detail.comparables),
    }


def _remove_direct_contact_data(value: Any) -> Any:
    forbidden = ("phone", "email")
    if isinstance(value, Mapping):
        return {
            str(key): _remove_direct_contact_data(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in forbidden)
        }
    if isinstance(value, list):
        return [_remove_direct_contact_data(item) for item in value]
    return value


def _realestateapi_identity_error(
    property_payload: Mapping[str, Any],
    requested_address: str,
) -> str | None:
    returned = _realestateapi_property_address(property_payload)
    if returned and normalize_address_key(returned) != normalize_address_key(requested_address):
        return (
            "RealEstateAPI returned a different subject address; its property facts and comps "
            "were excluded."
        )
    return None


def _realestateapi_property_address(property_payload: Mapping[str, Any]) -> str | None:
    info = property_payload.get("propertyInfo")
    info_values = info if isinstance(info, Mapping) else {}
    address = info_values.get("address")
    if not isinstance(address, Mapping):
        address = property_payload.get("address")
    return _realestateapi_record_address(
        {"address": address} if isinstance(address, Mapping) else {}
    )


def _realestateapi_record_address(record: Mapping[str, Any]) -> str | None:
    direct = _first(record, "formattedAddress", "fullAddress")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    address = record.get("address")
    values = address if isinstance(address, Mapping) else {}
    direct = _first(values, "formattedAddress", "fullAddress")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    street = _first(values, "address", "addressLine1", "streetAddress")
    if not isinstance(street, str) or not street.strip():
        house = _first(values, "house")
        street_name = _first(values, "street")
        street = " ".join(
            str(value).strip() for value in (house, street_name) if value is not None
        )
    if not isinstance(street, str) or not street.strip():
        return None
    city = _first(values, "city")
    state = _first(values, "state")
    postal_code = _first(values, "zip", "zipCode", "postalCode")
    locality = ", ".join(str(value).strip() for value in (city, state) if value)
    return ", ".join(value for value in (street.strip(), locality) if value) + (
        f" {str(postal_code).strip()}" if postal_code else ""
    )


def _result(
    *,
    mode: CompProviderMode,
    analysis_evidence: ComparableEvidenceSet,
    comparison_evidence: ComparableEvidenceSet,
    rentcast_batch: ComparableProviderBatch,
    dealmachine_batch: ComparableProviderBatch | None,
    dealmachine_status: str,
    dealmachine_error: str | None,
    dealmachine_latency_ms: int | None,
    credits_used: int | None,
    benchmarks: list[dict[str, Any]],
    provider_payload: dict[str, Any],
    warnings: list[str],
    credit_audit: Mapping[str, Any] | None = None,
) -> ComparableIntelligenceResult:
    comparison_records = comparison_evidence.to_underwriting_records()
    dealmachine_records = [
        record
        for record in comparison_records
        if "dealmachine" in _string_list(record.get("_stonegateSourceProviders"))
    ]
    dealmachine_eligible_records = [
        record
        for record in dealmachine_records
        if record.get("_stonegateTransactionEligibility") != "ineligible"
    ]
    dealmachine_net_new_count = sum(
        "rentcast" not in _string_list(record.get("_stonegateSourceProviders"))
        for record in dealmachine_eligible_records
    )
    dealmachine_overlap_count = len(dealmachine_eligible_records) - dealmachine_net_new_count
    source_conflicts = _source_conflicts(comparison_records)
    provider_use = (
        CANDIDATE_CLOSED_SALE_EVIDENCE if mode == "candidate" else SHADOW_CLOSED_SALE_EVIDENCE
    )
    dm_usable = dealmachine_batch.usable_count if dealmachine_batch is not None else 0
    rentcast_internal_duplicates = rentcast_batch.duplicate_count
    dealmachine_internal_duplicates = (
        dealmachine_batch.duplicate_count if dealmachine_batch is not None else 0
    )
    cross_provider_duplicates = comparison_evidence.duplicate_observation_count
    total_duplicate_count = (
        rentcast_internal_duplicates + dealmachine_internal_duplicates + cross_provider_duplicates
    )
    metadata = {
        "version": COMP_INTELLIGENCE_VERSION,
        "mode": mode,
        "valuation_use": CORE_CLOSED_SALE_EVIDENCE,
        "providers": [
            {
                "provider": "rentcast",
                "status": rentcast_batch.status,
                "valuation_use": CORE_CLOSED_SALE_EVIDENCE,
                "returned_count": rentcast_batch.raw_count,
                "normalized_count": rentcast_batch.normalized_count,
                "retained_count": rentcast_batch.retained_count,
                "unique_count": rentcast_batch.usable_count,
                "usable_count": rentcast_batch.usable_count,
                "dropped_count": rentcast_batch.dropped_count,
                "valuation_eligible_count": rentcast_batch.valuation_eligible_count,
                "ineligible_transfer_count": rentcast_batch.ineligible_transfer_count,
                "net_new_count": rentcast_batch.usable_count,
                "overlap_count": cross_provider_duplicates,
                "duplicate_count": rentcast_internal_duplicates,
                "conflict_count": 0,
                "credits_used": None,
                "latency_ms": None,
                "error": rentcast_batch.error,
                "warnings": list(rentcast_batch.warnings),
            },
            {
                "provider": "dealmachine",
                "status": dealmachine_status,
                "valuation_use": provider_use,
                "returned_count": (
                    dealmachine_batch.raw_count if dealmachine_batch is not None else 0
                ),
                "normalized_count": (
                    dealmachine_batch.normalized_count if dealmachine_batch is not None else 0
                ),
                "retained_count": (
                    dealmachine_batch.retained_count if dealmachine_batch is not None else 0
                ),
                "unique_count": dealmachine_net_new_count,
                "usable_count": dm_usable,
                "dropped_count": (
                    dealmachine_batch.dropped_count if dealmachine_batch is not None else 0
                ),
                "valuation_eligible_count": (
                    dealmachine_batch.valuation_eligible_count
                    if dealmachine_batch is not None
                    else 0
                ),
                "ineligible_transfer_count": (
                    dealmachine_batch.ineligible_transfer_count
                    if dealmachine_batch is not None
                    else 0
                ),
                "net_new_count": dealmachine_net_new_count,
                "overlap_count": dealmachine_overlap_count,
                "duplicate_count": dealmachine_internal_duplicates,
                "conflict_count": comparison_evidence.field_conflict_count,
                "credits_used": credits_used,
                "property_credits": (
                    credit_audit.get("property_credits") if credit_audit is not None else None
                ),
                "people_credits": (
                    credit_audit.get("people_credits") if credit_audit is not None else None
                ),
                "property_only_credit_status": (
                    credit_audit.get("property_only_credit_status")
                    if credit_audit is not None
                    else "not_run"
                ),
                "credits_estimated": (
                    credit_audit.get("credits_estimated") if credit_audit is not None else None
                ),
                "credit_cost_status": (
                    credit_audit.get("credit_cost_status")
                    if credit_audit is not None
                    else "not_run"
                ),
                "latency_ms": dealmachine_latency_ms,
                "error": dealmachine_error,
                "warnings": (
                    list(dealmachine_batch.warnings) if dealmachine_batch is not None else []
                ),
            },
        ],
        "corroborated_sale_count": sum(
            record.get("_stonegateCorroborated") is True for record in comparison_records
        ),
        "cross_sourced_sale_count": sum(
            len(_string_list(record.get("_stonegateSourceProviders"))) > 1
            for record in comparison_records
        ),
        "duplicate_count": total_duplicate_count,
        "conflict_count": comparison_evidence.field_conflict_count,
        "source_conflicts": source_conflicts,
        "external_benchmarks": benchmarks,
        "shadow_comps": dealmachine_records if mode == "shadow" else [],
        "warnings": warnings,
    }
    return ComparableIntelligenceResult(
        analysis_records=analysis_evidence.to_underwriting_records(),
        metadata=metadata,
        provider_payload=provider_payload,
    )


def _source_conflicts(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for record in records:
        raw_conflicts = record.get("_stonegateFieldConflicts")
        if not isinstance(raw_conflicts, list):
            continue
        for conflict in raw_conflicts:
            if not isinstance(conflict, dict):
                continue
            conflicts.append(
                {
                    "canonical_evidence_id": record.get("_stonegateCanonicalEvidenceId"),
                    "formatted_address": record.get("formattedAddress"),
                    **conflict,
                }
            )
    return conflicts[:100]


def _rentcast_benchmarks(
    point_cents: int | None,
    low_cents: int | None,
    high_cents: int | None,
) -> list[dict[str, Any]]:
    if point_cents is None and low_cents is None and high_cents is None:
        return []
    return [
        {
            "provider": "rentcast",
            "label": "RentCast AVM",
            "point_cents": point_cents,
            "low_cents": low_cents,
            "high_cents": high_cents,
            "status": "available",
            "source_url": None,
            "valuation_use": EXCLUDED_FROM_VALUATION,
        }
    ]


def _dealmachine_benchmark(values: Mapping[str, Any]) -> dict[str, Any] | None:
    point = _dollars_to_cents(
        _first(values, "estimated_value", "estimate", "value", "median_value")
    )
    low = _dollars_to_cents(
        _first(
            values,
            "estimated_value_low",
            "low_estimate",
            "estimated_low",
            "low_value",
        )
    )
    high = _dollars_to_cents(
        _first(
            values,
            "estimated_value_high",
            "high_estimate",
            "estimated_high",
            "high_value",
        )
    )
    if point is None and low is None and high is None:
        return None
    return {
        "provider": "dealmachine",
        "label": "DealMachine provider estimate",
        "point_cents": point,
        "low_cents": low,
        "high_cents": high,
        "status": "available",
        "source_url": None,
        "valuation_use": EXCLUDED_FROM_VALUATION,
    }


def _safe_lookup_payload(lookup: DealMachinePropertyLookup) -> dict[str, Any]:
    return {
        "matched": lookup.matched,
        "property": _remove_contact_data(lookup.property),
        "credits": _remove_contact_data(lookup.credits),
        "match_warning": _remove_contact_data(lookup.match_warning),
        "match_failure": _remove_contact_data(lookup.match_failure),
    }


def _safe_comparable_payload(search: DealMachineComparableSearch) -> dict[str, Any]:
    return {
        "subject_property_id": search.subject_property_id,
        "found": search.found,
        "subject_property": _remove_contact_data(search.subject_property),
        "comparables": _remove_contact_data(search.comparables),
        "summary": _remove_contact_data(search.summary),
        "provider_value_estimation": _remove_contact_data(search.provider_value_estimation),
        "total_comps_found": search.total_comps_found,
        "credits": _remove_contact_data(search.credits),
        "request": _remove_contact_data(search.request),
    }


def _remove_contact_data(value: Any) -> Any:
    forbidden = ("owner", "contact", "phone", "email", "mailing", "people", "person")
    if isinstance(value, Mapping):
        return {
            str(key): _remove_contact_data(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in forbidden)
        }
    if isinstance(value, list):
        return [_remove_contact_data(item) for item in value]
    return value


def _search_level(summary: Mapping[str, Any] | None) -> SearchLevel:
    value = summary.get("final_level") if summary is not None else None
    return cast(
        SearchLevel,
        value if value in {"preferred", "expanded", "extended", "manual"} else "expanded",
    )


def _dealmachine_profile(
    search_level: SearchLevel,
) -> tuple[float, DealMachineTimeframe]:
    if search_level == "preferred":
        return 0.5, "6months"
    if search_level == "expanded":
        return 1, "12months"
    return 3, "all"


def _provider_search_level(search_level: SearchLevel) -> SearchLevel:
    """A paid provider result is never human-verified manual evidence."""
    return "extended" if search_level == "manual" else search_level


def _filter_dealmachine_profile_records(
    records: Sequence[dict[str, Any]],
    *,
    subject_facts: Mapping[str, Any] | None,
    search_level: SearchLevel,
    subject_property_id: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    limits = {
        "preferred": {
            "days": 180,
            "radius": 0.5,
            "bedrooms": 0.0,
            "bathrooms": 0.5,
            "gla": 0.15,
            "year": 15,
        },
        "expanded": {
            "days": 365,
            "radius": 1.0,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "gla": 0.20,
            "year": 25,
        },
        "extended": {
            "days": 730,
            "radius": 3.0,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "gla": 0.25,
            "year": 35,
        },
        "manual": {
            "days": 730,
            "radius": 3.0,
            "bedrooms": 1.0,
            "bathrooms": 1.0,
            "gla": 0.25,
            "year": 35,
        },
    }[search_level]
    subject = subject_facts or {}
    admitted: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, record in enumerate(records):
        record_id = _first(record, "dm_property_id", "property_id", "id")
        if subject_property_id and str(record_id or "").strip() == subject_property_id:
            warnings.append(f"Record {index + 1} was excluded because it is the subject property.")
            continue
        observation = normalize_dealmachine_comparable(
            record,
            search_level=search_level,
        )
        if observation is None:
            admitted.append(record)
            continue
        reason = _profile_rejection_reason(
            observation.values,
            subject=subject,
            limits=limits,
        )
        if reason is None:
            admitted.append(record)
        else:
            warnings.append(
                f"Record {index + 1} was excluded by the {search_level} profile: {reason}"
            )
    return admitted, warnings


def _profile_rejection_reason(
    values: Mapping[str, Any],
    *,
    subject: Mapping[str, Any],
    limits: Mapping[str, float | int],
) -> str | None:
    sale_date = _date_value(values.get("sale_date"))
    if sale_date is None:
        return "closed-sale date is missing or invalid."
    age_days = (datetime.now(UTC).date() - sale_date).days
    if age_days < 0:
        return "closed-sale date is in the future."
    if age_days > int(limits["days"]):
        return f"sale is older than {int(limits['days'])} days."
    distance = _number_value(values.get("distance_miles"))
    if distance is not None and distance > float(limits["radius"]):
        return f"distance exceeds {float(limits['radius']):g} miles."

    subject_type = _property_type_key(subject.get("propertyType"))
    comp_type = _property_type_key(values.get("property_type"))
    if subject_type:
        if not comp_type:
            return "property type is missing."
        if subject_type != comp_type:
            return "property type does not match the subject."

    dimension_checks = (
        ("bedrooms", "bedrooms", float(limits["bedrooms"]), False),
        ("bathrooms", "bathrooms", float(limits["bathrooms"]), False),
        ("square_footage", "squareFootage", float(limits["gla"]), True),
        ("year_built", "yearBuilt", float(limits["year"]), False),
    )
    for comp_key, subject_key, tolerance, relative in dimension_checks:
        subject_value = _number_value(subject.get(subject_key))
        if subject_value is None:
            continue
        comp_value = _number_value(values.get(comp_key))
        if comp_value is None:
            return f"{comp_key.replace('_', ' ')} is missing."
        difference = abs(comp_value - subject_value)
        if relative:
            if subject_value <= 0 or difference / subject_value > tolerance:
                return f"living area differs by more than {round(tolerance * 100)}%."
        elif difference > tolerance:
            return f"{comp_key.replace('_', ' ')} exceeds the allowed tolerance."
    return None


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _number_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _property_type_key(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = next((item for item in value if isinstance(item, str) and item.strip()), "")
    if not isinstance(value, str):
        return ""
    key = "".join(character for character in value.casefold() if character.isalnum())
    aliases = {
        "singlefamilyresidential": "singlefamily",
        "singlefamilyhome": "singlefamily",
        "detachedsinglefamily": "singlefamily",
        "multifamilyresidential": "multifamily",
    }
    return aliases.get(key, key)


def _property_id(property_record: Mapping[str, Any] | None) -> str | None:
    if property_record is None:
        return None
    value = _first(property_record, "dm_property_id", "property_id", "id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _lookup_identity_error(
    lookup: DealMachinePropertyLookup,
    *,
    requested_address: str,
) -> str | None:
    if not lookup.matched:
        return None
    if lookup.match_warning:
        return (
            "DealMachine returned a fuzzy subject match warning, so its comparable search was "
            "not trusted."
        )
    returned_address = _provider_address(lookup.property)
    requested_key = normalize_address_key(requested_address)
    returned_key = normalize_address_key(returned_address)
    if not returned_key:
        return (
            "DealMachine did not return a verifiable subject address, so its comparable search "
            "was not trusted."
        )
    if not requested_key or requested_key != returned_key:
        return (
            "DealMachine returned a different subject address, so its comparable search was "
            "not trusted."
        )
    return None


def _provider_address(property_record: Mapping[str, Any] | None) -> str | None:
    if property_record is None:
        return None
    for key in ("full_address", "formatted_address", "property_address"):
        value = property_record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raw_address = property_record.get("address")
    if isinstance(raw_address, str) and raw_address.strip():
        return raw_address.strip()
    if isinstance(raw_address, Mapping):
        nested = _provider_address(raw_address)
        if nested:
            return nested
    line_1 = _first(property_record, "address_line_1", "display_line_1", "street")
    city = _first(property_record, "city", "address_city")
    state = _first(property_record, "state", "address_state")
    postal_code = _first(property_record, "zip", "postal_code", "address_zip")
    parts = [
        value.strip()
        for value in (line_1, city, state, postal_code)
        if isinstance(value, str) and value.strip()
    ]
    return ", ".join(parts) if parts else None


def _credits_used(credits: Mapping[str, Any], *, fallback: int) -> int:
    for key in ("used", "this_page"):
        value = credits.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return fallback


def _property_only_credit_audit(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    property_values = [_credit_count(payload.get("properties")) for payload in payloads]
    people_values = [_credit_count(payload.get("people")) for payload in payloads]
    lookup_people = people_values[0] if people_values else None
    if any(value is not None and value > 0 for value in people_values):
        status = "violation"
    elif lookup_people == 0:
        status = "verified_zero_people"
    elif payloads:
        status = "unverified"
    else:
        status = "not_run"
    credits_estimated = bool(payloads) and any(
        _reported_credit_used(payload) is None for payload in payloads
    )
    return {
        "property_credits": (
            sum(value for value in property_values if value is not None)
            if any(value is not None for value in property_values)
            else None
        ),
        "people_credits": (
            sum(value for value in people_values if value is not None)
            if any(value is not None for value in people_values)
            else None
        ),
        "property_only_credit_status": status,
        "credits_estimated": credits_estimated,
        "credit_cost_status": (
            "estimated" if credits_estimated else "measured" if payloads else "not_run"
        ),
        "reported_credit_call_count": len(payloads),
    }


def _failed_credit_audit(
    payloads: Sequence[Mapping[str, Any]],
    *,
    attempted_call_count: int,
) -> dict[str, Any]:
    audit = _property_only_credit_audit(payloads)
    unreported_attempts = max(0, attempted_call_count - len(payloads))
    if not unreported_attempts:
        return audit
    reported_properties = audit.get("property_credits")
    property_credits = (
        reported_properties
        if isinstance(reported_properties, int) and not isinstance(reported_properties, bool)
        else 0
    )
    return {
        **audit,
        "property_credits": property_credits + unreported_attempts,
        "property_only_credit_status": (
            "unverified" if not payloads else audit["property_only_credit_status"]
        ),
        "credits_estimated": True,
        "credit_cost_status": "estimated",
        "attempted_credit_call_count": attempted_call_count,
        "unreported_attempted_call_count": unreported_attempts,
    }


def _reported_credit_used(payload: Mapping[str, Any]) -> int | None:
    for key in ("used", "this_page"):
        value = _credit_count(payload.get(key))
        if value is not None:
            return value
    return None


def _property_only_credit_warning(credit_audit: Mapping[str, Any]) -> str | None:
    status = credit_audit.get("property_only_credit_status")
    if status == "violation":
        return (
            "HIGH: DealMachine reported people credits on a property-only underwriting "
            "request. Its comparable evidence was excluded from valuation."
        )
    if status == "unverified":
        return (
            "HIGH: DealMachine did not return complete people-credit telemetry, so the "
            "property-only billing boundary could not be verified from the response."
        )
    return None


def _credit_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _first(values: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if values.get(key) is not None:
            return values[key]
    return None


def _dollars_to_cents(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value >= 0:
        return round(float(value) * 100)
    if isinstance(value, str):
        try:
            parsed = float(value.replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
        return round(parsed * 100) if parsed >= 0 else None
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
