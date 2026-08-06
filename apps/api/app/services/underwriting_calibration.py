from collections import defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    AcquisitionsCopilotRecommendation,
    AcquisitionsCopilotReview,
    ActivityEvent,
    AuditEvent,
    Contact,
    Lead,
    Property,
    UnderwritingCalibrationCase,
    UnderwritingCalibrationDecision,
    UnderwritingMarketAnalysis,
)
from app.schemas.underwriting import (
    CalibrationCaseRead,
    CalibrationCaseUpsert,
    CalibrationDecisionAction,
    CalibrationDecisionCreate,
    CalibrationDecisionRead,
    CalibrationMetricSummary,
    CalibrationOverview,
    CalibrationSegmentSummary,
    ShadowReplayCaseRead,
    ShadowReplayMetric,
    UnderwritingBaselineSummary,
    UnderwritingRolloutGate,
    UnderwritingShadowValidation,
)

FORMULA_REVIEW_SAMPLE = 50
PRELIMINARY_PROVIDER_SAMPLE = 10
ARV_ERROR_MONITOR_PERCENTAGE = 12
ARV_ERROR_REVIEW_PERCENTAGE = 15
RANGE_COVERAGE_MONITOR_PERCENTAGE = 70
RANGE_COVERAGE_REVIEW_PERCENTAGE = 60
SHADOW_TIE_TOLERANCE_PERCENTAGE_POINTS = 0.5
MAXIMUM_OPERATOR_OVERRIDE_PERCENTAGE = 25
REQUIRED_VALIDATION_SCENARIOS = (
    "dense_market",
    "suburban",
    "rural",
    "unique_property",
    "low_comp",
    "wrong_address",
    "provider_failure",
    "high_risk_repairs",
)


def get_calibration_case(
    db: Session,
    principal: Principal,
    analysis_id: UUID,
) -> CalibrationCaseRead | None:
    case = db.scalar(
        select(UnderwritingCalibrationCase).where(
            UnderwritingCalibrationCase.organization_id == principal.organization_id,
            UnderwritingCalibrationCase.analysis_id == analysis_id,
        )
    )
    return calibration_case_to_read(db, case) if case else None


def upsert_calibration_case(
    db: Session,
    principal: Principal,
    analysis_id: UUID,
    payload: CalibrationCaseUpsert,
) -> CalibrationCaseRead:
    analysis = db.scalar(
        select(UnderwritingMarketAnalysis).where(
            UnderwritingMarketAnalysis.id == analysis_id,
            UnderwritingMarketAnalysis.organization_id == principal.organization_id,
        )
    )
    if analysis is None:
        raise ValueError("Market analysis not found.")
    predicted_arv = metadata_int(analysis, "arv_point_cents")
    if predicted_arv is None:
        raise ValueError("This analysis does not contain an ARV point estimate to calibrate.")
    lead = db.get(Lead, analysis.lead_id)
    property_record = db.get(Property, analysis.property_id)
    if lead is None or property_record is None:
        raise ValueError("The analysis is missing its lead or property record.")

    existing = db.scalar(
        select(UnderwritingCalibrationCase).where(
            UnderwritingCalibrationCase.organization_id == principal.organization_id,
            UnderwritingCalibrationCase.analysis_id == analysis.id,
        )
    )
    previous = calibration_audit_value(existing) if existing else None
    case = existing or UnderwritingCalibrationCase(
        organization_id=principal.organization_id,
        lead_id=analysis.lead_id,
        property_id=analysis.property_id,
        analysis_id=analysis.id,
        recorded_by_user_id=principal.user_id,
        market_key=market_key(property_record),
        benchmark_type=payload.benchmark_type,
        evidence_date=payload.evidence_date,
        benchmark_arv_cents=payload.benchmark_arv_cents,
    )
    case.recorded_by_user_id = principal.user_id
    case.market_key = market_key(property_record)
    case.benchmark_type = payload.benchmark_type
    case.evidence_date = payload.evidence_date
    case.benchmark_arv_cents = payload.benchmark_arv_cents
    case.actual_rehab_cents = payload.actual_rehab_cents
    case.actual_seller_contract_cents = payload.actual_seller_contract_cents
    case.actual_disposition_cents = payload.actual_disposition_cents
    case.predicted_arv_low_cents = analysis.arv_low_cents
    case.predicted_arv_point_cents = predicted_arv
    case.predicted_arv_high_cents = analysis.arv_high_cents
    case.predicted_rehab_cents = metadata_int(analysis, "total_rehab_cents")
    case.predicted_seller_ceiling_cents = metadata_int(analysis, "seller_contract_ceiling_cents")
    case.predicted_disposition_cents = metadata_int(analysis, "recommended_disposition_cents")
    case.evidence_reference = payload.evidence_reference
    case.notes = payload.notes
    case.validation_scenarios = list(dict.fromkeys(payload.validation_scenarios))
    db.add(case)
    db.flush()

    action = "underwriting.calibration.update" if existing else "underwriting.calibration.create"
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="lead",
            entity_id=lead.id,
            event_type=action,
            summary=(
                f"Calibration benchmark recorded for {case.market_key}: "
                f"{case.benchmark_type.replace('_', ' ')}."
            ),
        )
    )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="underwriting_calibration_case",
            entity_id=case.id,
            previous_value=previous,
            new_value=calibration_audit_value(case),
            reason="Human-entered underwriting calibration evidence",
        )
    )
    db.commit()
    db.refresh(case)
    return calibration_case_to_read(db, case)


def get_calibration_overview(
    db: Session,
    principal: Principal,
) -> CalibrationOverview:
    cases = list(
        db.scalars(
            select(UnderwritingCalibrationCase)
            .where(UnderwritingCalibrationCase.organization_id == principal.organization_id)
            .order_by(
                UnderwritingCalibrationCase.evidence_date.desc(),
                UnderwritingCalibrationCase.created_at.desc(),
            )
        )
    )
    grouped: dict[str, list[UnderwritingCalibrationCase]] = defaultdict(list)
    for case in cases:
        grouped[case.market_key].append(case)
    analyses = list(
        db.scalars(
            select(UnderwritingMarketAnalysis).where(
                UnderwritingMarketAnalysis.organization_id == principal.organization_id
            )
        )
    )
    analyses_by_id = {analysis.id: analysis for analysis in analyses}
    provider_grouped: dict[tuple[str, str], list[UnderwritingCalibrationCase]] = defaultdict(list)
    for case in cases:
        analysis = analyses_by_id.get(case.analysis_id)
        provider_grouped[(case.market_key, analysis.provider if analysis else "unknown")].append(
            case
        )
    decisions = list(
        db.scalars(
            select(UnderwritingCalibrationDecision)
            .where(UnderwritingCalibrationDecision.organization_id == principal.organization_id)
            .order_by(UnderwritingCalibrationDecision.created_at.desc())
        )
    )
    total_analyses = int(
        db.scalar(
            select(func.count())
            .select_from(UnderwritingMarketAnalysis)
            .where(UnderwritingMarketAnalysis.organization_id == principal.organization_id)
        )
        or 0
    )
    ai_scope_review_decisions = list(
        db.scalars(
            select(AcquisitionsCopilotReview.decision)
            .join(
                AcquisitionsCopilotRecommendation,
                AcquisitionsCopilotRecommendation.id == AcquisitionsCopilotReview.recommendation_id,
            )
            .where(
                AcquisitionsCopilotReview.organization_id == principal.organization_id,
                AcquisitionsCopilotRecommendation.recommendation_type == "repair_scope",
            )
        ).all()
    )
    case_reads = [calibration_case_to_read(db, case) for case in cases]
    return CalibrationOverview(
        baseline=baseline_summary(
            analyses,
            cases=cases,
            ai_scope_review_decisions=ai_scope_review_decisions,
        ),
        overall=metric_summary("All markets", cases, analyses_by_id),
        markets=[
            metric_summary(key, values, analyses_by_id) for key, values in sorted(grouped.items())
        ],
        provider_scorecards=[
            metric_summary(market, values, analyses_by_id)
            for (market, _provider), values in sorted(provider_grouped.items())
        ],
        segments=calibration_segments(cases, analyses_by_id),
        shadow_validation=shadow_validation_summary(
            cases=cases,
            case_reads=case_reads,
            analyses_by_id=analyses_by_id,
            decisions=decisions,
        ),
        cases=case_reads,
        decisions=[calibration_decision_to_read(decision) for decision in decisions],
        uncalibrated_analysis_count=max(0, total_analyses - len(cases)),
    )


def baseline_summary(
    analyses: list[UnderwritingMarketAnalysis],
    *,
    cases: list[UnderwritingCalibrationCase] | None = None,
    ai_scope_review_decisions: list[str] | None = None,
) -> UnderwritingBaselineSummary:
    cases = cases or []
    ai_scope_review_decisions = ai_scope_review_decisions or []
    analyses_by_id = {analysis.id: analysis for analysis in analyses}
    instrumented = [
        analysis
        for analysis in analyses
        if isinstance(
            (analysis.analysis_metadata or {}).get("execution_metrics"),
            dict,
        )
    ]
    execution_metrics = [
        (analysis.analysis_metadata or {})["execution_metrics"] for analysis in instrumented
    ]
    comp_yields = [
        round(
            analysis.selected_comp_count
            / (analysis.selected_comp_count + analysis.rejected_comp_count)
            * 100,
            1,
        )
        for analysis in analyses
        if analysis.selected_comp_count + analysis.rejected_comp_count > 0
    ]
    review_case_count, review_decisions, review_overrides = comp_review_metrics(
        analyses,
        analyses_by_id,
    )
    reuse_count = sum(metric.get("market_data_reused") is True for metric in execution_metrics)
    manual_review_count = sum(
        metric.get("manual_review_required") is True for metric in execution_metrics
    )
    methodology_versions = sorted(
        {
            version
            for analysis in analyses
            if (
                version := string_value(
                    (analysis.analysis_metadata or {}).get("methodology_version")
                )
            )
        }
    )
    repair_catalog_errors = [
        error
        for case in cases
        if (analysis := analyses_by_id.get(case.analysis_id)) is not None
        and repair_catalog_version(analysis) is not None
        and case.actual_rehab_cents is not None
        and (
            error := percentage_error(
                case.predicted_rehab_cents,
                case.actual_rehab_cents,
            )
        )
        is not None
    ]
    ai_scope_corrections = sum(decision == "edited" for decision in ai_scope_review_decisions)
    return UnderwritingBaselineSummary(
        analysis_count=len(analyses),
        instrumented_analysis_count=len(instrumented),
        methodology_versions=methodology_versions,
        median_duration_ms=metadata_median(execution_metrics, "duration_ms"),
        median_provider_returned_comp_count=metadata_median(
            execution_metrics,
            "provider_returned_comp_count",
        ),
        median_candidate_comp_count=rounded_median(
            [
                float(analysis.selected_comp_count + analysis.rejected_comp_count)
                for analysis in analyses
            ]
        ),
        median_selected_comp_count=rounded_median(
            [float(analysis.selected_comp_count) for analysis in analyses]
        ),
        median_comp_yield_percentage=rounded_median(comp_yields),
        market_data_reuse_count=reuse_count,
        market_data_reuse_percentage=percentage_of(reuse_count, len(instrumented)),
        manual_review_required_count=manual_review_count,
        manual_review_required_percentage=percentage_of(
            manual_review_count,
            len(instrumented),
        ),
        comp_review_case_count=review_case_count,
        comp_review_decision_count=review_decisions,
        comp_review_override_count=review_overrides,
        comp_review_override_percentage=percentage_of(
            review_overrides,
            review_decisions,
        ),
        ai_scope_review_count=len(ai_scope_review_decisions),
        ai_scope_correction_count=ai_scope_corrections,
        ai_scope_correction_percentage=percentage_of(
            ai_scope_corrections,
            len(ai_scope_review_decisions),
        ),
        repair_catalog_case_count=len(repair_catalog_errors),
        repair_catalog_median_absolute_error_percentage=rounded_median(
            [abs(value) for value in repair_catalog_errors]
        ),
    )


def metric_summary(
    key: str,
    cases: list[UnderwritingCalibrationCase],
    analyses_by_id: dict[UUID, UnderwritingMarketAnalysis],
) -> CalibrationMetricSummary:
    arv_errors = [
        percentage_error(case.predicted_arv_point_cents, case.benchmark_arv_cents) for case in cases
    ]
    valid_arv_errors = [value for value in arv_errors if value is not None]
    range_results = [
        range_hit(
            case.predicted_arv_low_cents,
            case.predicted_arv_high_cents,
            case.benchmark_arv_cents,
        )
        for case in cases
    ]
    valid_range_results = [value for value in range_results if value is not None]
    repair_errors = [
        percentage_error(case.predicted_rehab_cents, case.actual_rehab_cents)
        for case in cases
        if case.actual_rehab_cents is not None and case.actual_rehab_cents > 0
    ]
    valid_repair_errors = [value for value in repair_errors if value is not None]
    seller_contract_variances = [
        percentage_error(
            case.predicted_seller_ceiling_cents,
            case.actual_seller_contract_cents,
        )
        for case in cases
        if case.actual_seller_contract_cents is not None and case.actual_seller_contract_cents > 0
    ]
    valid_seller_contract_variances = [
        value for value in seller_contract_variances if value is not None
    ]
    disposition_errors = [
        percentage_error(case.predicted_disposition_cents, case.actual_disposition_cents)
        for case in cases
        if case.actual_disposition_cents is not None and case.actual_disposition_cents > 0
    ]
    valid_disposition_errors = [value for value in disposition_errors if value is not None]
    sample_count = len(valid_arv_errors)
    case_analyses = [
        analyses_by_id[case.analysis_id] for case in cases if case.analysis_id in analyses_by_id
    ]
    providers = sorted({analysis.provider for analysis in case_analyses})
    methodology_versions = sorted(
        {
            value
            for analysis in case_analyses
            if (
                value := string_value((analysis.analysis_metadata or {}).get("methodology_version"))
            )
        }
    )
    review_case_count, review_decisions, review_overrides = comp_review_metrics(
        case_analyses,
        analyses_by_id,
    )
    arv_mape = rounded_median([abs(value) for value in valid_arv_errors])
    range_coverage = (
        round(sum(valid_range_results) / len(valid_range_results) * 100, 1)
        if valid_range_results
        else None
    )
    repair_mape = rounded_median([abs(value) for value in valid_repair_errors])
    seller_contract_variance = rounded_median(
        [abs(value) for value in valid_seller_contract_variances]
    )
    disposition_mape = rounded_median([abs(value) for value in valid_disposition_errors])
    median_error = rounded_median(valid_arv_errors)
    failure_patterns = calibration_failure_patterns(
        arv_mape=arv_mape,
        median_error=median_error,
        range_coverage=range_coverage,
        repair_mape=repair_mape,
        disposition_mape=disposition_mape,
        comp_review_decision_count=review_decisions,
        comp_review_override_count=review_overrides,
    )
    return CalibrationMetricSummary(
        market_key=key,
        providers=providers,
        methodology_versions=methodology_versions,
        sample_count=sample_count,
        median_error_percentage=median_error,
        median_absolute_error_percentage=arv_mape,
        range_coverage_percentage=range_coverage,
        overestimate_count=sum(value > 2 for value in valid_arv_errors),
        underestimate_count=sum(value < -2 for value in valid_arv_errors),
        balanced_count=sum(abs(value) <= 2 for value in valid_arv_errors),
        repair_sample_count=len(valid_repair_errors),
        repair_median_absolute_error_percentage=repair_mape,
        seller_contract_sample_count=len(valid_seller_contract_variances),
        seller_contract_median_absolute_variance_percentage=(seller_contract_variance),
        disposition_sample_count=len(valid_disposition_errors),
        disposition_median_absolute_error_percentage=disposition_mape,
        comp_review_case_count=review_case_count,
        comp_review_decision_count=review_decisions,
        comp_review_override_count=review_overrides,
        comp_review_override_percentage=(
            round(review_overrides / review_decisions * 100, 1) if review_decisions else None
        ),
        provider_adequacy=provider_adequacy(
            sample_count=sample_count,
            arv_mape=arv_mape,
            range_coverage=range_coverage,
        ),
        failure_patterns=failure_patterns,
        readiness=readiness(sample_count),
    )


def calibration_segments(
    cases: list[UnderwritingCalibrationCase],
    analyses_by_id: dict[UUID, UnderwritingMarketAnalysis],
) -> list[CalibrationSegmentSummary]:
    grouped: dict[tuple[str, str], list[UnderwritingCalibrationCase]] = defaultdict(list)
    for case in cases:
        analysis = analyses_by_id.get(case.analysis_id)
        if analysis is None:
            continue
        for dimension, segment_key in calibration_segment_keys(analysis):
            grouped[(dimension, segment_key)].append(case)

    segments: list[CalibrationSegmentSummary] = []
    for (dimension, segment_key), segment_cases in sorted(grouped.items()):
        metric = metric_summary(segment_key, segment_cases, analyses_by_id)
        segments.append(
            CalibrationSegmentSummary(
                dimension=dimension,
                segment_key=segment_key,
                sample_count=metric.sample_count,
                median_absolute_error_percentage=(metric.median_absolute_error_percentage),
                range_coverage_percentage=metric.range_coverage_percentage,
                repair_sample_count=metric.repair_sample_count,
                repair_median_absolute_error_percentage=(
                    metric.repair_median_absolute_error_percentage
                ),
                comp_review_override_percentage=(metric.comp_review_override_percentage),
            )
        )
    return segments


def calibration_segment_keys(
    analysis: UnderwritingMarketAnalysis,
) -> set[tuple[str, str]]:
    metadata = analysis.analysis_metadata or {}
    subject = analysis.subject_property or {}
    search = metadata_dict(metadata.get("comp_search_summary"))
    inputs = metadata_dict(metadata.get("pre_meeting_inputs"))
    segments: set[tuple[str, str]] = set()

    property_type = first_non_empty_string(
        subject,
        ("propertyType", "property_type"),
    )
    if property_type:
        segments.add(("property_type", property_type))
    search_level = string_value(search.get("final_level"))
    if search_level:
        segments.add(("search_level", search_level))
    for comp in metadata_list_of_dicts(analysis.selected_comps):
        grade = string_value(comp.get("comp_grade"))
        if grade:
            segments.add(("comp_grade", grade))
    for item in metadata_list_of_dicts(inputs.get("repair_items")):
        category = string_value(item.get("category"))
        status = string_value(item.get("scope_status"))
        if category and status not in {"no_work", "not_assessed"}:
            segments.add(("repair_category", category))
    report_stage = string_value(metadata.get("report_stage"))
    if report_stage:
        segments.add(("verification_stage", report_stage))
    catalog_version = repair_catalog_version(analysis)
    if catalog_version:
        segments.add(("repair_catalog", catalog_version))
    return segments


def repair_catalog_version(
    analysis: UnderwritingMarketAnalysis,
) -> str | None:
    metadata = analysis.analysis_metadata or {}
    inputs = metadata_dict(metadata.get("pre_meeting_inputs"))
    scenario = metadata_dict(inputs.get("repair_scenario")) or metadata_dict(
        metadata.get("repair_scenario")
    )
    return string_value(inputs.get("repair_catalog_version")) or string_value(
        scenario.get("version")
    )


def calibration_case_to_read(
    db: Session,
    case: UnderwritingCalibrationCase,
) -> CalibrationCaseRead:
    lead = db.get(Lead, case.lead_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    property_record = db.get(Property, case.property_id)
    analysis = db.get(UnderwritingMarketAnalysis, case.analysis_id)
    analysis_metadata = (analysis.analysis_metadata or {}) if analysis else {}
    error = percentage_error(case.predicted_arv_point_cents, case.benchmark_arv_cents)
    return CalibrationCaseRead(
        id=case.id,
        lead_id=case.lead_id,
        analysis_id=case.analysis_id,
        seller_name=contact.legal_name if contact else "Unknown seller",
        property_address=(
            f"{property_record.street_address}, {property_record.city}, "
            f"{property_record.state} {property_record.postal_code}"
            if property_record
            else "Unknown property"
        ),
        market_key=case.market_key,
        benchmark_type=case.benchmark_type,
        evidence_date=case.evidence_date,
        benchmark_arv_cents=case.benchmark_arv_cents,
        actual_rehab_cents=case.actual_rehab_cents,
        actual_seller_contract_cents=case.actual_seller_contract_cents,
        actual_disposition_cents=case.actual_disposition_cents,
        predicted_arv_low_cents=case.predicted_arv_low_cents,
        predicted_arv_point_cents=case.predicted_arv_point_cents,
        predicted_arv_high_cents=case.predicted_arv_high_cents,
        predicted_rehab_cents=case.predicted_rehab_cents,
        predicted_seller_ceiling_cents=case.predicted_seller_ceiling_cents,
        predicted_disposition_cents=case.predicted_disposition_cents,
        arv_error_cents=(
            case.predicted_arv_point_cents - case.benchmark_arv_cents
            if case.predicted_arv_point_cents is not None
            else None
        ),
        arv_error_percentage=round(error, 1) if error is not None else None,
        arv_absolute_error_percentage=round(abs(error), 1) if error is not None else None,
        arv_range_hit=range_hit(
            case.predicted_arv_low_cents,
            case.predicted_arv_high_cents,
            case.benchmark_arv_cents,
        ),
        provider=analysis.provider if analysis else "unknown",
        methodology_version=string_value(analysis_metadata.get("methodology_version")),
        confidence_score=analysis.confidence_score if analysis else 0,
        comp_review_applied=isinstance(analysis_metadata.get("comp_review"), dict),
        evidence_reference=case.evidence_reference,
        notes=case.notes,
        validation_scenarios=list(case.validation_scenarios or []),
        recorded_by_user_id=case.recorded_by_user_id,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def metadata_int(analysis: UnderwritingMarketAnalysis, key: str) -> int | None:
    value = (analysis.analysis_metadata or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def create_calibration_decision(
    db: Session,
    principal: Principal,
    payload: CalibrationDecisionCreate,
) -> CalibrationDecisionRead:
    cases, analyses_by_id = calibration_evidence(db, principal)
    available_scopes = {"All markets", *(case.market_key for case in cases)}
    if payload.scope_key not in available_scopes:
        raise ValueError("Choose a market with verified calibration evidence.")
    if payload.decision_type == "methodology_change" and not payload.proposed_methodology_version:
        raise ValueError("A methodology change requires a proposed version.")
    if (
        payload.decision_type in {"methodology_change", "provider_change"}
        and not payload.proposed_changes
    ):
        raise ValueError("Describe the proposed formula or provider change.")
    if payload.decision_type == "v3_rollout":
        if payload.proposed_methodology_version != "v3":
            raise ValueError("A V3 rollout decision must propose methodology version v3.")
        required_confirmations = {
            "owner_usability_accepted",
            "internal_pilot_accepted",
            "rollback_confirmed",
            "human_authority_confirmed",
        }
        missing = sorted(
            key for key in required_confirmations if payload.proposed_changes.get(key) is not True
        )
        if missing:
            raise ValueError(
                "V3 rollout requires Owner usability, internal pilot, rollback, and "
                "human-authority confirmations."
            )

    scoped_cases = (
        cases
        if payload.scope_key == "All markets"
        else [case for case in cases if case.market_key == payload.scope_key]
    )
    metric = metric_summary(payload.scope_key, scoped_cases, analyses_by_id)
    governed_changes = {"methodology_change", "provider_change", "v3_rollout"}
    minimum = FORMULA_REVIEW_SAMPLE if payload.decision_type in governed_changes else 0
    evidence_snapshot: dict[str, object] = metric.model_dump(mode="json")
    if payload.decision_type == "v3_rollout":
        case_reads = [calibration_case_to_read(db, case) for case in cases]
        validation = shadow_validation_summary(
            cases=cases,
            case_reads=case_reads,
            analyses_by_id=analyses_by_id,
            decisions=[],
        )
        evidence_snapshot = {
            "calibration": metric.model_dump(mode="json"),
            "shadow_validation": validation.model_dump(mode="json"),
        }
    decision = UnderwritingCalibrationDecision(
        organization_id=principal.organization_id,
        proposed_by_user_id=principal.user_id,
        scope_key=payload.scope_key,
        decision_type=payload.decision_type,
        status="draft",
        title=payload.title.strip(),
        rationale=payload.rationale.strip(),
        current_methodology_version=latest_methodology_version(scoped_cases, analyses_by_id),
        proposed_methodology_version=payload.proposed_methodology_version,
        proposed_changes=payload.proposed_changes,
        evidence_snapshot=evidence_snapshot,
        sample_count=metric.sample_count,
        minimum_sample_required=minimum,
    )
    db.add(decision)
    db.flush()
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="underwriting.calibration_decision.create",
            entity_type="underwriting_calibration_decision",
            entity_id=decision.id,
            previous_value=None,
            new_value=calibration_decision_audit_value(decision),
            reason="Evidence-backed underwriting methodology review",
        )
    )
    db.commit()
    db.refresh(decision)
    return calibration_decision_to_read(decision)


def decide_calibration_decision(
    db: Session,
    principal: Principal,
    decision_id: UUID,
    payload: CalibrationDecisionAction,
) -> CalibrationDecisionRead:
    decision = db.scalar(
        select(UnderwritingCalibrationDecision).where(
            UnderwritingCalibrationDecision.id == decision_id,
            UnderwritingCalibrationDecision.organization_id == principal.organization_id,
        )
    )
    if decision is None:
        raise ValueError("Calibration decision not found.")
    if decision.status != "draft":
        raise ValueError("Only a draft calibration decision can be decided.")

    previous = calibration_decision_audit_value(decision)
    cases, analyses_by_id = calibration_evidence(db, principal)
    scoped_cases = (
        cases
        if decision.scope_key == "All markets"
        else [case for case in cases if case.market_key == decision.scope_key]
    )
    metric = metric_summary(decision.scope_key, scoped_cases, analyses_by_id)
    if (
        payload.status == "approved"
        and decision.minimum_sample_required
        and metric.sample_count < decision.minimum_sample_required
    ):
        raise ValueError(
            f"This change needs {decision.minimum_sample_required} verified cases "
            f"in {decision.scope_key}; {metric.sample_count} are available."
        )
    if payload.status == "approved" and decision.decision_type == "v3_rollout":
        case_reads = [calibration_case_to_read(db, case) for case in cases]
        validation = shadow_validation_summary(
            cases=cases,
            case_reads=case_reads,
            analyses_by_id=analyses_by_id,
            decisions=[],
        )
        blockers = [
            gate.label
            for gate in validation.gates
            if gate.key != "owner_acceptance" and gate.status != "passed"
        ]
        if blockers:
            raise ValueError(
                "V3 rollout cannot be approved until these gates pass: " + ", ".join(blockers) + "."
            )

    decision.status = payload.status
    decision.decided_by_user_id = principal.user_id
    decision.decision_notes = payload.decision_notes.strip()
    decision.decided_at = datetime.now(UTC)
    if decision.decision_type == "v3_rollout":
        case_reads = [calibration_case_to_read(db, case) for case in cases]
        validation = shadow_validation_summary(
            cases=cases,
            case_reads=case_reads,
            analyses_by_id=analyses_by_id,
            decisions=[decision] if payload.status == "approved" else [],
        )
        decision.evidence_snapshot = {
            "calibration": metric.model_dump(mode="json"),
            "shadow_validation": validation.model_dump(mode="json"),
        }
    else:
        decision.evidence_snapshot = metric.model_dump(mode="json")
    decision.sample_count = metric.sample_count
    db.add(decision)
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=f"underwriting.calibration_decision.{payload.status}",
            entity_type="underwriting_calibration_decision",
            entity_id=decision.id,
            previous_value=previous,
            new_value=calibration_decision_audit_value(decision),
            reason=payload.decision_notes.strip(),
        )
    )
    db.commit()
    db.refresh(decision)
    return calibration_decision_to_read(decision)


def calibration_evidence(
    db: Session,
    principal: Principal,
) -> tuple[
    list[UnderwritingCalibrationCase],
    dict[UUID, UnderwritingMarketAnalysis],
]:
    cases = list(
        db.scalars(
            select(UnderwritingCalibrationCase)
            .where(UnderwritingCalibrationCase.organization_id == principal.organization_id)
            .order_by(UnderwritingCalibrationCase.evidence_date.desc())
        )
    )
    analyses = list(
        db.scalars(
            select(UnderwritingMarketAnalysis).where(
                UnderwritingMarketAnalysis.organization_id == principal.organization_id
            )
        )
    )
    return cases, {analysis.id: analysis for analysis in analyses}


def calibration_decision_to_read(
    decision: UnderwritingCalibrationDecision,
) -> CalibrationDecisionRead:
    return CalibrationDecisionRead(
        id=decision.id,
        scope_key=decision.scope_key,
        decision_type=decision.decision_type,
        status=decision.status,
        title=decision.title,
        rationale=decision.rationale,
        current_methodology_version=decision.current_methodology_version,
        proposed_methodology_version=decision.proposed_methodology_version,
        proposed_changes=decision.proposed_changes,
        evidence_snapshot=decision.evidence_snapshot,
        sample_count=decision.sample_count,
        minimum_sample_required=decision.minimum_sample_required,
        approval_blocked=(
            decision.status == "draft" and decision.minimum_sample_required > decision.sample_count
        ),
        proposed_by_user_id=decision.proposed_by_user_id,
        decided_by_user_id=decision.decided_by_user_id,
        decision_notes=decision.decision_notes,
        decided_at=decision.decided_at,
        created_at=decision.created_at,
        updated_at=decision.updated_at,
    )


def shadow_validation_summary(
    *,
    cases: list[UnderwritingCalibrationCase],
    case_reads: list[CalibrationCaseRead],
    analyses_by_id: dict[UUID, UnderwritingMarketAnalysis],
    decisions: list[UnderwritingCalibrationDecision],
) -> UnderwritingShadowValidation:
    reads_by_analysis_id = {item.analysis_id: item for item in case_reads}
    replay_cases = [
        replay
        for case in cases
        if (read := reads_by_analysis_id.get(case.analysis_id)) is not None
        and (analysis := analyses_by_id.get(case.analysis_id)) is not None
        and (replay := shadow_replay_case(case, read, analysis)) is not None
    ]
    market_groups: dict[str, list[ShadowReplayCaseRead]] = defaultdict(list)
    for replay in replay_cases:
        market_groups[replay.market_key].append(replay)
    scenario_coverage = {
        scenario: sum(scenario in replay.validation_scenarios for replay in replay_cases)
        for scenario in REQUIRED_VALIDATION_SCENARIOS
    }
    overall = shadow_replay_metric("All markets", replay_cases)
    market_metrics = [
        shadow_replay_metric(key, values) for key, values in sorted(market_groups.items())
    ]
    approved_rollout = next(
        (
            decision
            for decision in decisions
            if decision.decision_type == "v3_rollout"
            and decision.status == "approved"
            and decision.proposed_methodology_version == "v3"
        ),
        None,
    )
    paired_analyses = [
        analyses_by_id[case.analysis_id]
        for case in replay_cases
        if case.analysis_id in analyses_by_id
    ]
    _, review_decision_count, review_override_count = comp_review_metrics(
        paired_analyses,
        analyses_by_id,
    )
    override_percentage = percentage_of(review_override_count, review_decision_count)
    gates = shadow_rollout_gates(
        overall=overall,
        markets=market_metrics,
        scenario_coverage=scenario_coverage,
        review_decision_count=review_decision_count,
        override_percentage=override_percentage,
        owner_accepted=approved_rollout is not None,
    )
    activation_allowed = all(gate.status == "passed" for gate in gates)
    if activation_allowed:
        rollout_status = "approved_for_controlled_pilot"
    elif not replay_cases:
        rollout_status = "collecting_verified_outcomes"
    else:
        rollout_status = "validation_blocked"
    return UnderwritingShadowValidation(
        rollout_status=rollout_status,
        activation_allowed=activation_allowed,
        overall=overall,
        markets=market_metrics,
        cases=sorted(
            replay_cases,
            key=lambda item: item.improvement_percentage_points,
            reverse=True,
        ),
        gates=gates,
        scenario_coverage=scenario_coverage,
        approved_rollout_decision_id=(approved_rollout.id if approved_rollout else None),
    )


def shadow_replay_case(
    case: UnderwritingCalibrationCase,
    case_read: CalibrationCaseRead,
    analysis: UnderwritingMarketAnalysis,
) -> ShadowReplayCaseRead | None:
    metadata = analysis.analysis_metadata or {}
    live_adjustment = metadata_dict(metadata.get("market_adjustment"))
    shadow = live_adjustment or metadata_dict(metadata.get("adjustment_shadow"))
    baseline = metadata_dict(shadow.get("baseline"))
    baseline_point = (
        integer_value(baseline.get("arv_point_cents"))
        if live_adjustment
        else case.predicted_arv_point_cents
    )
    conclusion = metadata_dict(shadow.get("conclusion"))
    shadow_point = integer_value(conclusion.get("arv_point_cents"))
    baseline_error = percentage_error(baseline_point, case.benchmark_arv_cents)
    shadow_error = percentage_error(shadow_point, case.benchmark_arv_cents)
    if (
        baseline_point is None
        or shadow_point is None
        or baseline_error is None
        or shadow_error is None
    ):
        return None
    baseline_absolute = abs(baseline_error)
    shadow_absolute = abs(shadow_error)
    difference = baseline_absolute - shadow_absolute
    winner: Literal["v2.2", "v3_shadow", "tie"]
    if abs(difference) <= SHADOW_TIE_TOLERANCE_PERCENTAGE_POINTS:
        winner = "tie"
    elif difference > 0:
        winner = "v3_shadow"
    else:
        winner = "v2.2"
    shadow_status = string_value(shadow.get("status")) or "unknown"
    shadow_confidence = integer_value(conclusion.get("confidence_score"))
    risk_flags: list[str] = []
    if shadow_status != "supported":
        risk_flags.append(f"Shadow evidence is {shadow_status}.")
    if shadow_confidence is not None and shadow_confidence < 60:
        risk_flags.append("Shadow confidence is below 60%.")
    warnings = shadow.get("warnings")
    if isinstance(warnings, list) and warnings:
        risk_flags.append(f"Shadow analysis recorded {len(warnings)} warning(s).")
    return ShadowReplayCaseRead(
        analysis_id=case.analysis_id,
        lead_id=case.lead_id,
        property_address=case_read.property_address,
        market_key=case.market_key,
        benchmark_arv_cents=case.benchmark_arv_cents,
        baseline_arv_cents=baseline_point,
        shadow_arv_cents=shadow_point,
        baseline_absolute_error_percentage=round(baseline_absolute, 1),
        shadow_absolute_error_percentage=round(shadow_absolute, 1),
        improvement_percentage_points=round(difference, 1),
        winner=winner,
        shadow_status=shadow_status,
        shadow_confidence_score=shadow_confidence,
        validation_scenarios=list(case.validation_scenarios or []),
        risk_flags=risk_flags,
    )


def shadow_replay_metric(
    scope_key: str,
    cases: list[ShadowReplayCaseRead],
) -> ShadowReplayMetric:
    baseline_error = rounded_median([case.baseline_absolute_error_percentage for case in cases])
    shadow_error = rounded_median([case.shadow_absolute_error_percentage for case in cases])
    return ShadowReplayMetric(
        scope_key=scope_key,
        paired_case_count=len(cases),
        baseline_median_absolute_error_percentage=baseline_error,
        shadow_median_absolute_error_percentage=shadow_error,
        median_improvement_percentage_points=(
            round(baseline_error - shadow_error, 1)
            if baseline_error is not None and shadow_error is not None
            else None
        ),
        shadow_win_count=sum(case.winner == "v3_shadow" for case in cases),
        tie_count=sum(case.winner == "tie" for case in cases),
        baseline_win_count=sum(case.winner == "v2.2" for case in cases),
        shadow_supported_count=sum(case.shadow_status == "supported" for case in cases),
        shadow_partial_count=sum(case.shadow_status == "partial" for case in cases),
        shadow_unsupported_count=sum(
            case.shadow_status not in {"supported", "partial"} for case in cases
        ),
        unsafe_certainty_count=sum(
            case.shadow_status != "supported"
            and case.shadow_confidence_score is not None
            and case.shadow_confidence_score >= 70
            for case in cases
        ),
    )


def shadow_rollout_gates(
    *,
    overall: ShadowReplayMetric,
    markets: list[ShadowReplayMetric],
    scenario_coverage: dict[str, int],
    review_decision_count: int,
    override_percentage: float | None,
    owner_accepted: bool,
) -> list[UnderwritingRolloutGate]:
    sample_passed = overall.paired_case_count >= FORMULA_REVIEW_SAMPLE
    georgia_markets = [market for market in markets if market.scope_key.startswith("GA |")]
    market_passed = bool(georgia_markets) and all(
        market.paired_case_count >= PRELIMINARY_PROVIDER_SAMPLE for market in georgia_markets
    )
    uncovered_scenarios = [key for key, count in scenario_coverage.items() if count == 0]
    accuracy_measured = overall.paired_case_count >= PRELIMINARY_PROVIDER_SAMPLE
    accuracy_passed = (
        accuracy_measured
        and overall.median_improvement_percentage_points is not None
        and overall.median_improvement_percentage_points >= 0
    )
    operator_measured = review_decision_count >= PRELIMINARY_PROVIDER_SAMPLE
    operator_passed = (
        operator_measured
        and override_percentage is not None
        and override_percentage <= MAXIMUM_OPERATOR_OVERRIDE_PERCENTAGE
    )
    return [
        rollout_gate(
            "paired_sample",
            "Paired verified sample",
            sample_passed,
            current=f"{overall.paired_case_count} cases",
            required=f"{FORMULA_REVIEW_SAMPLE} cases",
            detail=(
                "The same known deal must contain a V2.2 result, V3 shadow result, "
                "and verified ARV."
            ),
        ),
        rollout_gate(
            "georgia_market_sample",
            "Georgia market depth",
            market_passed,
            pending=not georgia_markets,
            current=(
                ", ".join(
                    f"{market.scope_key}: {market.paired_case_count}" for market in georgia_markets
                )
                or "No paired Georgia markets"
            ),
            required=f"At least {PRELIMINARY_PROVIDER_SAMPLE} per tracked Georgia market",
            detail=(
                "Each launch market needs enough local evidence to avoid applying "
                "statewide anecdotes."
            ),
        ),
        rollout_gate(
            "scenario_coverage",
            "Difficult-scenario coverage",
            not uncovered_scenarios,
            current=(
                "All scenarios represented"
                if not uncovered_scenarios
                else f"Missing {len(uncovered_scenarios)}"
            ),
            required=f"All {len(REQUIRED_VALIDATION_SCENARIOS)} scenarios",
            detail=(
                "Missing: " + ", ".join(uncovered_scenarios)
                if uncovered_scenarios
                else (
                    "Dense, suburban, rural, unique, thin-data, failure, and "
                    "repair-risk cases are represented."
                )
            ),
        ),
        rollout_gate(
            "accuracy",
            "Shadow accuracy",
            accuracy_passed,
            pending=not accuracy_measured,
            current=(
                f"{overall.median_improvement_percentage_points:+.1f} points"
                if overall.median_improvement_percentage_points is not None
                else "Not measured"
            ),
            required="V3 median error no worse than V2.2",
            detail="Positive improvement means the shadow method is closer to verified ARV.",
        ),
        rollout_gate(
            "unsafe_certainty",
            "Unsafe certainty",
            overall.paired_case_count > 0 and overall.unsafe_certainty_count == 0,
            pending=overall.paired_case_count == 0,
            current=f"{overall.unsafe_certainty_count} flagged cases",
            required="0 high-confidence unsupported cases",
            detail="Unsupported adjustment evidence cannot be presented with high confidence.",
        ),
        rollout_gate(
            "operator_burden",
            "Operator review burden",
            operator_passed,
            pending=not operator_measured,
            current=(
                f"{override_percentage:.1f}% across {review_decision_count} decisions"
                if override_percentage is not None
                else f"{review_decision_count} review decisions"
            ),
            required=(
                f"At least {PRELIMINARY_PROVIDER_SAMPLE} decisions and no more than "
                f"{MAXIMUM_OPERATOR_OVERRIDE_PERCENTAGE}% overrides"
            ),
            detail="The method should not create more unexplained manual correction work.",
        ),
        rollout_gate(
            "owner_acceptance",
            "Owner rollout acceptance",
            owner_accepted,
            current="Approved" if owner_accepted else "Not approved",
            required="Approved V3 rollout decision",
            detail=(
                "Owner acceptance must confirm usability, internal pilot, rollback, "
                "and human authority."
            ),
        ),
    ]


def rollout_gate(
    key: str,
    label: str,
    passed: bool,
    *,
    current: str,
    required: str,
    detail: str,
    pending: bool = False,
) -> UnderwritingRolloutGate:
    return UnderwritingRolloutGate(
        key=key,
        label=label,
        status="passed" if passed else "pending" if pending else "blocked",
        current_value=current,
        required_value=required,
        detail=detail,
    )


def comp_review_metrics(
    analyses: list[UnderwritingMarketAnalysis],
    analyses_by_id: dict[UUID, UnderwritingMarketAnalysis],
) -> tuple[int, int, int]:
    review_case_count = 0
    decision_count = 0
    override_count = 0
    for analysis in analyses:
        review = (analysis.analysis_metadata or {}).get("comp_review")
        if not isinstance(review, dict):
            continue
        decisions = review.get("decisions")
        if not isinstance(decisions, list):
            continue
        review_case_count += 1
        source_id = parse_uuid(review.get("source_analysis_id"))
        source = analyses_by_id.get(source_id) if source_id else None
        source_included = {
            comparable_key(comp)
            for comp in (source.selected_comps if source else [])
            if comparable_key(comp)
        }
        for item in decisions:
            if not isinstance(item, dict):
                continue
            comp_key = string_value(item.get("comp_key"))
            included = item.get("included")
            if not comp_key or not isinstance(included, bool):
                continue
            decision_count += 1
            if source and included != (comp_key in source_included):
                override_count += 1
    return review_case_count, decision_count, override_count


def provider_adequacy(
    *,
    sample_count: int,
    arv_mape: float | None,
    range_coverage: float | None,
) -> str:
    if sample_count < PRELIMINARY_PROVIDER_SAMPLE:
        return "insufficient_evidence"
    if (arv_mape is not None and arv_mape > ARV_ERROR_REVIEW_PERCENTAGE) or (
        range_coverage is not None and range_coverage < RANGE_COVERAGE_REVIEW_PERCENTAGE
    ):
        return "provider_review_required"
    if (arv_mape is not None and arv_mape > ARV_ERROR_MONITOR_PERCENTAGE) or (
        range_coverage is not None and range_coverage < RANGE_COVERAGE_MONITOR_PERCENTAGE
    ):
        return "monitor"
    return "adequate"


def calibration_failure_patterns(
    *,
    arv_mape: float | None,
    median_error: float | None,
    range_coverage: float | None,
    repair_mape: float | None,
    disposition_mape: float | None,
    comp_review_decision_count: int,
    comp_review_override_count: int,
) -> list[str]:
    patterns: list[str] = []
    if arv_mape is not None and arv_mape > ARV_ERROR_MONITOR_PERCENTAGE:
        patterns.append("ARV error is above Stonegate's 12% pilot monitoring threshold.")
    if median_error is not None and median_error > 5:
        patterns.append("ARV estimates show a material overvaluation bias.")
    elif median_error is not None and median_error < -5:
        patterns.append("ARV estimates show a material undervaluation bias.")
    if range_coverage is not None and range_coverage < RANGE_COVERAGE_MONITOR_PERCENTAGE:
        patterns.append("Verified ARV falls outside the reported range too often.")
    if repair_mape is not None and repair_mape > 25:
        patterns.append("Repair estimates need local cost calibration.")
    if disposition_mape is not None and disposition_mape > 10:
        patterns.append("Disposition guidance differs materially from closed outcomes.")
    if (
        comp_review_decision_count >= 10
        and comp_review_override_count / comp_review_decision_count > 0.25
    ):
        patterns.append("Operators overturn more than 25% of automated comp choices.")
    return patterns


def latest_methodology_version(
    cases: list[UnderwritingCalibrationCase],
    analyses_by_id: dict[UUID, UnderwritingMarketAnalysis],
) -> str | None:
    for case in sorted(cases, key=lambda item: item.evidence_date, reverse=True):
        analysis = analyses_by_id.get(case.analysis_id)
        value = (
            string_value((analysis.analysis_metadata or {}).get("methodology_version"))
            if analysis
            else None
        )
        if value:
            return value
    return None


def parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def comparable_key(value: dict[str, object]) -> str | None:
    return string_value(value.get("provider_id")) or string_value(value.get("formatted_address"))


def metadata_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def metadata_list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def first_non_empty_string(
    values: dict[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        if value := string_value(values.get(key)):
            return value
    return None


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def integer_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def percentage_error(predicted: int | None, actual: int | None) -> float | None:
    if predicted is None or actual is None or actual <= 0:
        return None
    return (predicted - actual) / actual * 100


def range_hit(low: int | None, high: int | None, actual: int) -> bool | None:
    if low is None or high is None:
        return None
    return low <= actual <= high


def rounded_median(values: list[float]) -> float | None:
    return round(median(values), 1) if values else None


def metadata_median(metrics: list[dict[str, object]], key: str) -> float | None:
    values = [
        float(value)
        for metric in metrics
        if isinstance((value := metric.get(key)), (int, float)) and not isinstance(value, bool)
    ]
    return rounded_median(values)


def percentage_of(count: int, total: int) -> float | None:
    return round(count / total * 100, 1) if total else None


def readiness(sample_count: int) -> str:
    if sample_count >= FORMULA_REVIEW_SAMPLE:
        return "formula_review_ready"
    if sample_count >= 10:
        return "building_evidence"
    return "insufficient_sample"


def market_key(property_record: Property) -> str:
    local_market = property_record.county or property_record.city
    return f"{property_record.state.upper()} | {local_market}"


def calibration_audit_value(
    case: UnderwritingCalibrationCase | None,
) -> dict[str, object] | None:
    if case is None:
        return None
    return {
        "analysis_id": str(case.analysis_id),
        "market_key": case.market_key,
        "benchmark_type": case.benchmark_type,
        "evidence_date": case.evidence_date.isoformat(),
        "benchmark_arv_cents": case.benchmark_arv_cents,
        "actual_rehab_cents": case.actual_rehab_cents,
        "actual_seller_contract_cents": case.actual_seller_contract_cents,
        "actual_disposition_cents": case.actual_disposition_cents,
        "evidence_reference": case.evidence_reference,
        "notes": case.notes,
        "validation_scenarios": list(case.validation_scenarios or []),
    }


def calibration_decision_audit_value(
    decision: UnderwritingCalibrationDecision,
) -> dict[str, object]:
    return {
        "scope_key": decision.scope_key,
        "decision_type": decision.decision_type,
        "status": decision.status,
        "title": decision.title,
        "current_methodology_version": decision.current_methodology_version,
        "proposed_methodology_version": decision.proposed_methodology_version,
        "proposed_changes": decision.proposed_changes,
        "sample_count": decision.sample_count,
        "minimum_sample_required": decision.minimum_sample_required,
        "decision_notes": decision.decision_notes,
        "decided_at": (decision.decided_at.isoformat() if decision.decided_at else None),
    }
