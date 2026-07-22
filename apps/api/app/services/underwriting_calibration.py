from collections import defaultdict
from statistics import median
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Contact,
    Lead,
    Property,
    UnderwritingCalibrationCase,
    UnderwritingMarketAnalysis,
)
from app.schemas.underwriting import (
    CalibrationCaseRead,
    CalibrationCaseUpsert,
    CalibrationMetricSummary,
    CalibrationOverview,
)

FORMULA_REVIEW_SAMPLE = 50


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
    case.predicted_seller_ceiling_cents = metadata_int(
        analysis, "seller_contract_ceiling_cents"
    )
    case.predicted_disposition_cents = metadata_int(
        analysis, "recommended_disposition_cents"
    )
    case.evidence_reference = payload.evidence_reference
    case.notes = payload.notes
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
    total_analyses = int(
        db.scalar(
            select(func.count())
            .select_from(UnderwritingMarketAnalysis)
            .where(UnderwritingMarketAnalysis.organization_id == principal.organization_id)
        )
        or 0
    )
    return CalibrationOverview(
        overall=metric_summary("All markets", cases),
        markets=[metric_summary(key, values) for key, values in sorted(grouped.items())],
        cases=[calibration_case_to_read(db, case) for case in cases],
        uncalibrated_analysis_count=max(0, total_analyses - len(cases)),
    )


def metric_summary(
    key: str,
    cases: list[UnderwritingCalibrationCase],
) -> CalibrationMetricSummary:
    arv_errors = [
        percentage_error(case.predicted_arv_point_cents, case.benchmark_arv_cents)
        for case in cases
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
    disposition_errors = [
        percentage_error(case.predicted_disposition_cents, case.actual_disposition_cents)
        for case in cases
        if case.actual_disposition_cents is not None and case.actual_disposition_cents > 0
    ]
    valid_disposition_errors = [value for value in disposition_errors if value is not None]
    sample_count = len(valid_arv_errors)
    return CalibrationMetricSummary(
        market_key=key,
        sample_count=sample_count,
        median_error_percentage=rounded_median(valid_arv_errors),
        median_absolute_error_percentage=rounded_median(
            [abs(value) for value in valid_arv_errors]
        ),
        range_coverage_percentage=(
            round(sum(valid_range_results) / len(valid_range_results) * 100, 1)
            if valid_range_results
            else None
        ),
        overestimate_count=sum(value > 2 for value in valid_arv_errors),
        underestimate_count=sum(value < -2 for value in valid_arv_errors),
        balanced_count=sum(abs(value) <= 2 for value in valid_arv_errors),
        repair_sample_count=len(valid_repair_errors),
        repair_median_absolute_error_percentage=rounded_median(
            [abs(value) for value in valid_repair_errors]
        ),
        disposition_sample_count=len(valid_disposition_errors),
        disposition_median_absolute_error_percentage=rounded_median(
            [abs(value) for value in valid_disposition_errors]
        ),
        readiness=readiness(sample_count),
    )


def calibration_case_to_read(
    db: Session,
    case: UnderwritingCalibrationCase,
) -> CalibrationCaseRead:
    lead = db.get(Lead, case.lead_id)
    contact = db.get(Contact, lead.contact_id) if lead else None
    property_record = db.get(Property, case.property_id)
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
        evidence_reference=case.evidence_reference,
        notes=case.notes,
        recorded_by_user_id=case.recorded_by_user_id,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def metadata_int(analysis: UnderwritingMarketAnalysis, key: str) -> int | None:
    value = (analysis.analysis_metadata or {}).get(key)
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
    }
