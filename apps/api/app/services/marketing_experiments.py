from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Appointment,
    AuditEvent,
    ConversionEvent,
    Lead,
    MarketingExperiment,
    MarketingExperimentAssignment,
    RevenueRecord,
    Transaction,
)
from app.schemas.marketing_experiments import (
    ExperimentSourcePerformance,
    ExperimentVariantPerformance,
    MarketingExperimentCreate,
    MarketingExperimentDecisionRequest,
    MarketingExperimentOverview,
    MarketingExperimentRead,
    MarketingExperimentUpdate,
    MarketingExperimentVariant,
    PublicExperimentRead,
    PublicExperimentResponse,
)
from app.services.conversion_events import get_default_organization

QUALIFIED_STAGES = {
    "qualified",
    "appointment_scheduled",
    "underwriting",
    "offer_presented",
    "negotiating",
    "under_contract",
    "closed",
}


def list_marketing_experiments(
    db: Session,
    principal: Principal,
) -> MarketingExperimentOverview:
    experiments = list(
        db.scalars(
            select(MarketingExperiment)
            .where(MarketingExperiment.organization_id == principal.organization_id)
            .order_by(
                MarketingExperiment.created_at.desc(),
                MarketingExperiment.experiment_key,
            )
        )
    )
    return MarketingExperimentOverview(
        can_manage=(
            PermissionKeys.MANAGE_MARKETING_EXPERIMENTS
            in principal.permission_keys
        ),
        experiments=[
            experiment_read(db, principal.organization_id, experiment)
            for experiment in experiments
        ],
    )


def list_public_experiments(db: Session) -> PublicExperimentResponse:
    organization = get_default_organization(db)
    experiments = list(
        db.scalars(
            select(MarketingExperiment)
            .where(
                MarketingExperiment.organization_id == organization.id,
                MarketingExperiment.status == "running",
            )
            .order_by(MarketingExperiment.started_at, MarketingExperiment.experiment_key)
        )
    )
    selected: dict[str, MarketingExperiment] = {}
    for experiment in experiments:
        selected.setdefault(experiment.surface_key, experiment)
    return PublicExperimentResponse(
        experiments=[
            PublicExperimentRead(
                experiment_key=experiment.experiment_key,
                surface_key=experiment.surface_key,
                variants=parse_variants(experiment),
            )
            for experiment in selected.values()
        ]
    )


def create_marketing_experiment(
    db: Session,
    principal: Principal,
    payload: MarketingExperimentCreate,
) -> MarketingExperimentRead:
    require_manage(principal)
    existing = db.scalar(
        select(MarketingExperiment.id).where(
            MarketingExperiment.organization_id == principal.organization_id,
            MarketingExperiment.experiment_key == payload.experiment_key,
        )
    )
    if existing is not None:
        raise ValueError("Experiment key already exists.")
    values = payload.model_dump(mode="json")
    experiment = MarketingExperiment(
        organization_id=principal.organization_id,
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
        status="draft",
        **values,
    )
    db.add(experiment)
    db.flush()
    add_audit(
        db,
        principal,
        experiment,
        action="marketing.experiment_create",
        reason="Created a draft conversion experiment.",
        previous=None,
    )
    db.commit()
    db.refresh(experiment)
    return experiment_read(db, principal.organization_id, experiment)


def update_marketing_experiment(
    db: Session,
    principal: Principal,
    experiment_id: UUID,
    payload: MarketingExperimentUpdate,
) -> MarketingExperimentRead | None:
    require_manage(principal)
    experiment = get_experiment(db, principal.organization_id, experiment_id)
    if experiment is None:
        return None
    if experiment.status != "draft":
        raise ValueError("Only a draft experiment can be edited.")
    previous = snapshot(experiment)
    for key, value in payload.model_dump(mode="json").items():
        setattr(experiment, key, value)
    experiment.updated_by_user_id = principal.user_id
    add_audit(
        db,
        principal,
        experiment,
        action="marketing.experiment_update",
        reason="Updated a draft conversion experiment.",
        previous=previous,
    )
    db.commit()
    db.refresh(experiment)
    return experiment_read(db, principal.organization_id, experiment)


def decide_marketing_experiment(
    db: Session,
    principal: Principal,
    experiment_id: UUID,
    payload: MarketingExperimentDecisionRequest,
) -> MarketingExperimentRead | None:
    require_manage(principal)
    experiment = get_experiment(db, principal.organization_id, experiment_id)
    if experiment is None:
        return None
    previous = snapshot(experiment)
    now = datetime.now(UTC)

    if payload.decision == "start":
        if experiment.status != "draft":
            raise ValueError("Only a draft experiment can be started.")
        ensure_surface_available(db, experiment)
        experiment.status = "running"
        experiment.started_at = now
        experiment.active_started_at = now
        experiment.accumulated_runtime_seconds = 0
        experiment.paused_at = None
        experiment.completed_at = None
        experiment.decision_notes = None
    elif payload.decision == "pause":
        if experiment.status != "running":
            raise ValueError("Only a running experiment can be paused.")
        accumulate_runtime(experiment, now)
        experiment.status = "paused"
        experiment.paused_at = now
    elif payload.decision == "resume":
        if experiment.status != "paused":
            raise ValueError("Only a paused experiment can be resumed.")
        ensure_surface_available(db, experiment)
        experiment.status = "running"
        experiment.active_started_at = now
        experiment.paused_at = None
    elif payload.decision == "complete":
        if experiment.status not in {"running", "paused"}:
            raise ValueError("Only a running or paused experiment can be completed.")
        if experiment.status == "running":
            accumulate_runtime(experiment, now)
        experiment.status = "completed"
        experiment.completed_at = now
        experiment.decision_notes = payload.reason
    elif payload.decision == "return_to_draft":
        if experiment.status != "paused":
            raise ValueError("Pause the experiment before returning it to draft.")
        assignment_count = int(
            db.scalar(
                select(func.count(MarketingExperimentAssignment.id)).where(
                    MarketingExperimentAssignment.experiment_id == experiment.id
                )
            )
            or 0
        )
        if assignment_count:
            raise ValueError(
                "An experiment with recorded assignments cannot be returned to draft."
            )
        experiment.status = "draft"
        experiment.started_at = None
        experiment.active_started_at = None
        experiment.accumulated_runtime_seconds = 0
        experiment.paused_at = None
    else:
        raise ValueError("Unsupported experiment decision.")

    experiment.updated_by_user_id = principal.user_id
    add_audit(
        db,
        principal,
        experiment,
        action=f"marketing.experiment_{payload.decision}",
        reason=payload.reason,
        previous=previous,
    )
    db.commit()
    db.refresh(experiment)
    return experiment_read(db, principal.organization_id, experiment)


def experiment_read(
    db: Session,
    organization_id: UUID,
    experiment: MarketingExperiment,
) -> MarketingExperimentRead:
    variants = parse_variants(experiment)
    performance = build_performance(db, organization_id, experiment, variants)
    runtime_seconds = experiment.accumulated_runtime_seconds
    if experiment.active_started_at is not None:
        runtime_seconds += max(
            0,
            int(
                (
                    datetime.now(UTC) - as_utc(experiment.active_started_at)
                ).total_seconds()
            ),
        )
    runtime_days = max(0, runtime_seconds // 86400)
    blockers: list[str] = []
    if experiment.started_at is None:
        blockers.append("Experiment has not started.")
    elif runtime_days < experiment.minimum_runtime_days:
        blockers.append(
            f"Collect {experiment.minimum_runtime_days - runtime_days} more runtime days."
        )
    for row in performance:
        remaining = experiment.minimum_sessions_per_variant - row.assigned_sessions
        if remaining > 0:
            blockers.append(f"{row.label} needs {remaining} more assigned sessions.")
    if experiment.status == "completed":
        decision_status = "completed"
    elif blockers:
        decision_status = "collecting_data"
    else:
        decision_status = "ready_for_human_review"
    return MarketingExperimentRead(
        id=experiment.id,
        experiment_key=experiment.experiment_key,
        name=experiment.name,
        hypothesis=experiment.hypothesis,
        surface_key=experiment.surface_key,
        primary_metric=experiment.primary_metric,
        variants=variants,
        minimum_sessions_per_variant=experiment.minimum_sessions_per_variant,
        minimum_runtime_days=experiment.minimum_runtime_days,
        decision_rule=experiment.decision_rule,
        status=experiment.status,
        started_at=experiment.started_at,
        paused_at=experiment.paused_at,
        completed_at=experiment.completed_at,
        decision_notes=experiment.decision_notes,
        runtime_days=runtime_days,
        decision_status=decision_status,
        decision_blockers=blockers,
        performance=performance,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
    )


def build_performance(
    db: Session,
    organization_id: UUID,
    experiment: MarketingExperiment,
    variants: list[MarketingExperimentVariant],
) -> list[ExperimentVariantPerformance]:
    assignments = list(
        db.scalars(
            select(MarketingExperimentAssignment).where(
                MarketingExperimentAssignment.organization_id == organization_id,
                MarketingExperimentAssignment.experiment_id == experiment.id,
            )
        )
    )
    events = list(
        db.scalars(
            select(ConversionEvent).where(
                ConversionEvent.organization_id == organization_id,
                ConversionEvent.experiment_id == experiment.id,
            )
        )
    )
    lead_ids = {
        assignment.lead_id for assignment in assignments if assignment.lead_id is not None
    }
    leads = {
        lead.id: lead
        for lead in (
            db.scalars(
                select(Lead).where(
                    Lead.organization_id == organization_id,
                    Lead.id.in_(lead_ids),
                )
            )
            if lead_ids
            else []
        )
    }
    appointment_leads = (
        set(
            db.scalars(
                select(Appointment.lead_id).where(
                    Appointment.organization_id == organization_id,
                    Appointment.lead_id.in_(lead_ids),
                    Appointment.status.not_in({"cancelled", "canceled"}),
                )
            )
        )
        if lead_ids
        else set()
    )
    contract_leads = (
        set(
            db.scalars(
                select(Transaction.lead_id).where(
                    Transaction.organization_id == organization_id,
                    Transaction.lead_id.in_(lead_ids),
                    Transaction.contract_executed_at.is_not(None),
                )
            )
        )
        if lead_ids
        else set()
    )
    revenue_rows = (
        list(
            db.scalars(
                select(RevenueRecord).where(
                    RevenueRecord.organization_id == organization_id,
                    RevenueRecord.lead_id.in_(lead_ids),
                    RevenueRecord.status == "collected",
                )
            )
        )
        if lead_ids
        else []
    )
    assignments_by_variant: defaultdict[str, list[MarketingExperimentAssignment]] = (
        defaultdict(list)
    )
    for assignment in assignments:
        assignments_by_variant[assignment.variant_key].append(assignment)
    events_by_variant: defaultdict[str, list[ConversionEvent]] = defaultdict(list)
    for event in events:
        if event.experiment_variant:
            events_by_variant[event.experiment_variant].append(event)
    attribution_by_session: dict[str, tuple[str, str, str]] = {}
    for event in sorted(events, key=lambda item: item.created_at):
        if event.session_id:
            attribution_by_session.setdefault(
                event.session_id,
                (
                    event.source or "direct",
                    event.medium or "unknown",
                    event.campaign or "uncategorized",
                ),
            )

    rows: list[ExperimentVariantPerformance] = []
    for variant in variants:
        variant_assignments = assignments_by_variant[variant.key]
        variant_events = events_by_variant[variant.key]
        variant_lead_ids = {
            assignment.lead_id
            for assignment in variant_assignments
            if assignment.lead_id is not None
        }
        form_starts = distinct_event_sessions(variant_events, "form_start")
        form_submits = distinct_event_sessions(variant_events, "form_submit")
        qualified_leads = sum(
            1
            for lead_id in variant_lead_ids
            if lead_id in leads and leads[lead_id].stage_key in QUALIFIED_STAGES
        )
        appointments = len(variant_lead_ids & appointment_leads)
        contracts = len(variant_lead_ids & contract_leads)
        variant_revenue = [
            revenue for revenue in revenue_rows if revenue.lead_id in variant_lead_ids
        ]
        funded_deals = len({revenue.lead_id for revenue in variant_revenue})
        primary_outcomes = {
            "form_submit": form_submits,
            "qualified_lead": qualified_leads,
            "appointment_scheduled": appointments,
            "contract_signed": contracts,
            "funded_deal": funded_deals,
        }[experiment.primary_metric]
        assigned_sessions = len(variant_assignments)
        rows.append(
            ExperimentVariantPerformance(
                key=variant.key,
                label=variant.label,
                cta_label=variant.cta_label,
                assigned_sessions=assigned_sessions,
                desktop_sessions=sum(
                    item.device_category == "desktop" for item in variant_assignments
                ),
                tablet_sessions=sum(
                    item.device_category == "tablet" for item in variant_assignments
                ),
                mobile_sessions=sum(
                    item.device_category == "mobile" for item in variant_assignments
                ),
                form_starts=form_starts,
                form_submits=form_submits,
                leads_created=len(variant_lead_ids),
                qualified_leads=qualified_leads,
                appointments_scheduled=appointments,
                contracts_signed=contracts,
                funded_deals=funded_deals,
                collected_revenue_cents=sum(
                    revenue.amount_cents for revenue in variant_revenue
                ),
                primary_outcomes=primary_outcomes,
                primary_rate_basis_points=(
                    round(primary_outcomes / assigned_sessions * 10000)
                    if assigned_sessions
                    else None
                ),
                source_breakdown=build_source_breakdown(
                    variant_assignments,
                    attribution_by_session,
                    leads,
                    contract_leads,
                    variant_revenue,
                ),
            )
        )
    return rows


def build_source_breakdown(
    assignments: list[MarketingExperimentAssignment],
    attribution_by_session: dict[str, tuple[str, str, str]],
    leads: dict[UUID, Lead],
    contract_leads: set[UUID],
    revenue_rows: list[RevenueRecord],
) -> list[ExperimentSourcePerformance]:
    grouped: defaultdict[
        tuple[str, str, str],
        list[MarketingExperimentAssignment],
    ] = defaultdict(list)
    for assignment in assignments:
        key = attribution_by_session.get(
            assignment.session_id,
            ("direct", "unknown", "uncategorized"),
        )
        grouped[key].append(assignment)
    rows: list[ExperimentSourcePerformance] = []
    for (source, medium, campaign), source_assignments in grouped.items():
        lead_ids = {
            assignment.lead_id
            for assignment in source_assignments
            if assignment.lead_id is not None
        }
        source_revenue = [
            revenue for revenue in revenue_rows if revenue.lead_id in lead_ids
        ]
        rows.append(
            ExperimentSourcePerformance(
                source=source,
                medium=medium,
                campaign=campaign,
                assigned_sessions=len(source_assignments),
                leads_created=len(lead_ids),
                qualified_leads=sum(
                    1
                    for lead_id in lead_ids
                    if lead_id in leads and leads[lead_id].stage_key in QUALIFIED_STAGES
                ),
                contracts_signed=len(lead_ids & contract_leads),
                funded_deals=len(
                    {
                        revenue.lead_id
                        for revenue in source_revenue
                        if revenue.lead_id is not None
                    }
                ),
                collected_revenue_cents=sum(
                    revenue.amount_cents for revenue in source_revenue
                ),
            )
        )
    return sorted(
        rows,
        key=lambda item: (
            -item.assigned_sessions,
            -item.qualified_leads,
            item.source,
            item.campaign,
        ),
    )[:10]


def distinct_event_sessions(events: list[ConversionEvent], event_type: str) -> int:
    return len(
        {
            event.session_id
            for event in events
            if event.event_type == event_type and event.session_id
        }
    )


def parse_variants(
    experiment: MarketingExperiment,
) -> list[MarketingExperimentVariant]:
    return [
        MarketingExperimentVariant.model_validate(variant)
        for variant in experiment.variants
    ]


def ensure_surface_available(db: Session, experiment: MarketingExperiment) -> None:
    conflict = db.scalar(
        select(MarketingExperiment.id).where(
            MarketingExperiment.organization_id == experiment.organization_id,
            MarketingExperiment.surface_key == experiment.surface_key,
            MarketingExperiment.status == "running",
            MarketingExperiment.id != experiment.id,
        )
    )
    if conflict is not None:
        raise ValueError("Another experiment is already running on this surface.")


def accumulate_runtime(
    experiment: MarketingExperiment,
    ended_at: datetime,
) -> None:
    if experiment.active_started_at is not None:
        experiment.accumulated_runtime_seconds += max(
            0,
            int((ended_at - as_utc(experiment.active_started_at)).total_seconds()),
        )
    experiment.active_started_at = None


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_experiment(
    db: Session,
    organization_id: UUID,
    experiment_id: UUID,
) -> MarketingExperiment | None:
    return db.scalar(
        select(MarketingExperiment).where(
            MarketingExperiment.organization_id == organization_id,
            MarketingExperiment.id == experiment_id,
        )
    )


def require_manage(principal: Principal) -> None:
    if (
        PermissionKeys.MANAGE_MARKETING_EXPERIMENTS
        not in principal.permission_keys
    ):
        raise PermissionError("Experiment management requires Marketing or Owner access.")


def snapshot(experiment: MarketingExperiment) -> dict[str, object]:
    return {
        "experiment_key": experiment.experiment_key,
        "surface_key": experiment.surface_key,
        "primary_metric": experiment.primary_metric,
        "status": experiment.status,
        "minimum_sessions_per_variant": experiment.minimum_sessions_per_variant,
        "minimum_runtime_days": experiment.minimum_runtime_days,
        "started_at": (
            experiment.started_at.isoformat() if experiment.started_at else None
        ),
        "completed_at": (
            experiment.completed_at.isoformat() if experiment.completed_at else None
        ),
    }


def add_audit(
    db: Session,
    principal: Principal,
    experiment: MarketingExperiment,
    *,
    action: str,
    reason: str,
    previous: dict[str, object] | None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="marketing_experiment",
            entity_id=experiment.id,
            previous_value=previous,
            new_value=snapshot(experiment),
            reason=reason,
        )
    )
