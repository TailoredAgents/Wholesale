from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Appointment,
    AttributionTouch,
    CallRecord,
    Campaign,
    CampaignCost,
    DealReconciliation,
    DispositionCase,
    Lead,
    MarketingSpend,
    Organization,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCallQualityReview,
    ProspectingCohort,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingWorkSession,
    RevenueRecord,
    Transaction,
    User,
    VoiceLine,
)
from app.schemas.prospecting import (
    ProspectingAnalyticsFilterOptionRead,
    ProspectingAnalyticsFilterOptionsRead,
    ProspectingAnalyticsFiltersRead,
    ProspectingAnalyticsPeriodRead,
    ProspectingDialerAnalyticsRead,
    ProspectingDialerDailyPointRead,
    ProspectingDialerDimensionScorecardRead,
    ProspectingDialerLaunchReadinessRead,
    ProspectingDialerReadinessCheckRead,
    ProspectingDialerScorecardMetricsRead,
    ProspectingMetricCoverageRead,
    ProspectingMetricDefinitionRead,
)
from app.services.operations import get_worker_readiness
from app.services.prospecting_measurement import (
    has_accepted_warm_evidence,
    is_accepted_warm_lead,
)

PROSPECTING_LINE_PURPOSE = "prospecting_outbound"
MAX_REPORT_DAYS = 366
MAX_ORIGIN_RECORDS = 50_000
HELD_APPOINTMENT_STATUSES = {"completed", "held"}
FINAL_APPOINTMENT_STATUSES = HELD_APPOINTMENT_STATUSES | {
    "cancelled",
    "canceled",
    "no_show",
}
PROVIDER_COST_CATEGORIES = {"dialer_license", "phone_number", "voice_usage"}
KNOWN_COST_CATEGORIES = PROVIDER_COST_CATEGORIES | {"va_labor", "list_purchase"}
TERMINAL_FAILED_LEG_STATUSES = {"busy", "failed", "cancelled"}
NATIVE_SOURCE = "native_stonegate"
BATCHDIALER_SOURCE = "batchdialer"
PAID_ADS_SOURCE = "paid_ads"
ATTRIBUTION_MODEL_VERSION = "stonegate-dialer-activity-cohort-v1"
PROFIT_FORMULA_VERSION = "approved-reconciliation-company-profit-v1"
METRIC_STATES = {"known", "partial", "unknown", "not_applicable"}
MetricStatus = Literal["known", "partial", "unknown", "not_applicable"]


@dataclass(frozen=True)
class AnalyticsFilters:
    date_from: date
    date_to: date
    cohort_id: UUID | None = None
    source: str | None = None
    campaign_id: UUID | None = None
    caller_user_id: UUID | None = None
    dial_mode: str | None = None

    @property
    def start_at(self) -> datetime:
        return datetime.combine(self.date_from, time.min, tzinfo=UTC)

    @property
    def end_at_exclusive(self) -> datetime:
        return datetime.combine(self.date_to + timedelta(days=1), time.min, tzinfo=UTC)


@dataclass(frozen=True)
class DownstreamFact:
    lead_id: UUID
    appointments: tuple[tuple[UUID, str, datetime], ...]
    transaction_ids: tuple[UUID, ...]
    signed_transactions: tuple[tuple[UUID, datetime], ...]
    closed_transactions: tuple[tuple[UUID, datetime], ...]
    reconciliations: tuple[tuple[UUID, int, int, datetime | None], ...]
    collected_revenue: tuple[tuple[UUID, int, datetime, UUID | None], ...]


@dataclass(frozen=True)
class AttemptFact:
    attempt: ProspectingAttempt
    campaign: Campaign
    cohort: ProspectingCohort | None
    batch: ProspectCallingBatch
    caller: User
    call: CallRecord | None
    quality: ProspectingCallQualityReview | None
    handoff: ProspectHandoff | None
    downstream: DownstreamFact | None
    legs: tuple[ProspectingDialLeg, ...]
    source: str


@dataclass(frozen=True)
class LeadFact:
    lead: Lead
    source: str
    entry_at: datetime
    downstream: DownstreamFact


@dataclass(frozen=True)
class CostFact:
    cost: CampaignCost
    campaign: Campaign
    cohort: ProspectingCohort | None
    batch: ProspectCallingBatch | None
    dial_mode: str | None
    source: str
    worker: User | None


@dataclass(frozen=True)
class WorkFact:
    session: ProspectingWorkSession
    campaign: Campaign
    cohort: ProspectingCohort
    source: str
    caller: User


@dataclass(frozen=True)
class SpendFact:
    spend: MarketingSpend
    source: str
    complete_month: bool


@dataclass
class ScoreAccumulator:
    raw_mode: Literal["measured", "unavailable", "mixed"]
    entered_lead_ids: set[UUID] = field(default_factory=set)
    attempt_ids: set[UUID] = field(default_factory=set)
    answered_attempt_ids: set[UUID] = field(default_factory=set)
    human_prospect_ids: set[UUID] = field(default_factory=set)
    long_conversation_prospect_ids: set[UUID] = field(default_factory=set)
    right_party_prospect_ids: set[UUID] = field(default_factory=set)
    qualified_prospect_ids: set[UUID] = field(default_factory=set)
    appointment_ids: set[UUID] = field(default_factory=set)
    appointment_status_by_id: dict[UUID, str] = field(default_factory=dict)
    handoff_ids: set[UUID] = field(default_factory=set)
    accepted_handoff_ids: set[UUID] = field(default_factory=set)
    signed_transaction_ids: set[UUID] = field(default_factory=set)
    closed_transaction_ids: set[UUID] = field(default_factory=set)
    reconciliation_by_transaction: dict[UUID, tuple[int, int]] = field(default_factory=dict)
    revenue_by_record: dict[UUID, int] = field(default_factory=dict)
    revenue_transaction_ids: set[UUID] = field(default_factory=set)
    downstream_lead_ids: set[UUID] = field(default_factory=set)
    paid_minutes: int = 0
    productive_calling_minutes: int = 0
    work_session_count: int = 0
    paid_time_applicable: bool = False
    labor_cost_cents: int = 0
    labor_cost_record_count: int = 0
    campaign_voice_cost_cents: int = 0
    campaign_voice_cost_record_count: int = 0
    fixed_provider_cost_cents: int = 0
    fixed_provider_cost_record_count: int = 0
    list_cost_cents: int = 0
    list_cost_record_count: int = 0
    other_cost_cents: int = 0
    other_cost_record_count: int = 0
    marketing_spend_cents: int = 0
    marketing_spend_record_count: int = 0
    marketing_spend_partial_month: bool = False
    leg_count: int = 0
    leg_actual_cost_count: int = 0
    leg_actual_cost_cents: int = 0
    short_calls: int = 0
    blocked_or_failed_calls: int = 0
    no_answer_calls: int = 0
    voicemail_calls: int = 0
    seller_complaints: int = 0
    dnc_requests: int = 0
    connection_seconds: int = 0
    connection_sample_count: int = 0
    reputation_score_total: int = 0
    reputation_score_count: int = 0


def get_prospecting_dialer_analytics(
    db: Session,
    principal: Principal,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    cohort_id: UUID | None = None,
    source: str | None = None,
    campaign_id: UUID | None = None,
    caller_user_id: UUID | None = None,
    dial_mode: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerAnalyticsRead:
    observed_at = _as_utc(now or datetime.now(UTC))
    end_date = date_to or observed_at.date()
    default_lookback_days = min(29, (end_date - date.min).days)
    start_date = date_from or (end_date - timedelta(days=default_lookback_days))
    if end_date < start_date:
        raise ValueError("Analytics end date cannot be before its start date.")
    if end_date > observed_at.date():
        raise ValueError("Analytics end date cannot be in the future.")
    if (end_date - start_date).days + 1 > MAX_REPORT_DAYS:
        raise ValueError(f"Analytics date range cannot exceed {MAX_REPORT_DAYS} days.")
    normalized_source = _normalize_filter_source(source)
    filters = AnalyticsFilters(
        date_from=start_date,
        date_to=end_date,
        cohort_id=cohort_id,
        source=normalized_source,
        campaign_id=campaign_id,
        caller_user_id=caller_user_id,
        dial_mode=(dial_mode or "").strip() or None,
    )
    _validate_scoped_filters(db, principal.organization_id, filters)
    financials_visible = PermissionKeys.VIEW_FINANCIALS in principal.permission_keys
    _validate_origin_volume(
        db,
        principal.organization_id,
        filters,
        include_financial_records=financials_visible,
    )

    attempts = _load_attempt_facts(db, principal.organization_id, filters, observed_at)
    leads = _load_non_prospecting_lead_facts(db, principal.organization_id, filters, observed_at)
    costs = _load_cost_facts(db, principal.organization_id, filters) if financials_visible else []
    work = _load_work_facts(db, principal.organization_id, filters)
    spend = _load_spend_facts(db, principal.organization_id, filters) if financials_visible else []

    by_source = _source_scorecards(
        attempts,
        leads,
        costs,
        work,
        spend,
        financials_visible=financials_visible,
        as_of=observed_at,
    )
    summary_accumulator = _score(
        attempts,
        leads,
        costs,
        work,
        spend,
        raw_mode=_raw_mode(attempts, leads, source=normalized_source),
        as_of=observed_at,
    )
    summary = _finalize_metrics(
        summary_accumulator,
        attempts,
        financials_visible=financials_visible,
    )

    return ProspectingDialerAnalyticsRead(
        attribution_model_version=ATTRIBUTION_MODEL_VERSION,
        profit_formula_version=PROFIT_FORMULA_VERSION,
        financials_visible=financials_visible,
        period=ProspectingAnalyticsPeriodRead(
            date_from=start_date,
            date_to=end_date,
            start_at=filters.start_at,
            end_at_exclusive=filters.end_at_exclusive,
            as_of=observed_at,
        ),
        filters=ProspectingAnalyticsFiltersRead(
            cohort_id=cohort_id,
            source=normalized_source,
            campaign_id=campaign_id,
            caller_user_id=caller_user_id,
            dial_mode=filters.dial_mode,
        ),
        filter_options=_filter_options(db, principal.organization_id),
        summary=summary,
        by_va=_dimension_scorecards(
            attempts,
            costs,
            work,
            "va",
            financials_visible=financials_visible,
            as_of=observed_at,
        ),
        by_campaign=_dimension_scorecards(
            attempts,
            costs,
            work,
            "campaign",
            financials_visible=financials_visible,
            as_of=observed_at,
        ),
        by_cohort=_dimension_scorecards(
            attempts,
            costs,
            work,
            "cohort",
            financials_visible=financials_visible,
            as_of=observed_at,
        ),
        by_list=_dimension_scorecards(
            attempts, costs, work, "list", financials_visible=financials_visible, as_of=observed_at
        ),
        by_dial_mode=_dimension_scorecards(
            attempts,
            costs,
            work,
            "dial_mode",
            financials_visible=financials_visible,
            as_of=observed_at,
        ),
        by_source=by_source,
        daily_trend=_daily_trend(filters, attempts, leads, as_of=observed_at),
        readiness=_launch_readiness(
            db,
            principal.organization_id,
            settings or get_settings(),
            observed_at,
        ),
        metric_definitions=_metric_definitions(),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _normalize_filter_source(value: str | None) -> str | None:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None
    aliases = {
        "native": NATIVE_SOURCE,
        "stonegate": NATIVE_SOURCE,
        "native_dialer": NATIVE_SOURCE,
        "batch": BATCHDIALER_SOURCE,
        "facebook": PAID_ADS_SOURCE,
        "meta": PAID_ADS_SOURCE,
        "google": PAID_ADS_SOURCE,
        "paid": PAID_ADS_SOURCE,
    }
    normalized = aliases.get(normalized, normalized)
    supported = {NATIVE_SOURCE, BATCHDIALER_SOURCE, PAID_ADS_SOURCE, "other"}
    if normalized not in supported:
        raise ValueError(f"Unsupported analytics source: {value}.")
    return normalized


def _validate_scoped_filters(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
) -> None:
    checks: tuple[tuple[UUID | None, type[object], str], ...] = (
        (filters.cohort_id, ProspectingCohort, "cohort"),
        (filters.campaign_id, Campaign, "campaign"),
        (filters.caller_user_id, User, "caller"),
    )
    for record_id, model, label in checks:
        if record_id is None:
            continue
        record = db.get(model, record_id)
        if record is None or getattr(record, "organization_id", None) != organization_id:
            raise ValueError(f"The selected {label} is not available in this organization.")


def _validate_origin_volume(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
    *,
    include_financial_records: bool,
) -> None:
    """Reject pathological materialization before loading report records into memory."""

    total = 0

    def add_count(statement: Select[tuple[int]]) -> None:
        nonlocal total
        total += int(db.scalar(statement) or 0)
        if total > MAX_ORIGIN_RECORDS:
            raise ValueError(
                "Analytics request exceeds the safe 50,000 origin-record limit; "
                "narrow the date range or select a campaign, cohort, caller, or source."
            )

    if filters.source in {None, NATIVE_SOURCE}:
        attempt_statement = (
            select(func.count(ProspectingAttempt.id))
            .select_from(ProspectingAttempt)
            .where(
                ProspectingAttempt.organization_id == organization_id,
                ProspectingAttempt.dial_started_at.is_not(None),
                ProspectingAttempt.dial_started_at >= filters.start_at,
                ProspectingAttempt.dial_started_at < filters.end_at_exclusive,
            )
        )
        if filters.cohort_id is not None:
            attempt_statement = attempt_statement.where(
                ProspectingAttempt.cohort_id == filters.cohort_id
            )
        if filters.caller_user_id is not None:
            attempt_statement = attempt_statement.where(
                ProspectingAttempt.caller_user_id == filters.caller_user_id
            )
        if filters.dial_mode is not None:
            attempt_statement = attempt_statement.where(
                ProspectingAttempt.dialer_mode == filters.dial_mode
            )
        if filters.campaign_id is not None:
            attempt_statement = (
                attempt_statement.join(
                    ProspectCallingBatchEntry,
                    ProspectCallingBatchEntry.id == ProspectingAttempt.batch_entry_id,
                )
                .join(
                    ProspectCallingBatch,
                    ProspectCallingBatch.id == ProspectCallingBatchEntry.prospect_calling_batch_id,
                )
                .where(
                    ProspectCallingBatchEntry.organization_id == organization_id,
                    ProspectCallingBatch.organization_id == organization_id,
                    ProspectCallingBatch.campaign_id == filters.campaign_id,
                )
            )
        add_count(attempt_statement)

    has_dimension_filter = any(
        value is not None
        for value in (
            filters.cohort_id,
            filters.campaign_id,
            filters.caller_user_id,
            filters.dial_mode,
        )
    )
    if filters.source != NATIVE_SOURCE and not has_dimension_filter:
        add_count(
            select(func.count(Lead.id)).where(
                Lead.organization_id == organization_id,
                Lead.created_at >= filters.start_at,
                Lead.created_at < filters.end_at_exclusive,
            )
        )
        if filters.source in {None, BATCHDIALER_SOURCE}:
            add_count(
                select(func.count(AttributionTouch.id)).where(
                    AttributionTouch.organization_id == organization_id,
                    AttributionTouch.touch_type == "batchdialer_handoff",
                    AttributionTouch.created_at >= filters.start_at,
                    AttributionTouch.created_at < filters.end_at_exclusive,
                )
            )

    work_statement = select(func.count(ProspectingWorkSession.id)).where(
        ProspectingWorkSession.organization_id == organization_id,
        ProspectingWorkSession.work_date >= filters.date_from,
        ProspectingWorkSession.work_date <= filters.date_to,
    )
    if filters.campaign_id is not None:
        work_statement = work_statement.where(
            ProspectingWorkSession.campaign_id == filters.campaign_id
        )
    if filters.cohort_id is not None:
        work_statement = work_statement.where(ProspectingWorkSession.cohort_id == filters.cohort_id)
    if filters.caller_user_id is not None:
        work_statement = work_statement.where(
            ProspectingWorkSession.caller_user_id == filters.caller_user_id
        )
    add_count(work_statement)

    if include_financial_records:
        cost_statement = select(func.count(CampaignCost.id)).where(
            CampaignCost.organization_id == organization_id,
            CampaignCost.incurred_on >= filters.date_from,
            CampaignCost.incurred_on <= filters.date_to,
        )
        if filters.campaign_id is not None:
            cost_statement = cost_statement.where(CampaignCost.campaign_id == filters.campaign_id)
        if filters.cohort_id is not None:
            cost_statement = cost_statement.where(CampaignCost.cohort_id == filters.cohort_id)
        if filters.caller_user_id is not None:
            cost_statement = cost_statement.where(
                CampaignCost.worker_user_id == filters.caller_user_id
            )
        add_count(cost_statement)
        if not has_dimension_filter:
            spend_start_at, spend_end_at = _marketing_spend_query_bounds(filters)
            add_count(
                select(func.count(MarketingSpend.id)).where(
                    MarketingSpend.organization_id == organization_id,
                    MarketingSpend.spend_month_at >= spend_start_at,
                    MarketingSpend.spend_month_at < spend_end_at,
                )
            )


def _filter_options(db: Session, organization_id: UUID) -> ProspectingAnalyticsFilterOptionsRead:
    campaigns = db.scalars(
        select(Campaign)
        .where(Campaign.organization_id == organization_id)
        .order_by(Campaign.name, Campaign.id)
    ).all()
    cohorts = db.scalars(
        select(ProspectingCohort)
        .where(ProspectingCohort.organization_id == organization_id)
        .order_by(ProspectingCohort.name, ProspectingCohort.id)
    ).all()
    historical_caller_ids = {
        *db.scalars(
            select(ProspectingAttempt.caller_user_id).where(
                ProspectingAttempt.organization_id == organization_id
            )
        ).all(),
        *db.scalars(
            select(ProspectingWorkSession.caller_user_id).where(
                ProspectingWorkSession.organization_id == organization_id
            )
        ).all(),
        *db.scalars(
            select(CampaignCost.worker_user_id).where(
                CampaignCost.organization_id == organization_id,
                CampaignCost.worker_user_id.is_not(None),
            )
        ).all(),
    }
    organization_users = db.scalars(
        select(User)
        .where(User.organization_id == organization_id)
        .order_by(User.display_name, User.id)
    ).all()
    callers = [
        user
        for user in organization_users
        if user.calling_enabled or user.id in historical_caller_ids
    ]
    dial_modes = sorted(
        {
            *(cohort.dialer_mode for cohort in cohorts if cohort.dialer_mode),
            *(
                mode
                for mode in db.scalars(
                    select(ProspectCallingBatch.dialer_mode).where(
                        ProspectCallingBatch.organization_id == organization_id
                    )
                ).all()
                if mode
            ),
        }
    )
    return ProspectingAnalyticsFilterOptionsRead(
        sources=[NATIVE_SOURCE, BATCHDIALER_SOURCE, PAID_ADS_SOURCE, "other"],
        campaigns=[
            ProspectingAnalyticsFilterOptionRead(id=campaign.id, name=campaign.name)
            for campaign in campaigns
        ],
        cohorts=[
            ProspectingAnalyticsFilterOptionRead(id=cohort.id, name=cohort.name)
            for cohort in cohorts
        ],
        callers=[
            ProspectingAnalyticsFilterOptionRead(id=caller.id, name=caller.display_name)
            for caller in callers
        ],
        dial_modes=dial_modes,
    )


def _load_attempt_facts(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
    as_of: datetime,
) -> list[AttemptFact]:
    if filters.source not in {None, NATIVE_SOURCE}:
        return []
    statement = select(ProspectingAttempt).where(
        ProspectingAttempt.organization_id == organization_id,
        ProspectingAttempt.dial_started_at.is_not(None),
        ProspectingAttempt.dial_started_at >= filters.start_at,
        ProspectingAttempt.dial_started_at < min(filters.end_at_exclusive, as_of),
    )
    if filters.cohort_id is not None:
        statement = statement.where(ProspectingAttempt.cohort_id == filters.cohort_id)
    if filters.caller_user_id is not None:
        statement = statement.where(ProspectingAttempt.caller_user_id == filters.caller_user_id)
    if filters.dial_mode is not None:
        statement = statement.where(ProspectingAttempt.dialer_mode == filters.dial_mode)
    attempts = db.scalars(statement.order_by(ProspectingAttempt.dial_started_at)).all()
    if not attempts:
        return []

    entry_ids = {attempt.batch_entry_id for attempt in attempts}
    entries = db.scalars(
        select(ProspectCallingBatchEntry).where(
            ProspectCallingBatchEntry.organization_id == organization_id,
            ProspectCallingBatchEntry.id.in_(entry_ids),
        )
    ).all()
    entry_by_id = {entry.id: entry for entry in entries}
    batch_ids = {entry.prospect_calling_batch_id for entry in entries}
    batches = db.scalars(
        select(ProspectCallingBatch).where(
            ProspectCallingBatch.organization_id == organization_id,
            ProspectCallingBatch.id.in_(batch_ids),
        )
    ).all()
    batch_by_id = {batch.id: batch for batch in batches}
    campaign_ids = {batch.campaign_id for batch in batches}
    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.id.in_(campaign_ids),
        )
    ).all()
    campaign_by_id = {campaign.id: campaign for campaign in campaigns}
    cohort_ids = {attempt.cohort_id for attempt in attempts if attempt.cohort_id is not None}
    cohorts = (
        db.scalars(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == organization_id,
                ProspectingCohort.id.in_(cohort_ids),
            )
        ).all()
        if cohort_ids
        else []
    )
    cohort_by_id = {cohort.id: cohort for cohort in cohorts}
    caller_ids = {attempt.caller_user_id for attempt in attempts}
    callers = db.scalars(
        select(User).where(User.organization_id == organization_id, User.id.in_(caller_ids))
    ).all()
    caller_by_id = {caller.id: caller for caller in callers}
    attempt_ids = {attempt.id for attempt in attempts}
    calls = db.scalars(
        select(CallRecord).where(
            CallRecord.organization_id == organization_id,
            CallRecord.prospecting_attempt_id.in_(attempt_ids),
        )
    ).all()
    call_by_attempt = {call.prospecting_attempt_id: call for call in calls}
    quality_rows = db.scalars(
        select(ProspectingCallQualityReview).where(
            ProspectingCallQualityReview.organization_id == organization_id,
            ProspectingCallQualityReview.attempt_id.in_(attempt_ids),
        )
    ).all()
    quality_by_attempt = {row.attempt_id: row for row in quality_rows}
    handoffs = db.scalars(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == organization_id,
            ProspectHandoff.attempt_id.in_(attempt_ids),
        )
    ).all()
    handoff_by_attempt = {handoff.attempt_id: handoff for handoff in handoffs}
    accepted_handoff_winners = _accepted_handoff_winner_ids(
        db,
        organization_id,
        {handoff.lead_id for handoff in handoffs},
    )
    legs = db.scalars(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.organization_id == organization_id,
            ProspectingDialLeg.attempt_id.in_(attempt_ids),
        )
    ).all()
    legs_by_attempt: dict[UUID, list[ProspectingDialLeg]] = defaultdict(list)
    for leg in legs:
        if leg.attempt_id is not None:
            legs_by_attempt[leg.attempt_id].append(leg)
    downstream_by_lead = _load_downstream_facts(
        db,
        organization_id,
        {handoff.lead_id for handoff in handoffs if handoff.id in accepted_handoff_winners},
    )

    result: list[AttemptFact] = []
    for attempt in attempts:
        entry = entry_by_id.get(attempt.batch_entry_id)
        batch = batch_by_id.get(entry.prospect_calling_batch_id) if entry else None
        campaign = campaign_by_id.get(batch.campaign_id) if batch else None
        caller = caller_by_id.get(attempt.caller_user_id)
        if batch is None or campaign is None or caller is None:
            continue
        if filters.campaign_id is not None and campaign.id != filters.campaign_id:
            continue
        handoff = handoff_by_attempt.get(attempt.id)
        result.append(
            AttemptFact(
                attempt=attempt,
                campaign=campaign,
                cohort=(
                    cohort_by_id.get(attempt.cohort_id) if attempt.cohort_id is not None else None
                ),
                batch=batch,
                caller=caller,
                call=call_by_attempt.get(attempt.id),
                quality=quality_by_attempt.get(attempt.id),
                handoff=handoff,
                downstream=(
                    downstream_by_lead.get(handoff.lead_id)
                    if handoff is not None and handoff.id in accepted_handoff_winners
                    else None
                ),
                legs=tuple(legs_by_attempt.get(attempt.id, [])),
                source=NATIVE_SOURCE,
            )
        )
    return result


def _accepted_handoff_winner_ids(
    db: Session,
    organization_id: UUID,
    lead_ids: set[UUID],
) -> set[UUID]:
    """Choose at most one evidence-complete accepted native handoff per CRM lead."""

    if not lead_ids:
        return set()
    handoffs = db.scalars(
        select(ProspectHandoff).where(
            ProspectHandoff.organization_id == organization_id,
            ProspectHandoff.lead_id.in_(lead_ids),
        )
    ).all()
    attempt_ids = {handoff.attempt_id for handoff in handoffs}
    attempts = db.scalars(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == organization_id,
            ProspectingAttempt.id.in_(attempt_ids),
        )
    ).all()
    attempt_by_id = {attempt.id: attempt for attempt in attempts}
    winners: dict[UUID, ProspectHandoff] = {}
    for handoff in sorted(
        handoffs,
        key=lambda row: (
            _as_utc(row.reviewed_at or row.submitted_at),
            _as_utc(row.submitted_at),
            row.id,
        ),
    ):
        attempt = attempt_by_id.get(handoff.attempt_id)
        if attempt is None or not is_accepted_warm_lead(attempt, handoff):
            continue
        winners.setdefault(handoff.lead_id, handoff)
    return {handoff.id for handoff in winners.values()}


def _load_downstream_facts(
    db: Session,
    organization_id: UUID,
    lead_ids: set[UUID],
) -> dict[UUID, DownstreamFact]:
    if not lead_ids:
        return {}
    appointments = db.scalars(
        select(Appointment).where(
            Appointment.organization_id == organization_id,
            Appointment.lead_id.in_(lead_ids),
        )
    ).all()
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.organization_id == organization_id,
            Transaction.lead_id.in_(lead_ids),
        )
    ).all()
    transaction_ids = {transaction.id for transaction in transactions}
    disposition_cases = (
        db.scalars(
            select(DispositionCase).where(
                DispositionCase.organization_id == organization_id,
                DispositionCase.transaction_id.in_(transaction_ids),
            )
        ).all()
        if transaction_ids
        else []
    )
    disposition_by_transaction = {row.transaction_id: row for row in disposition_cases}
    reconciliations = (
        db.scalars(
            select(DealReconciliation).where(
                DealReconciliation.organization_id == organization_id,
                DealReconciliation.transaction_id.in_(transaction_ids),
                DealReconciliation.status == "approved",
            )
        ).all()
        if transaction_ids
        else []
    )
    revenues = db.scalars(
        select(RevenueRecord).where(
            RevenueRecord.organization_id == organization_id,
            RevenueRecord.lead_id.in_(lead_ids),
            RevenueRecord.status == "collected",
        )
    ).all()
    appointments_by_lead: dict[UUID, list[Appointment]] = defaultdict(list)
    transactions_by_lead: dict[UUID, list[Transaction]] = defaultdict(list)
    reconciliation_by_transaction = {row.transaction_id: row for row in reconciliations}
    revenue_by_lead: dict[UUID, list[RevenueRecord]] = defaultdict(list)
    for appointment in appointments:
        appointments_by_lead[appointment.lead_id].append(appointment)
    for transaction in transactions:
        transactions_by_lead[transaction.lead_id].append(transaction)
    for revenue in revenues:
        if revenue.lead_id is not None:
            revenue_by_lead[revenue.lead_id].append(revenue)
    result: dict[UUID, DownstreamFact] = {}
    for lead_id in lead_ids:
        lead_appointments = appointments_by_lead.get(lead_id, [])
        lead_transactions = transactions_by_lead.get(lead_id, [])
        result[lead_id] = DownstreamFact(
            lead_id=lead_id,
            appointments=tuple(
                (row.id, row.status.lower(), _as_utc(row.created_at)) for row in lead_appointments
            ),
            transaction_ids=tuple(row.id for row in lead_transactions),
            signed_transactions=tuple(
                (row.id, _as_utc(row.contract_executed_at))
                for row in lead_transactions
                if row.contract_executed_at is not None
            ),
            closed_transactions=tuple(
                (row.id, _transaction_close_at(row))
                for row in lead_transactions
                if (row.closed_at is not None or row.funded_at is not None)
                and row.id in disposition_by_transaction
                and _normalized_strategy(disposition_by_transaction[row.id].strategy)
                == "assignment"
            ),
            reconciliations=tuple(
                (
                    row.id,
                    reconciliation_by_transaction[row.id].gross_revenue_cents,
                    reconciliation_by_transaction[row.id].company_profit_cents,
                    (
                        _as_utc(
                            cast(
                                datetime,
                                reconciliation_by_transaction[row.id].approved_at,
                            )
                        )
                        if reconciliation_by_transaction[row.id].approved_at is not None
                        else None
                    ),
                )
                for row in lead_transactions
                if row.id in reconciliation_by_transaction
            ),
            collected_revenue=tuple(
                (row.id, row.amount_cents, _as_utc(row.received_at), row.transaction_id)
                for row in revenue_by_lead.get(lead_id, [])
            ),
        )
    return result


def _normalized_strategy(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return "assignment" if normalized in {"assignment", "contract_assignment"} else normalized


def _transaction_close_at(transaction: Transaction) -> datetime:
    candidates = [
        _as_utc(value)
        for value in (transaction.funded_at, transaction.closed_at)
        if value is not None
    ]
    return min(candidates)


def _load_non_prospecting_lead_facts(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
    as_of: datetime,
) -> list[LeadFact]:
    if filters.source == NATIVE_SOURCE:
        return []
    if any(
        value is not None
        for value in (
            filters.cohort_id,
            filters.campaign_id,
            filters.caller_user_id,
            filters.dial_mode,
        )
    ):
        return []
    created_leads = db.scalars(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.created_at >= filters.start_at,
            Lead.created_at < min(filters.end_at_exclusive, as_of),
        )
    ).all()
    batch_touches = db.scalars(
        select(AttributionTouch).where(
            AttributionTouch.organization_id == organization_id,
            AttributionTouch.touch_type == "batchdialer_handoff",
            AttributionTouch.created_at >= filters.start_at,
            AttributionTouch.created_at < min(filters.end_at_exclusive, as_of),
        )
    ).all()
    lead_ids = {lead.id for lead in created_leads} | {touch.lead_id for touch in batch_touches}
    if not lead_ids:
        return []
    leads = db.scalars(
        select(Lead).where(
            Lead.organization_id == organization_id,
            Lead.id.in_(lead_ids),
        )
    ).all()
    lead_by_id = {lead.id: lead for lead in leads}
    creation_touches = _first_attribution_touches(
        db,
        organization_id,
        lead_ids,
        touch_type="lead_creation",
        before_at=as_of,
    )
    all_batch_touches = _first_attribution_touches(
        db,
        organization_id,
        lead_ids,
        touch_type="batchdialer_handoff",
        before_at=as_of,
    )
    creation_touch_by_lead = {touch.lead_id: touch for touch in creation_touches}
    batch_touch_by_lead = {touch.lead_id: touch for touch in all_batch_touches}

    # Acquisition and calling activity are separate cohorts. A paid lead may later be
    # worked in BatchDialer; preserve both rows while summary sets deduplicate the lead.
    entries: dict[tuple[UUID, str], datetime] = {}
    for lead_id, touch in batch_touch_by_lead.items():
        if lead_id not in lead_by_id:
            continue
        first_entry_at = _as_utc(touch.created_at)
        if filters.start_at <= first_entry_at < min(filters.end_at_exclusive, as_of):
            entries[(lead_id, BATCHDIALER_SOURCE)] = first_entry_at
    for lead in created_leads:
        lead_creation_touch = creation_touch_by_lead.get(lead.id)
        source = _canonical_lead_source(lead, lead_creation_touch)
        batch_creation_without_handoff = (
            source == BATCHDIALER_SOURCE and lead.id not in batch_touch_by_lead
        )
        if source != NATIVE_SOURCE and (
            source != BATCHDIALER_SOURCE or batch_creation_without_handoff
        ):
            entry_at = _as_utc(lead.created_at)
            key = (lead.id, source)
            entries[key] = min(entries.get(key, entry_at), entry_at)
    cutoff = min(filters.end_at_exclusive, as_of)
    entries = {
        key: entry_at
        for key, entry_at in entries.items()
        if filters.start_at <= entry_at < cutoff
        and (filters.source is None or key[1] == filters.source)
    }
    downstream = _load_downstream_facts(
        db,
        organization_id,
        {lead_id for lead_id, _source in entries},
    )
    return [
        LeadFact(
            lead=lead_by_id[lead_id],
            source=source,
            entry_at=entry_at,
            downstream=downstream[lead_id],
        )
        for (lead_id, source), entry_at in sorted(
            entries.items(), key=lambda item: (item[1], item[0][0], item[0][1])
        )
    ]


def _canonical_lead_source(lead: Lead, touch: AttributionTouch | None) -> str:
    lead_source = _normalize_source_token(lead.source)
    touch_source = _normalize_source_token(touch.source if touch else None)
    touch_medium = _normalize_source_token(touch.medium if touch else None)
    if "batchdialer" in lead_source or "batchdialer" in touch_source:
        return BATCHDIALER_SOURCE
    if lead_source in {"cold_call", "prospecting"} or touch_source == "cold_call":
        return NATIVE_SOURCE
    paid_tokens = {
        "facebook",
        "facebook_lead_ads",
        "fb",
        "meta",
        "instagram",
        "google",
        "google_ads",
        "audience_network",
    }
    if (
        lead_source in paid_tokens
        or touch_source in paid_tokens
        or touch_medium in {"paid", "paid_social", "cpc", "ppc"}
        or bool(touch and (touch.fbclid or touch.gclid))
    ):
        return PAID_ADS_SOURCE
    return "other"


def _normalize_source_token(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _first_attribution_touches(
    db: Session,
    organization_id: UUID,
    lead_ids: set[UUID],
    *,
    touch_type: str,
    before_at: datetime,
) -> list[AttributionTouch]:
    """Return one deterministic earliest touch per lead without materializing replay history."""

    if not lead_ids:
        return []
    ranked = (
        select(
            AttributionTouch.id.label("touch_id"),
            func.row_number()
            .over(
                partition_by=AttributionTouch.lead_id,
                order_by=(AttributionTouch.created_at.asc(), AttributionTouch.id.asc()),
            )
            .label("touch_rank"),
        )
        .where(
            AttributionTouch.organization_id == organization_id,
            AttributionTouch.lead_id.in_(lead_ids),
            AttributionTouch.touch_type == touch_type,
            AttributionTouch.created_at < before_at,
        )
        .subquery()
    )
    return list(
        db.scalars(
            select(AttributionTouch)
            .join(ranked, ranked.c.touch_id == AttributionTouch.id)
            .where(ranked.c.touch_rank == 1)
        ).all()
    )


def _prospecting_source(
    *,
    cohort: ProspectingCohort | None,
    batch: ProspectCallingBatch | None = None,
    explicit_source: str | None = None,
) -> str:
    """Resolve durable prospecting cost/work ownership without guessing from campaign names."""

    explicit = (explicit_source or "").strip().lower().replace("-", "_").replace(" ", "_")
    if explicit == "provider_import" or "batchdialer" in explicit:
        return BATCHDIALER_SOURCE
    dialer_tokens = {
        (value or "").strip().lower().replace("-", "_").replace(" ", "_")
        for value in (
            cohort.dialer_mode if cohort else None,
            batch.dialer_mode if batch else None,
        )
        if value
    }
    if any("batchdialer" in token or token == "batch" for token in dialer_tokens):
        return BATCHDIALER_SOURCE
    if dialer_tokens & {
        "native",
        "native_stonegate",
        "stonegate",
        "stonegate_native",
        "one_line_power",
        "multi_line_parallel",
    }:
        return NATIVE_SOURCE
    return "other"


def _load_cost_facts(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
) -> list[CostFact]:
    statement = select(CampaignCost).where(
        CampaignCost.organization_id == organization_id,
        CampaignCost.incurred_on >= filters.date_from,
        CampaignCost.incurred_on <= filters.date_to,
    )
    if filters.campaign_id is not None:
        statement = statement.where(CampaignCost.campaign_id == filters.campaign_id)
    if filters.cohort_id is not None:
        statement = statement.where(CampaignCost.cohort_id == filters.cohort_id)
    if filters.caller_user_id is not None:
        statement = statement.where(CampaignCost.worker_user_id == filters.caller_user_id)
    costs = db.scalars(statement.order_by(CampaignCost.incurred_on, CampaignCost.id)).all()
    if not costs:
        return []
    campaign_ids = {cost.campaign_id for cost in costs}
    worker_ids = {cost.worker_user_id for cost in costs if cost.worker_user_id is not None}
    workers = (
        db.scalars(
            select(User).where(
                User.organization_id == organization_id,
                User.id.in_(worker_ids),
            )
        ).all()
        if worker_ids
        else []
    )
    worker_by_id = {worker.id: worker for worker in workers}
    work_sources = db.execute(
        select(ProspectingWorkSession.campaign_cost_id, ProspectingWorkSession.source).where(
            ProspectingWorkSession.organization_id == organization_id,
            ProspectingWorkSession.campaign_cost_id.in_({cost.id for cost in costs}),
        )
    ).all()
    work_source_by_cost: dict[UUID, str] = {}
    for work_cost_id, work_source_name in work_sources:
        work_source_by_cost[work_cost_id] = work_source_name
    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.id.in_(campaign_ids),
        )
    ).all()
    campaign_by_id = {campaign.id: campaign for campaign in campaigns}
    cohort_ids = {cost.cohort_id for cost in costs if cost.cohort_id is not None}
    cohorts = (
        db.scalars(
            select(ProspectingCohort).where(
                ProspectingCohort.organization_id == organization_id,
                ProspectingCohort.id.in_(cohort_ids),
            )
        ).all()
        if cohort_ids
        else []
    )
    cohort_by_id = {cohort.id: cohort for cohort in cohorts}
    import_batch_ids = {cost.import_batch_id for cost in costs if cost.import_batch_id is not None}
    batches = (
        db.scalars(
            select(ProspectCallingBatch).where(
                ProspectCallingBatch.organization_id == organization_id,
                ProspectCallingBatch.import_batch_id.in_(import_batch_ids),
            )
        ).all()
        if import_batch_ids
        else []
    )
    batches_by_import: dict[UUID, list[ProspectCallingBatch]] = defaultdict(list)
    for batch in batches:
        if batch.import_batch_id is not None:
            batches_by_import[batch.import_batch_id].append(batch)
    result: list[CostFact] = []
    for cost in costs:
        campaign = campaign_by_id.get(cost.campaign_id)
        if campaign is None:
            continue
        cohort = cohort_by_id.get(cost.cohort_id) if cost.cohort_id is not None else None
        candidates = (
            batches_by_import.get(cost.import_batch_id, [])
            if cost.import_batch_id is not None
            else []
        )
        resolved_batch = candidates[0] if len(candidates) == 1 else None
        dial_mode = (
            cohort.dialer_mode
            if cohort
            else (resolved_batch.dialer_mode if resolved_batch else None)
        )
        source = _prospecting_source(
            cohort=cohort,
            batch=resolved_batch,
            explicit_source=(
                work_source_by_cost.get(cost.id)
                or (
                    cost.vendor_name
                    if "batchdialer" in (cost.vendor_name or "").strip().lower()
                    else None
                )
            ),
        )
        if filters.source is not None and source != filters.source:
            continue
        if filters.dial_mode is not None and dial_mode != filters.dial_mode:
            continue
        result.append(
            CostFact(
                cost=cost,
                campaign=campaign,
                cohort=cohort,
                batch=resolved_batch,
                dial_mode=dial_mode,
                source=source,
                worker=(
                    worker_by_id.get(cost.worker_user_id)
                    if cost.worker_user_id is not None
                    else None
                ),
            )
        )
    return result


def _load_work_facts(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
) -> list[WorkFact]:
    statement = select(ProspectingWorkSession).where(
        ProspectingWorkSession.organization_id == organization_id,
        ProspectingWorkSession.work_date >= filters.date_from,
        ProspectingWorkSession.work_date <= filters.date_to,
    )
    if filters.campaign_id is not None:
        statement = statement.where(ProspectingWorkSession.campaign_id == filters.campaign_id)
    if filters.cohort_id is not None:
        statement = statement.where(ProspectingWorkSession.cohort_id == filters.cohort_id)
    if filters.caller_user_id is not None:
        statement = statement.where(ProspectingWorkSession.caller_user_id == filters.caller_user_id)
    sessions = db.scalars(
        statement.order_by(ProspectingWorkSession.work_date, ProspectingWorkSession.id)
    ).all()
    if not sessions:
        return []
    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.id.in_({row.campaign_id for row in sessions}),
        )
    ).all()
    cohorts = db.scalars(
        select(ProspectingCohort).where(
            ProspectingCohort.organization_id == organization_id,
            ProspectingCohort.id.in_({row.cohort_id for row in sessions}),
        )
    ).all()
    callers = db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.id.in_({row.caller_user_id for row in sessions}),
        )
    ).all()
    campaign_by_id = {row.id: row for row in campaigns}
    cohort_by_id = {row.id: row for row in cohorts}
    caller_by_id = {row.id: row for row in callers}
    result: list[WorkFact] = []
    for session in sessions:
        campaign = campaign_by_id.get(session.campaign_id)
        cohort = cohort_by_id.get(session.cohort_id)
        caller = caller_by_id.get(session.caller_user_id)
        if campaign is None or cohort is None or caller is None:
            continue
        if filters.dial_mode is not None and cohort.dialer_mode != filters.dial_mode:
            continue
        source = _prospecting_source(cohort=cohort, explicit_source=session.source)
        if filters.source is not None and source != filters.source:
            continue
        result.append(
            WorkFact(
                session=session,
                campaign=campaign,
                cohort=cohort,
                source=source,
                caller=caller,
            )
        )
    return result


def _load_spend_facts(
    db: Session,
    organization_id: UUID,
    filters: AnalyticsFilters,
) -> list[SpendFact]:
    if any(
        value is not None
        for value in (
            filters.cohort_id,
            filters.campaign_id,
            filters.caller_user_id,
            filters.dial_mode,
        )
    ):
        return []
    spend_start_at, spend_end_at = _marketing_spend_query_bounds(filters)
    rows = db.scalars(
        select(MarketingSpend).where(
            MarketingSpend.organization_id == organization_id,
            MarketingSpend.spend_month_at >= spend_start_at,
            MarketingSpend.spend_month_at < spend_end_at,
        )
    ).all()
    result: list[SpendFact] = []
    for row in rows:
        source = _canonical_spend_source(row.source)
        if filters.source is not None and source != filters.source:
            continue
        month_start = _as_utc(row.spend_month_at).replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        next_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12
            else month_start.replace(month=month_start.month + 1)
        )
        if month_start >= filters.end_at_exclusive or next_month <= filters.start_at:
            continue
        result.append(
            SpendFact(
                spend=row,
                source=source,
                complete_month=(
                    filters.start_at <= month_start and filters.end_at_exclusive >= next_month
                ),
            )
        )
    return result


def _marketing_spend_query_bounds(filters: AnalyticsFilters) -> tuple[datetime, datetime]:
    first_month = filters.start_at.replace(day=1)
    final_month = datetime.combine(filters.date_to.replace(day=1), time.min, tzinfo=UTC)
    month_after_final = (
        final_month.replace(year=final_month.year + 1, month=1)
        if final_month.month == 12
        else final_month.replace(month=final_month.month + 1)
    )
    return first_month, month_after_final


def _canonical_spend_source(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if "batchdialer" in normalized:
        return BATCHDIALER_SOURCE
    if normalized in {
        "facebook",
        "facebook_ads",
        "facebook_lead_ads",
        "fb",
        "instagram",
        "meta",
        "meta_ads",
        "google",
        "google_ads",
        "paid_ads",
        "paid_social",
        "ppc",
    }:
        return PAID_ADS_SOURCE
    if normalized in {"native", "native_stonegate", "stonegate_native", "cold_call"}:
        return NATIVE_SOURCE
    return "other"


def _raw_mode(
    attempts: list[AttemptFact],
    leads: list[LeadFact],
    *,
    source: str | None,
) -> Literal["measured", "unavailable", "mixed"]:
    if source == NATIVE_SOURCE:
        return "measured"
    if source in {BATCHDIALER_SOURCE, PAID_ADS_SOURCE, "other"}:
        return "unavailable"
    if attempts and leads:
        return "mixed"
    return "measured" if attempts else "unavailable"


def _score(
    attempts: Iterable[AttemptFact],
    leads: Iterable[LeadFact],
    costs: Iterable[CostFact],
    work: Iterable[WorkFact],
    spend: Iterable[SpendFact],
    *,
    raw_mode: Literal["measured", "unavailable", "mixed"],
    as_of: datetime,
) -> ScoreAccumulator:
    accumulator = ScoreAccumulator(raw_mode=raw_mode)
    for fact in attempts:
        attempt = fact.attempt
        accumulator.paid_time_applicable = True
        accumulator.attempt_ids.add(attempt.id)
        answered = bool(
            attempt.answered_at or attempt.answer_classification in {"live_person", "machine"}
        )
        if answered:
            accumulator.answered_attempt_ids.add(attempt.id)
        if attempt.answer_classification == "live_person":
            accumulator.human_prospect_ids.add(attempt.prospect_id)
            if fact.call and (fact.call.duration_seconds or 0) > 60:
                accumulator.long_conversation_prospect_ids.add(attempt.prospect_id)
        if (
            attempt.answer_classification == "live_person"
            and attempt.party_classification == "right_party"
        ):
            accumulator.right_party_prospect_ids.add(attempt.prospect_id)
        if has_accepted_warm_evidence(attempt):
            accumulator.qualified_prospect_ids.add(attempt.prospect_id)
        if fact.handoff is not None:
            accumulator.entered_lead_ids.add(fact.handoff.lead_id)
            accumulator.handoff_ids.add(fact.handoff.lead_id)
            if is_accepted_warm_lead(attempt, fact.handoff):
                accumulator.accepted_handoff_ids.add(fact.handoff.lead_id)
                if fact.downstream is not None:
                    origin_at = max(
                        _as_utc(attempt.dial_started_at or attempt.started_at),
                        _as_utc(fact.handoff.submitted_at),
                    )
                    _add_downstream(
                        accumulator,
                        fact.downstream,
                        origin_at=origin_at,
                        as_of=as_of,
                    )
        for leg in fact.legs:
            accumulator.leg_count += 1
            if leg.actual_cost_cents is not None:
                accumulator.leg_actual_cost_count += 1
                accumulator.leg_actual_cost_cents += leg.actual_cost_cents
            if leg.status in TERMINAL_FAILED_LEG_STATUSES or leg.provider_error_code:
                accumulator.blocked_or_failed_calls += 1
            if leg.status == "no_answer" or leg.terminal_result == "no_answer":
                accumulator.no_answer_calls += 1
            if leg.dialing_at and leg.connected_at:
                seconds = int((_as_utc(leg.connected_at) - _as_utc(leg.dialing_at)).total_seconds())
                if seconds >= 0:
                    accumulator.connection_seconds += seconds
                    accumulator.connection_sample_count += 1
        outcome = (attempt.outcome or "").lower()
        if outcome in {"voicemail", "answering_machine", "left_voicemail"}:
            accumulator.voicemail_calls += 1
        if outcome == "do_not_call":
            accumulator.dnc_requests += 1
        if (
            fact.call
            and attempt.answer_classification == "live_person"
            and fact.call.duration_seconds is not None
            and fact.call.duration_seconds <= 15
        ):
            accumulator.short_calls += 1
        if fact.quality:
            flags = {flag.lower() for flag in fact.quality.compliance_flags}
            if flags & {"seller_complaint", "complaint", "consumer_complaint"}:
                accumulator.seller_complaints += 1
        reputation = (attempt.measurement_metadata or {}).get("number_reputation_score")
        if isinstance(reputation, int) and 0 <= reputation <= 100:
            accumulator.reputation_score_total += reputation
            accumulator.reputation_score_count += 1

    for lead_fact in leads:
        accumulator.entered_lead_ids.add(lead_fact.lead.id)
        if lead_fact.source == BATCHDIALER_SOURCE:
            accumulator.paid_time_applicable = True
            accumulator.handoff_ids.add(lead_fact.lead.id)
            accumulator.accepted_handoff_ids.add(lead_fact.lead.id)
        _add_downstream(
            accumulator,
            lead_fact.downstream,
            origin_at=lead_fact.entry_at,
            as_of=as_of,
        )
    for work_fact in work:
        if work_fact.source in {NATIVE_SOURCE, BATCHDIALER_SOURCE}:
            accumulator.paid_time_applicable = True
        accumulator.paid_minutes += work_fact.session.paid_minutes
        accumulator.productive_calling_minutes += work_fact.session.productive_calling_minutes
        accumulator.work_session_count += 1
    for cost_fact in costs:
        if cost_fact.source in {NATIVE_SOURCE, BATCHDIALER_SOURCE}:
            accumulator.paid_time_applicable = True
        amount = cost_fact.cost.amount_cents
        category = cost_fact.cost.category.lower()
        if category == "va_labor":
            accumulator.labor_cost_cents += amount
            accumulator.labor_cost_record_count += 1
        elif category == "voice_usage":
            accumulator.campaign_voice_cost_cents += amount
            accumulator.campaign_voice_cost_record_count += 1
        elif category in {"dialer_license", "phone_number"}:
            accumulator.fixed_provider_cost_cents += amount
            accumulator.fixed_provider_cost_record_count += 1
        elif category == "list_purchase":
            accumulator.list_cost_cents += amount
            accumulator.list_cost_record_count += 1
        else:
            accumulator.other_cost_cents += amount
            accumulator.other_cost_record_count += 1
    for spend_fact in spend:
        if spend_fact.complete_month:
            accumulator.marketing_spend_cents += spend_fact.spend.amount_cents
            accumulator.marketing_spend_record_count += 1
        else:
            accumulator.marketing_spend_partial_month = True
    return accumulator


def _add_downstream(
    accumulator: ScoreAccumulator,
    downstream: DownstreamFact,
    *,
    origin_at: datetime,
    as_of: datetime,
) -> None:
    accumulator.downstream_lead_ids.add(downstream.lead_id)
    for appointment_id, status, created_at in downstream.appointments:
        if created_at < origin_at or created_at > as_of:
            continue
        accumulator.appointment_ids.add(appointment_id)
        accumulator.appointment_status_by_id[appointment_id] = status
    eligible_signed_transaction_ids = {
        transaction_id
        for transaction_id, executed_at in downstream.signed_transactions
        if origin_at <= executed_at <= as_of
    }
    accumulator.signed_transaction_ids.update(eligible_signed_transaction_ids)
    eligible_closed_transaction_ids = {
        transaction_id
        for transaction_id, closed_at in downstream.closed_transactions
        if origin_at <= closed_at <= as_of and transaction_id in eligible_signed_transaction_ids
    }
    accumulator.closed_transaction_ids.update(eligible_closed_transaction_ids)
    for (
        transaction_id,
        gross_revenue_cents,
        company_profit_cents,
        approved_at,
    ) in downstream.reconciliations:
        if approved_at is not None and approved_at <= as_of:
            accumulator.reconciliation_by_transaction[transaction_id] = (
                gross_revenue_cents,
                company_profit_cents,
            )
    for (
        revenue_id,
        amount_cents,
        received_at,
        revenue_transaction_id,
    ) in downstream.collected_revenue:
        if (
            origin_at <= received_at <= as_of
            and revenue_transaction_id is not None
            and revenue_transaction_id in eligible_closed_transaction_ids
        ):
            accumulator.revenue_by_record[revenue_id] = amount_cents
            accumulator.revenue_transaction_ids.add(revenue_transaction_id)


def _rate(numerator: int, denominator: int, scale: int = 10_000) -> int | None:
    if denominator <= 0:
        return None
    return (numerator * scale + denominator // 2) // denominator


def _finalize_metrics(
    accumulator: ScoreAccumulator,
    attempts: Iterable[AttemptFact],
    *,
    financials_visible: bool,
) -> ProspectingDialerScorecardMetricsRead:
    attempt_rows = list(attempts)
    measured = accumulator.raw_mode == "measured"
    mixed = accumulator.raw_mode == "mixed"
    attempts_count = len(accumulator.attempt_ids)
    answered_count = len(accumulator.answered_attempt_ids)
    human_count = len(accumulator.human_prospect_ids)
    right_party_count = len(accumulator.right_party_prospect_ids)
    qualified_count = len(accumulator.qualified_prospect_ids)

    def raw_value(value: int) -> int | None:
        return value if measured else None

    final_appointments = {
        appointment_id
        for appointment_id, appointment_status in accumulator.appointment_status_by_id.items()
        if appointment_status in FINAL_APPOINTMENT_STATUSES
    }
    held_appointments = {
        appointment_id
        for appointment_id, appointment_status in accumulator.appointment_status_by_id.items()
        if appointment_status in HELD_APPOINTMENT_STATUSES
    }
    appointments_set = len(accumulator.appointment_ids)
    entered_leads = len(accumulator.entered_lead_ids)
    if appointments_set == 0:
        appointments_held: int | None = 0
    elif len(final_appointments) == appointments_set:
        appointments_held = len(held_appointments)
    else:
        appointments_held = len(held_appointments) if held_appointments else None

    handoffs_applicable = accumulator.raw_mode != "unavailable" or bool(accumulator.handoff_ids)
    submitted_handoffs = len(accumulator.handoff_ids) if handoffs_applicable else None
    accepted_handoffs = len(accumulator.accepted_handoff_ids) if handoffs_applicable else None
    signed_contracts = len(accumulator.signed_transaction_ids)
    closed_assignments = len(accumulator.closed_transaction_ids)

    if accumulator.work_session_count:
        paid_minutes: int | None = accumulator.paid_minutes
        productive_minutes: int | None = accumulator.productive_calling_minutes
    else:
        paid_minutes = None
        productive_minutes = None

    if accumulator.leg_count and accumulator.leg_actual_cost_count == accumulator.leg_count:
        provider_cost = accumulator.leg_actual_cost_cents + accumulator.fixed_provider_cost_cents
        provider_status: MetricStatus = "known"
    elif accumulator.campaign_voice_cost_record_count:
        provider_cost = (
            accumulator.campaign_voice_cost_cents + accumulator.fixed_provider_cost_cents
        )
        provider_status = "known"
    elif attempts_count == 0 and accumulator.fixed_provider_cost_record_count:
        provider_cost = accumulator.fixed_provider_cost_cents
        provider_status = "known"
    elif accumulator.paid_time_applicable:
        provider_cost = None
        provider_status = "unknown"
    else:
        provider_cost = None
        provider_status = "not_applicable"

    if accumulator.labor_cost_record_count:
        labor_cost = accumulator.labor_cost_cents
        labor_status: MetricStatus = "known"
    elif accumulator.paid_time_applicable:
        labor_cost = None
        labor_status = "unknown"
    else:
        labor_cost = None
        labor_status = "not_applicable"

    cost_activity_present = bool(
        attempts_count or accumulator.work_session_count or accumulator.downstream_lead_ids
    )
    if accumulator.list_cost_record_count:
        list_cost: int | None = accumulator.list_cost_cents
        list_cost_status: MetricStatus = "known"
    elif accumulator.paid_time_applicable and cost_activity_present:
        list_cost = None
        list_cost_status = "unknown"
    else:
        list_cost = None
        list_cost_status = "not_applicable"
    attributed_other_cost = accumulator.other_cost_cents + accumulator.marketing_spend_cents
    if accumulator.marketing_spend_partial_month:
        other_cost: int | None = None
        other_cost_status: MetricStatus = "partial"
        total_cost = None
        total_cost_status: MetricStatus = "partial"
    else:
        other_cost = attributed_other_cost
        other_cost_status = "known"
    if accumulator.marketing_spend_partial_month:
        pass
    elif accumulator.marketing_spend_record_count and not attempts_count:
        total_cost = (list_cost or 0) + attributed_other_cost
        total_cost_status = "known"
    elif labor_cost is not None and provider_cost is not None and list_cost is not None:
        total_cost = labor_cost + provider_cost + list_cost + attributed_other_cost
        total_cost_status = "known"
    elif (
        not attempts_count
        and not accumulator.downstream_lead_ids
        and not accumulator.work_session_count
        and not accumulator.paid_time_applicable
    ):
        total_cost = (list_cost or 0) + attributed_other_cost
        total_cost_status = "known"
    else:
        total_cost = None
        total_cost_status = "unknown"

    if closed_assignments == 0:
        realized_revenue: int | None = 0
        revenue_status: MetricStatus = "known"
    elif accumulator.closed_transaction_ids.issubset(accumulator.revenue_transaction_ids):
        realized_revenue = sum(accumulator.revenue_by_record.values())
        revenue_status = "known"
    elif accumulator.revenue_by_record:
        realized_revenue = None
        revenue_status = "partial"
    else:
        realized_revenue = None
        revenue_status = "unknown"
    if closed_assignments == 0:
        contribution_profit: int | None = 0
        profit_status: MetricStatus = "known"
    elif accumulator.closed_transaction_ids.issubset(accumulator.reconciliation_by_transaction):
        contribution_profit = sum(
            accumulator.reconciliation_by_transaction[transaction_id][1]
            for transaction_id in accumulator.closed_transaction_ids
        )
        profit_status = "known"
    else:
        contribution_profit = None
        profit_status = "unknown"

    statuses: dict[str, MetricStatus] = {}
    statuses["entered_leads"] = "known"
    raw_status: MetricStatus = "known" if measured else ("partial" if mixed else "not_applicable")
    for key in (
        "attempts",
        "answered_calls",
        "human_conversations",
        "conversations_over_60_seconds",
        "right_party_contacts",
        "qualified_sellers",
        "short_calls",
        "blocked_or_failed_calls",
        "no_answer_calls",
        "voicemail_calls",
    ):
        statuses[key] = raw_status
    statuses["human_contact_rate_basis_points"] = (
        raw_status if not measured else ("known" if attempts_count else "not_applicable")
    )
    statuses["right_party_contact_rate_basis_points"] = (
        raw_status if not measured else ("known" if human_count else "not_applicable")
    )
    statuses["qualified_seller_rate_basis_points"] = (
        raw_status if not measured else ("known" if right_party_count else "not_applicable")
    )
    statuses["average_connection_time_seconds"] = (
        raw_status
        if not measured
        else (
            "known"
            if accumulator.connection_sample_count
            else ("unknown" if attempts_count else "not_applicable")
        )
    )
    statuses["answer_rate_trend_basis_points"] = (
        raw_status if not measured else ("known" if attempts_count >= 2 else "not_applicable")
    )
    statuses["appointments_set"] = "known"
    statuses["appointments_held"] = (
        "known"
        if appointments_set == 0 or len(final_appointments) == appointments_set
        else "partial"
    )
    handoff_status: MetricStatus = (
        "known" if accumulator.raw_mode == "unavailable" and accumulator.handoff_ids else raw_status
    )
    statuses["submitted_handoffs"] = handoff_status
    statuses["accepted_handoffs"] = handoff_status
    statuses["accepted_handoff_rate_basis_points"] = (
        handoff_status if submitted_handoffs else "not_applicable"
    )
    statuses["signed_contracts"] = "known"
    statuses["closed_assignments"] = "known"
    statuses["paid_minutes"] = (
        "known"
        if paid_minutes is not None
        else ("unknown" if accumulator.paid_time_applicable else "not_applicable")
    )
    statuses["productive_calling_minutes"] = statuses["paid_minutes"]
    statuses["labor_cost_cents"] = labor_status
    statuses["provider_cost_cents"] = provider_status
    statuses["list_cost_cents"] = list_cost_status
    statuses["other_cost_cents"] = other_cost_status
    statuses["total_cost_cents"] = total_cost_status
    statuses["gross_revenue_cents"] = revenue_status
    statuses["contribution_profit_cents"] = profit_status
    statuses["silent_or_dead_air_calls"] = (
        "unknown" if measured and attempts_count else "not_applicable"
    )
    statuses["duplicate_call_incidents"] = (
        "unknown" if measured and attempts_count else "not_applicable"
    )
    statuses["seller_complaints"] = raw_status
    statuses["dnc_requests"] = raw_status
    statuses["abandoned_calls"] = "not_applicable"
    if not measured or not attempts_count:
        statuses["number_reputation_score"] = "not_applicable"
    elif accumulator.reputation_score_count == attempts_count and attempts_count:
        statuses["number_reputation_score"] = "known"
    elif accumulator.reputation_score_count:
        statuses["number_reputation_score"] = "partial"
    else:
        statuses["number_reputation_score"] = "unknown"

    financial_keys = {
        "labor_cost_cents",
        "provider_cost_cents",
        "list_cost_cents",
        "other_cost_cents",
        "total_cost_cents",
        "gross_revenue_cents",
        "contribution_profit_cents",
        "profit_per_paid_hour_cents",
        "cost_per_qualified_seller_cents",
        "cost_per_contract_cents",
    }
    if not financials_visible:
        for key in financial_keys:
            statuses[key] = "not_applicable"

    attempts_per_hour = (
        _rate(attempts_count * 60, paid_minutes, 100) if measured and paid_minutes else None
    )
    conversations_per_hour = (
        _rate(human_count * 60, paid_minutes, 100) if measured and paid_minutes else None
    )
    profit_per_hour = (
        _rate(contribution_profit * 60, paid_minutes, 1)
        if contribution_profit is not None and paid_minutes
        else None
    )
    cost_per_qualified = (
        _rate(total_cost, qualified_count, 1)
        if total_cost is not None and qualified_count
        else None
    )
    cost_per_contract = (
        _rate(total_cost, signed_contracts, 1)
        if total_cost is not None and signed_contracts
        else None
    )
    statuses["attempts_per_paid_hour_x100"] = (
        "known"
        if attempts_per_hour is not None
        else ("unknown" if measured and attempts_count else "not_applicable")
    )
    statuses["human_conversations_per_paid_hour_x100"] = (
        "known"
        if conversations_per_hour is not None
        else ("unknown" if measured and attempts_count else "not_applicable")
    )
    statuses["profit_per_paid_hour_cents"] = (
        "known"
        if profit_per_hour is not None
        else (
            "unknown"
            if financials_visible and accumulator.paid_time_applicable
            else "not_applicable"
        )
    )
    statuses["cost_per_qualified_seller_cents"] = (
        "known"
        if cost_per_qualified is not None
        else (
            "unknown"
            if financials_visible and qualified_count and total_cost is None
            else "not_applicable"
        )
    )
    statuses["cost_per_contract_cents"] = (
        "known"
        if cost_per_contract is not None
        else (
            "unknown"
            if financials_visible and signed_contracts and total_cost is None
            else "not_applicable"
        )
    )
    for key, _numerator, denominator in (
        ("appointment_held_rate_basis_points", len(held_appointments), appointments_set),
        ("contract_rate_basis_points", signed_contracts, entered_leads),
        ("close_rate_basis_points", closed_assignments, signed_contracts),
    ):
        if key == "appointment_held_rate_basis_points" and (
            appointments_set and len(final_appointments) != appointments_set
        ):
            statuses[key] = "partial"
        else:
            statuses[key] = "known" if denominator else "not_applicable"

    coverage = _coverage(
        accumulator,
        appointments_set=appointments_set,
        final_appointments=len(final_appointments),
        financials_visible=financials_visible,
    )
    return ProspectingDialerScorecardMetricsRead(
        entered_leads=entered_leads,
        attempts=raw_value(attempts_count),
        answered_calls=raw_value(answered_count),
        human_conversations=raw_value(human_count),
        conversations_over_60_seconds=raw_value(len(accumulator.long_conversation_prospect_ids)),
        right_party_contacts=raw_value(right_party_count),
        qualified_sellers=raw_value(qualified_count),
        appointments_set=appointments_set,
        appointments_held=appointments_held,
        submitted_handoffs=submitted_handoffs,
        accepted_handoffs=accepted_handoffs,
        signed_contracts=signed_contracts,
        closed_assignments=closed_assignments,
        paid_minutes=paid_minutes,
        productive_calling_minutes=productive_minutes,
        labor_cost_cents=labor_cost if financials_visible else None,
        provider_cost_cents=provider_cost if financials_visible else None,
        list_cost_cents=list_cost if financials_visible else None,
        other_cost_cents=other_cost if financials_visible else None,
        total_cost_cents=total_cost if financials_visible else None,
        gross_revenue_cents=realized_revenue if financials_visible else None,
        contribution_profit_cents=contribution_profit if financials_visible else None,
        attempts_per_paid_hour_x100=attempts_per_hour,
        human_conversations_per_paid_hour_x100=conversations_per_hour,
        profit_per_paid_hour_cents=profit_per_hour if financials_visible else None,
        cost_per_qualified_seller_cents=cost_per_qualified if financials_visible else None,
        cost_per_contract_cents=cost_per_contract if financials_visible else None,
        human_contact_rate_basis_points=(_rate(human_count, attempts_count) if measured else None),
        right_party_contact_rate_basis_points=(
            _rate(right_party_count, human_count) if measured else None
        ),
        qualified_seller_rate_basis_points=(
            _rate(qualified_count, right_party_count) if measured else None
        ),
        accepted_handoff_rate_basis_points=(
            _rate(len(accumulator.accepted_handoff_ids), len(accumulator.handoff_ids))
            if handoffs_applicable
            else None
        ),
        appointment_held_rate_basis_points=(
            _rate(len(held_appointments), appointments_set)
            if appointments_set == len(final_appointments)
            else None
        ),
        contract_rate_basis_points=_rate(
            signed_contracts,
            entered_leads,
        ),
        close_rate_basis_points=_rate(closed_assignments, signed_contracts),
        short_calls=raw_value(accumulator.short_calls),
        silent_or_dead_air_calls=None,
        blocked_or_failed_calls=raw_value(accumulator.blocked_or_failed_calls),
        no_answer_calls=raw_value(accumulator.no_answer_calls),
        voicemail_calls=raw_value(accumulator.voicemail_calls),
        duplicate_call_incidents=None,
        seller_complaints=raw_value(accumulator.seller_complaints),
        dnc_requests=raw_value(accumulator.dnc_requests),
        abandoned_calls=None,
        average_connection_time_seconds=(
            _rate(accumulator.connection_seconds, accumulator.connection_sample_count, 1)
            if measured
            else None
        ),
        number_reputation_score=(
            _rate(accumulator.reputation_score_total, accumulator.reputation_score_count, 1)
            if accumulator.reputation_score_count
            else None
        ),
        answer_rate_trend_basis_points=(_answer_rate_trend(attempt_rows) if measured else None),
        status_by_key=statuses,
        coverage=coverage,
    )


def _coverage(
    accumulator: ScoreAccumulator,
    *,
    appointments_set: int,
    final_appointments: int,
    financials_visible: bool,
) -> ProspectingMetricCoverageRead:
    warnings: list[str] = []
    if accumulator.raw_mode == "mixed":
        raw_coverage = None
        warnings.append(
            "Raw call rates are hidden because the row mixes dialer and lead-entry sources."
        )
    else:
        raw_coverage = 10_000 if accumulator.raw_mode == "measured" else None
    attempts_count = len(accumulator.attempt_ids)
    paid_coverage = (
        10_000
        if accumulator.work_session_count
        else (0 if accumulator.paid_time_applicable else None)
    )
    if accumulator.paid_time_applicable and accumulator.work_session_count == 0:
        warnings.append("Paid-hour coverage is missing for attributed dialer activity.")
    provider_coverage: int | None
    if financials_visible:
        if accumulator.campaign_voice_cost_record_count:
            provider_coverage = 10_000
        elif accumulator.leg_count:
            provider_coverage = _rate(accumulator.leg_actual_cost_count, accumulator.leg_count)
        else:
            provider_coverage = 0 if accumulator.paid_time_applicable else None
        if accumulator.paid_time_applicable and not provider_coverage:
            warnings.append(
                "Actual provider cost is unavailable; reserved leg cost is never reported."
            )
    else:
        provider_coverage = None
    appointment_coverage = _rate(final_appointments, appointments_set) if appointments_set else None
    if appointment_coverage is not None and appointment_coverage < 10_000:
        warnings.append("Some appointments do not yet have a final held/cancelled/no-show outcome.")
    closed_count = len(accumulator.closed_transaction_ids)
    profit_coverage = (
        _rate(
            len(
                accumulator.closed_transaction_ids
                & accumulator.reconciliation_by_transaction.keys()
            ),
            closed_count,
        )
        if closed_count
        else None
    )
    if financials_visible and closed_count and profit_coverage != 10_000:
        warnings.append(
            "Contribution profit is hidden until every close has an approved reconciliation."
        )
    reputation_coverage = (
        _rate(accumulator.reputation_score_count, attempts_count) if attempts_count else None
    )
    if attempts_count and not accumulator.reputation_score_count:
        warnings.append(
            "Number reputation and dead-air metrics require durable detector telemetry."
        )
    if not financials_visible:
        profit_coverage = None
    if financials_visible and accumulator.marketing_spend_partial_month:
        warnings.append(
            "Monthly marketing spend is excluded because the report does not cover the full "
            "UTC calendar month."
        )
    return ProspectingMetricCoverageRead(
        raw_attempts_basis_points=raw_coverage,
        paid_hours_basis_points=paid_coverage,
        provider_cost_basis_points=provider_coverage,
        appointment_outcomes_basis_points=appointment_coverage,
        profit_basis_points=profit_coverage,
        reputation_basis_points=reputation_coverage,
        warnings=warnings,
    )


def _answer_rate_trend(attempts: list[AttemptFact]) -> int | None:
    if len(attempts) < 2:
        return None
    ordered = sorted(attempts, key=lambda fact: _as_utc(fact.attempt.dial_started_at))  # type: ignore[arg-type]
    midpoint = len(ordered) // 2
    earlier, later = ordered[:midpoint], ordered[midpoint:]
    if not earlier or not later:
        return None

    def answered_rate(rows: list[AttemptFact]) -> int:
        answered = sum(
            bool(
                row.attempt.answered_at
                or row.attempt.answer_classification in {"live_person", "machine"}
            )
            for row in rows
        )
        return _rate(answered, len(rows)) or 0

    return answered_rate(later) - answered_rate(earlier)


DimensionName = Literal["va", "campaign", "cohort", "list", "dial_mode"]


def _dimension_key(fact: AttemptFact, dimension: DimensionName) -> str:
    if dimension == "va":
        return str(fact.caller.id)
    if dimension == "campaign":
        return str(fact.campaign.id)
    if dimension == "cohort":
        return str(fact.cohort.id) if fact.cohort else "unassigned"
    if dimension == "list":
        return str(fact.batch.id)
    return fact.attempt.dialer_mode


def _cost_dimension_key(fact: CostFact, dimension: DimensionName) -> str | None:
    if dimension == "va":
        return str(fact.cost.worker_user_id) if fact.cost.worker_user_id else None
    if dimension == "campaign":
        return str(fact.campaign.id)
    if dimension == "cohort":
        return str(fact.cohort.id) if fact.cohort else "unassigned"
    if dimension == "list":
        return str(fact.batch.id) if fact.batch else None
    return fact.dial_mode


def _work_dimension_key(fact: WorkFact, dimension: DimensionName) -> str | None:
    if dimension == "va":
        return str(fact.session.caller_user_id)
    if dimension == "campaign":
        return str(fact.campaign.id)
    if dimension == "cohort":
        return str(fact.cohort.id)
    if dimension == "list":
        return None
    return fact.cohort.dialer_mode


def _dimension_scorecards(
    attempts: list[AttemptFact],
    costs: list[CostFact],
    work: list[WorkFact],
    dimension: DimensionName,
    *,
    financials_visible: bool,
    as_of: datetime,
) -> list[ProspectingDialerDimensionScorecardRead]:
    attempts_by_key: dict[str, list[AttemptFact]] = defaultdict(list)
    costs_by_key: dict[str, list[CostFact]] = defaultdict(list)
    work_by_key: dict[str, list[WorkFact]] = defaultdict(list)
    for attempt_fact in attempts:
        attempts_by_key[_dimension_key(attempt_fact, dimension)].append(attempt_fact)
    for cost_fact in costs:
        key = _cost_dimension_key(cost_fact, dimension)
        if key is not None:
            costs_by_key[key].append(cost_fact)
    for work_fact in work:
        key = _work_dimension_key(work_fact, dimension)
        if key is not None:
            work_by_key[key].append(work_fact)
    keys = attempts_by_key.keys() | costs_by_key.keys() | work_by_key.keys()
    result: list[ProspectingDialerDimensionScorecardRead] = []
    for key in sorted(keys):
        scoped_attempts = attempts_by_key.get(key, [])
        scoped_costs = costs_by_key.get(key, [])
        scoped_work = work_by_key.get(key, [])
        identity = _dimension_identity(dimension, key, scoped_attempts, scoped_costs, scoped_work)
        row_sources = {
            *(fact.source for fact in scoped_attempts),
            *(fact.source for fact in scoped_costs),
            *(fact.source for fact in scoped_work),
        }
        row_source = next(iter(row_sources)) if len(row_sources) == 1 else None
        raw_mode: Literal["measured", "unavailable", "mixed"] = (
            "mixed" if len(row_sources) > 1 else _raw_mode(scoped_attempts, [], source=row_source)
        )
        accumulator = _score(
            scoped_attempts,
            [],
            scoped_costs,
            scoped_work,
            [],
            raw_mode=raw_mode,
            as_of=as_of,
        )
        result.append(
            ProspectingDialerDimensionScorecardRead(
                dimension_type=dimension,
                dimension_id=identity[0],
                dimension_name=identity[1],
                external_key=key,
                entry_stage=("dial_attempt" if scoped_attempts else "cost_or_work_record"),
                source=row_source,
                dial_mode=identity[2],
                metrics=_finalize_metrics(
                    accumulator,
                    scoped_attempts,
                    financials_visible=financials_visible,
                ),
            )
        )
    return result


def _dimension_identity(
    dimension: DimensionName,
    key: str,
    attempts: list[AttemptFact],
    costs: list[CostFact],
    work: list[WorkFact],
) -> tuple[UUID | None, str, str | None]:
    attempt = attempts[0] if attempts else None
    cost = costs[0] if costs else None
    session = work[0] if work else None
    resolved_mode = _single_mode(attempts, costs, work)
    if dimension == "va":
        if attempt:
            return attempt.caller.id, attempt.caller.display_name, resolved_mode
        if cost is not None and cost.worker is not None:
            return cost.worker.id, cost.worker.display_name, resolved_mode
        if session is not None:
            return session.caller.id, session.caller.display_name, resolved_mode
        user_id = UUID(key)
        return user_id, f"User {str(user_id)[:8]}", None
    if dimension == "campaign":
        if attempt is not None:
            campaign = attempt.campaign
        elif cost is not None:
            campaign = cost.campaign
        else:
            assert session is not None
            campaign = session.campaign
        return campaign.id, campaign.name, resolved_mode
    if dimension == "cohort":
        if attempt is not None:
            cohort = attempt.cohort
        elif cost is not None:
            cohort = cost.cohort
        else:
            assert session is not None
            cohort = session.cohort
        if cohort is None:
            return None, "Unassigned cohort", resolved_mode
        return cohort.id, cohort.name, resolved_mode
    if dimension == "list":
        batch = attempt.batch if attempt else (cost.batch if cost else None)
        assert batch is not None
        return batch.id, batch.name, batch.dialer_mode
    return None, key.replace("_", " ").title(), key


def _single_mode(
    attempts: list[AttemptFact],
    costs: list[CostFact] | None = None,
    work: list[WorkFact] | None = None,
) -> str | None:
    modes = {
        *(fact.attempt.dialer_mode for fact in attempts if fact.attempt.dialer_mode),
        *(fact.dial_mode for fact in costs or [] if fact.dial_mode),
        *(fact.cohort.dialer_mode for fact in work or [] if fact.cohort.dialer_mode),
    }
    return next(iter(modes)) if len(modes) == 1 else None


def _source_scorecards(
    attempts: list[AttemptFact],
    leads: list[LeadFact],
    costs: list[CostFact],
    work: list[WorkFact],
    spend: list[SpendFact],
    *,
    financials_visible: bool,
    as_of: datetime,
) -> list[ProspectingDialerDimensionScorecardRead]:
    attempts_by_source: dict[str, list[AttemptFact]] = defaultdict(list)
    leads_by_source: dict[str, list[LeadFact]] = defaultdict(list)
    costs_by_source: dict[str, list[CostFact]] = defaultdict(list)
    work_by_source: dict[str, list[WorkFact]] = defaultdict(list)
    spend_by_source: dict[str, list[SpendFact]] = defaultdict(list)
    for attempt_fact in attempts:
        attempts_by_source[attempt_fact.source].append(attempt_fact)
    for lead_fact in leads:
        leads_by_source[lead_fact.source].append(lead_fact)
    for cost_fact in costs:
        costs_by_source[cost_fact.source].append(cost_fact)
    for work_fact in work:
        work_by_source[work_fact.source].append(work_fact)
    for spend_fact in spend:
        spend_by_source[spend_fact.source].append(spend_fact)
    sources = (
        attempts_by_source.keys()
        | leads_by_source.keys()
        | costs_by_source.keys()
        | work_by_source.keys()
        | spend_by_source.keys()
    )
    names = {
        NATIVE_SOURCE: "Stonegate native dialer",
        BATCHDIALER_SOURCE: "BatchDialer",
        PAID_ADS_SOURCE: "Paid advertising",
        "other": "Other lead sources",
    }
    entry_stages = {
        NATIVE_SOURCE: "dial_attempt",
        BATCHDIALER_SOURCE: "crm_handoff_received",
        PAID_ADS_SOURCE: "crm_lead_created",
        "other": "crm_lead_created",
    }
    result: list[ProspectingDialerDimensionScorecardRead] = []
    for source in sorted(sources):
        source_attempts = attempts_by_source.get(source, [])
        source_leads = leads_by_source.get(source, [])
        source_costs = costs_by_source.get(source, [])
        source_work = work_by_source.get(source, [])
        source_spend = spend_by_source.get(source, [])
        accumulator = _score(
            source_attempts,
            source_leads,
            source_costs,
            source_work,
            source_spend,
            raw_mode=_raw_mode(source_attempts, source_leads, source=source),
            as_of=as_of,
        )
        result.append(
            ProspectingDialerDimensionScorecardRead(
                dimension_type="source",
                dimension_id=None,
                dimension_name=names.get(source, source.replace("_", " ").title()),
                external_key=source,
                entry_stage=entry_stages.get(source, "crm_lead_created"),
                source=source,
                dial_mode=_single_mode(source_attempts, source_costs, source_work),
                metrics=_finalize_metrics(
                    accumulator,
                    source_attempts,
                    financials_visible=financials_visible,
                ),
            )
        )
    return result


def _daily_trend(
    filters: AnalyticsFilters,
    attempts: list[AttemptFact],
    leads: list[LeadFact],
    *,
    as_of: datetime,
) -> list[ProspectingDialerDailyPointRead]:
    attempts_by_date: dict[date, list[AttemptFact]] = defaultdict(list)
    leads_by_date: dict[date, list[LeadFact]] = defaultdict(list)
    for attempt_fact in attempts:
        if attempt_fact.attempt.dial_started_at is not None:
            attempts_by_date[_as_utc(attempt_fact.attempt.dial_started_at).date()].append(
                attempt_fact
            )
    for lead_fact in leads:
        leads_by_date[lead_fact.entry_at.date()].append(lead_fact)
    result: list[ProspectingDialerDailyPointRead] = []
    current = filters.date_from
    while current <= filters.date_to:
        day_attempts = attempts_by_date.get(current, [])
        day_leads = leads_by_date.get(current, [])
        raw_mode = _raw_mode(day_attempts, day_leads, source=filters.source)
        accumulator = _score(
            day_attempts,
            day_leads,
            [],
            [],
            [],
            raw_mode=raw_mode,
            as_of=as_of,
        )
        measured = raw_mode == "measured"
        handoff_evidence_available = raw_mode != "unavailable" or bool(accumulator.handoff_ids)
        result.append(
            ProspectingDialerDailyPointRead(
                date=current,
                attempts=len(accumulator.attempt_ids) if measured else None,
                human_conversations=(len(accumulator.human_prospect_ids) if measured else None),
                right_party_contacts=(
                    len(accumulator.right_party_prospect_ids) if measured else None
                ),
                accepted_handoffs=(
                    len(accumulator.accepted_handoff_ids) if handoff_evidence_available else None
                ),
                answer_rate_basis_points=(
                    _rate(
                        len(accumulator.answered_attempt_ids),
                        len(accumulator.attempt_ids),
                    )
                    if measured
                    else None
                ),
                blocked_or_failed_calls=(accumulator.blocked_or_failed_calls if measured else None),
            )
        )
        current += timedelta(days=1)
    return result


def _technical_measurement_gaps(
    db: Session,
    organization_id: UUID,
    observed_at: datetime,
) -> list[str]:
    """Evaluate org-wide durable pilot telemetry independently of report filters/viewer RBAC."""

    start_at = observed_at - timedelta(days=30)
    native_scope_rows = db.execute(
        select(
            ProspectingAttempt.id,
            ProspectCallingBatch.campaign_id,
            ProspectingAttempt.cohort_id,
            ProspectCallingBatch.cohort_id,
        )
        .select_from(ProspectingAttempt)
        .join(
            ProspectCallingBatchEntry,
            ProspectCallingBatchEntry.id == ProspectingAttempt.batch_entry_id,
        )
        .join(
            ProspectCallingBatch,
            ProspectCallingBatch.id
            == ProspectCallingBatchEntry.prospect_calling_batch_id,
        )
        .where(
            ProspectingAttempt.organization_id == organization_id,
            ProspectCallingBatchEntry.organization_id == organization_id,
            ProspectCallingBatch.organization_id == organization_id,
            ProspectingAttempt.dial_started_at >= start_at,
            ProspectingAttempt.dial_started_at <= observed_at,
        )
    ).all()
    attempt_count = len(native_scope_rows)
    if attempt_count == 0:
        return ["No native attempt telemetry was observed in the last 30 days; validate it in D10."]

    native_scopes = {
        (campaign_id, attempt_cohort_id or batch_cohort_id)
        for _attempt_id, campaign_id, attempt_cohort_id, batch_cohort_id in native_scope_rows
    }
    native_campaign_ids = {campaign_id for campaign_id, _cohort_id in native_scopes}
    native_work_rows = db.scalars(
        select(ProspectingWorkSession).where(
            ProspectingWorkSession.organization_id == organization_id,
            ProspectingWorkSession.campaign_id.in_(native_campaign_ids),
            ProspectingWorkSession.work_date >= start_at.date(),
            ProspectingWorkSession.work_date <= observed_at.date(),
            ProspectingWorkSession.source == "manual",
        )
    ).all()
    work_count = sum(
        (work.campaign_id, work.cohort_id) in native_scopes
        or (work.campaign_id, None) in native_scopes
        for work in native_work_rows
    )
    leg_count = int(
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .select_from(ProspectingDialLeg)
            .join(ProspectingAttempt, ProspectingAttempt.id == ProspectingDialLeg.attempt_id)
            .where(
                ProspectingDialLeg.organization_id == organization_id,
                ProspectingAttempt.organization_id == organization_id,
                ProspectingAttempt.dial_started_at >= start_at,
                ProspectingAttempt.dial_started_at <= observed_at,
            )
        )
        or 0
    )
    actual_cost_count = int(
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .select_from(ProspectingDialLeg)
            .join(ProspectingAttempt, ProspectingAttempt.id == ProspectingDialLeg.attempt_id)
            .where(
                ProspectingDialLeg.organization_id == organization_id,
                ProspectingDialLeg.actual_cost_cents.is_not(None),
                ProspectingAttempt.organization_id == organization_id,
                ProspectingAttempt.dial_started_at >= start_at,
                ProspectingAttempt.dial_started_at <= observed_at,
            )
        )
        or 0
    )
    voice_fallback_rows = db.scalars(
        select(CampaignCost).where(
            CampaignCost.organization_id == organization_id,
            CampaignCost.campaign_id.in_(native_campaign_ids),
            CampaignCost.category == "voice_usage",
            CampaignCost.incurred_on >= start_at.date(),
            CampaignCost.incurred_on <= observed_at.date(),
        )
    ).all()
    voice_fallback_count = sum(
        (
            (cost.campaign_id, cost.cohort_id) in native_scopes
            or (cost.campaign_id, None) in native_scopes
            or cost.cohort_id is None
        )
        and "batchdialer" not in (cost.vendor_name or "").strip().lower()
        for cost in voice_fallback_rows
    )
    gaps: list[str] = []
    if not work_count:
        gaps.append("Recent native attempts have no durable paid-time work session.")
    if not leg_count:
        gaps.append("Recent native attempts have no durable provider dial-leg telemetry.")
    elif actual_cost_count < leg_count and not voice_fallback_count:
        gaps.append(
            "Recent dial legs have incomplete actual cost and no voice_usage ledger fallback."
        )
    return gaps


def _launch_readiness(
    db: Session,
    organization_id: UUID,
    settings: Settings,
    observed_at: datetime,
) -> ProspectingDialerLaunchReadinessRead:
    checks: list[ProspectingDialerReadinessCheckRead] = []

    def add(key: str, label: str, passed: bool, detail: str, *, warning: bool = False) -> None:
        checks.append(
            ProspectingDialerReadinessCheckRead(
                key=key,
                label=label,
                status="pass" if passed else ("warning" if warning else "block"),
                detail=detail,
            )
        )

    organization = db.scalar(
        select(Organization).where(
            Organization.id == organization_id,
            Organization.is_active.is_(True),
        )
    )
    feature_ready = bool(
        organization
        and organization.prospecting_dialer_enabled
        and settings.prospecting_native_dialer_enabled
    )
    add(
        "feature_switches",
        "Company and runtime switches",
        feature_ready,
        (
            "The native dialer is enabled at both company and runtime level."
            if feature_ready
            else "Enable both the company switch and PROSPECTING_NATIVE_DIALER_ENABLED."
        ),
    )

    profiles = db.scalars(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == organization_id,
            ProspectingDialerProfile.status == "active",
        )
    ).all()
    lines = db.scalars(
        select(VoiceLine).where(
            VoiceLine.organization_id == organization_id,
            VoiceLine.status == "active",
            VoiceLine.department_key == "acquisitions",
            VoiceLine.purpose_key == PROSPECTING_LINE_PURPOSE,
        )
    ).all()
    line_by_id = {line.id: line for line in lines}
    profile_user_ids = {profile.user_id for profile in profiles}
    profile_users = db.scalars(
        select(User).where(
            User.organization_id == organization_id,
            User.id.in_(profile_user_ids),
        )
    ).all()
    profile_user_by_id = {user.id: user for user in profile_users}
    assigned_line_ids = [
        profile.voice_line_id for profile in profiles if profile.voice_line_id is not None
    ]
    invalid_profiles = [
        profile
        for profile in profiles
        if (
            profile.voice_line_id not in line_by_id
            or not _is_e164(line_by_id[profile.voice_line_id].phone_number)
            or line_by_id[profile.voice_line_id].assigned_user_id != profile.user_id
            or profile.user_id not in profile_user_by_id
            or not profile_user_by_id[profile.user_id].is_active
            or not profile_user_by_id[profile.user_id].calling_enabled
        )
    ]
    lines_ready = bool(
        profiles and not invalid_profiles and len(assigned_line_ids) == len(set(assigned_line_ids))
    )
    add(
        "assigned_prospecting_lines",
        "Dedicated assigned prospecting line",
        lines_ready,
        (
            f"{len(profiles)} active profile(s) have a unique, user-owned E.164 "
            "prospecting-outbound line and an active calling-enabled user."
            if lines_ready
            else "Every active VA profile needs a dedicated active "
            "acquisitions/prospecting-outbound E.164 line."
        ),
    )

    add(
        "browser_voice_token",
        "Browser voice token",
        settings.twilio_browser_voice_configured,
        (
            "Twilio browser voice credentials and TwiML application are configured."
            if settings.twilio_browser_voice_configured
            else "Missing: " + ", ".join(settings.twilio_browser_voice_configuration_blockers)
        ),
    )
    add(
        "signed_callbacks",
        "Signed callback and routing controls",
        settings.twilio_voice_configured,
        (
            "Voice webhook base URL and signature validation are configured."
            if settings.twilio_voice_configured
            else "Missing: " + ", ".join(settings.twilio_voice_configuration_blockers)
        ),
    )
    add(
        "call_recording",
        "Call recording",
        settings.twilio_voice_recording_configured,
        (
            "Recording and retention are configured."
            if settings.twilio_voice_recording_configured
            else "Enable voice recording and a positive retention period before the pilot."
        ),
    )

    campaigns = db.scalars(
        select(Campaign).where(
            Campaign.organization_id == organization_id,
            Campaign.status == "active",
            Campaign.prospecting_dialer_enabled.is_(True),
        )
    ).all()
    caps_ready = bool(
        organization
        and organization.prospecting_dialer_max_concurrent_legs == 1
        and settings.prospecting_native_dialer_effective_line_cap == 1
        and settings.prospecting_native_dialer_implemented_line_cap == 1
        and profiles
        and all(
            profile.default_line_count == 1 and profile.max_line_count == 1 for profile in profiles
        )
        and lines_ready
        and all(
            line_by_id.get(line_id) is not None
            and line_by_id[line_id].prospecting_dialer_max_concurrent_legs == 1
            for line_id in assigned_line_ids
        )
        and campaigns
        and all(campaign.prospecting_dialer_max_concurrent_legs == 1 for campaign in campaigns)
    )
    add(
        "single_line_caps",
        "One-line concurrency caps",
        caps_ready,
        (
            "Runtime, company, VA, campaign, and voice-line caps are all exactly one."
            if caps_ready
            else "D9 permits only one-line calling; set every effective concurrency cap to one."
        ),
    )
    daily_caps_ready = bool(
        profiles
        and all(
            profile.daily_dial_limit is not None
            and profile.daily_spend_limit_cents is not None
            and profile.daily_dial_limit > 0
            and profile.daily_spend_limit_cents > 0
            for profile in profiles
        )
    )
    add(
        "daily_caps",
        "Daily dial and spend caps",
        daily_caps_ready,
        (
            "Every active profile has durable dial and spend caps."
            if daily_caps_ready
            else "Set both a daily dial limit and daily spend limit for every active VA profile."
        ),
    )

    active_sessions = db.scalars(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == organization_id,
            ProspectingDialSession.ended_at.is_(None),
        )
    ).all()
    stale_before = observed_at - timedelta(
        seconds=settings.prospecting_native_dialer_stale_after_seconds
    )
    stale_sessions = [
        session for session in active_sessions if _as_utc(session.heartbeat_at) < stale_before
    ]
    session_ids = {session.id for session in active_sessions}
    active_legs = db.scalars(
        select(ProspectingDialLeg).where(
            ProspectingDialLeg.organization_id == organization_id,
            ProspectingDialLeg.completed_at.is_(None),
        )
    ).all()
    orphan_legs = [leg for leg in active_legs if leg.dial_session_id not in session_ids]
    legs_by_session: dict[UUID, int] = defaultdict(int)
    legs_by_line: dict[UUID, int] = defaultdict(int)
    for leg in active_legs:
        legs_by_session[leg.dial_session_id] += 1
        if leg.voice_line_id is not None:
            legs_by_line[leg.voice_line_id] += 1
    multi_leg_sessions = sum(count > 1 for count in legs_by_session.values())
    multi_leg_lines = sum(count > 1 for count in legs_by_line.values())
    organization_over_live_leg_cap = len(active_legs) > 1
    over_cap_sessions = [
        session for session in active_sessions if session.effective_line_count != 1
    ]
    sessions_ready = bool(
        not stale_sessions
        and not orphan_legs
        and not multi_leg_sessions
        and not multi_leg_lines
        and not organization_over_live_leg_cap
        and not over_cap_sessions
    )
    add(
        "session_recovery",
        "Session and leg recovery",
        sessions_ready,
        (
            "No stale sessions, orphaned legs, or one-line concurrency violations were observed."
            if sessions_ready
            else f"Recover {len(stale_sessions)} stale session(s) and "
            f"{len(orphan_legs)} orphaned leg(s); resolve {multi_leg_sessions} "
            f"multi-leg session(s), {multi_leg_lines} shared active line(s), and "
            f"{len(over_cap_sessions)} over-cap session(s). The organization currently has "
            f"{len(active_legs)} live leg(s); the D9 cap is one."
        ),
    )

    worker = get_worker_readiness(db, settings)
    worker_ready = worker.status == "healthy" or (
        not worker.required and worker.status == "not_required"
    )
    add(
        "worker_health",
        "Communications worker",
        worker_ready,
        f"Worker status is {worker.status}; heartbeat {worker.heartbeat_at or 'not observed'}.",
        warning=not worker.required,
    )
    add(
        "hard_safety_gates",
        "Server-side safety gates",
        True,
        "DNC, calling-window, caller-ID, atomic reservation, idempotency, and "
        "connected-seller gates remain server enforced.",
    )
    add(
        "batchdialer_fallback",
        "BatchDialer fallback",
        settings.zapier_batchdialer_configured,
        (
            "The existing BatchDialer handoff remains configured as the rollback path."
            if settings.zapier_batchdialer_configured
            else "Fallback warning: "
            + ", ".join(settings.zapier_batchdialer_configuration_blockers)
        ),
        warning=True,
    )
    measurement_gaps = _technical_measurement_gaps(db, organization_id, observed_at)
    add(
        "measurement_coverage",
        "Technical measurement prerequisites",
        not measurement_gaps,
        (
            "Recent native activity has durable attempts, paid-time records, and cost telemetry."
            if not measurement_gaps
            else " ".join(measurement_gaps)
        ),
        warning=True,
    )
    add(
        "d10_acceptance",
        "D10 pilot acceptance",
        False,
        "D9 readiness never authorizes broad production use; D10 controlled-pilot "
        "acceptance is still required.",
        warning=True,
    )

    blockers = [check.detail for check in checks if check.status == "block"]
    warnings = [check.detail for check in checks if check.status == "warning"]
    controlled_pilot_ready = not blockers
    return ProspectingDialerLaunchReadinessRead(
        status=(
            "blocked"
            if blockers
            else (
                "needs_review"
                if any(
                    check.key != "d10_acceptance" for check in checks if check.status == "warning"
                )
                else "ready_for_controlled_pilot"
            )
        ),
        controlled_pilot_ready=controlled_pilot_ready,
        observed_at=observed_at,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
    )


def _is_e164(value: str | None) -> bool:
    normalized = (value or "").strip()
    return normalized.startswith("+") and normalized[1:].isdigit() and 8 <= len(normalized) <= 16


def _metric_definitions() -> list[ProspectingMetricDefinitionRead]:
    definitions: list[ProspectingMetricDefinitionRead] = []

    def add(
        key: str,
        label: str,
        definition: str,
        sources: list[str],
        timestamp: str,
        unavailable: str | None = None,
    ) -> None:
        definitions.append(
            ProspectingMetricDefinitionRead(
                key=key,
                label=label,
                definition=definition,
                source_records=sources,
                attribution_timestamp=timestamp,
                unavailable_when=unavailable,
            )
        )

    native_sources = ["ProspectingAttempt", "ProspectingDialLeg", "CallRecord"]
    native_time = "ProspectingAttempt.dial_started_at"
    native_unavailable = "Unavailable outside native Stonegate dialer activity cohorts."
    origin_time = "Attributed origin activity timestamp"

    add(
        "entered_leads",
        "Entered leads",
        "Unique leads entering the row's activity cohort in the UTC window. Source rows "
        "may overlap and must not be added together.",
        ["ProspectHandoff", "Lead", "AttributionTouch"],
        "Native handoff submitted_at, Batch handoff touch, or canonical Lead.created_at",
    )
    add(
        "attempts",
        "Dial attempts",
        "Unique native attempts with a durable dial start in the UTC activity window.",
        ["ProspectingAttempt"],
        native_time,
        native_unavailable,
    )
    add(
        "answered_calls",
        "Answered calls",
        "Unique native attempts with answered_at or a durable human or machine classification.",
        ["ProspectingAttempt"],
        native_time,
        native_unavailable,
    )
    add(
        "human_conversations",
        "Human conversations",
        "Unique prospects classified live_person; repeat attempts do not inflate the count.",
        ["ProspectingAttempt"],
        native_time,
        native_unavailable,
    )
    add(
        "conversations_over_60_seconds",
        "Conversations over 60 seconds",
        "Unique live-person prospects whose durable call duration is strictly over 60 seconds.",
        ["ProspectingAttempt", "CallRecord"],
        native_time,
        native_unavailable,
    )
    add(
        "right_party_contacts",
        "Right-party contacts",
        "Unique live-person prospects with durable right-party identity evidence.",
        ["ProspectingAttempt", "ProspectingQualificationResponse"],
        native_time,
        native_unavailable,
    )
    add(
        "qualified_sellers",
        "Qualified sellers",
        "Unique prospects retaining the complete accepted warm-lead evidence contract.",
        ["ProspectingAttempt", "ProspectingQualificationResponse"],
        native_time,
        native_unavailable,
    )
    add(
        "appointments_set",
        "Appointments set",
        "Unique linked appointments created after the attributed origin and by report as-of.",
        ["Appointment"],
        origin_time,
    )
    add(
        "appointments_held",
        "Appointments held",
        "Unique counted appointments with completed or held status by report as-of.",
        ["Appointment"],
        origin_time,
        "Partial until every counted appointment has a final outcome.",
    )
    add(
        "submitted_handoffs",
        "Submitted handoffs",
        "Unique native warm handoffs submitted to acquisitions plus accepted Batch CRM handoffs.",
        ["ProspectHandoff", "Lead", "AttributionTouch"],
        "Handoff timestamp",
        "Not applicable to paid-ad and other non-dialer activity cohorts.",
    )
    add(
        "accepted_handoffs",
        "Accepted handoffs",
        "Unique acquisitions handoffs retaining complete warm-lead evidence; Batch CRM handoffs "
        "are accepted by contract.",
        ["ProspectHandoff", "ProspectingAttempt", "AttributionTouch"],
        "Handoff timestamp",
        "Not applicable to paid-ad and other non-dialer activity cohorts.",
    )
    add(
        "signed_contracts",
        "Signed contracts",
        "Unique linked transactions executed after the origin and by report as-of.",
        ["Transaction"],
        origin_time,
    )
    add(
        "closed_assignments",
        "Closed assignments",
        "Unique linked funded or closed transactions with assignment disposition strategy.",
        ["Transaction", "DispositionCase"],
        origin_time,
        "Novation, listing, and other strategies are excluded.",
    )

    add(
        "paid_minutes",
        "Paid minutes",
        "Sum of persisted paid minutes for attributed native or Batch work sessions.",
        ["ProspectingWorkSession"],
        "ProspectingWorkSession.work_date",
        "Unknown when paid time applies without a work record; not applicable to non-dialer rows.",
    )
    add(
        "productive_calling_minutes",
        "Productive calling minutes",
        "Sum of persisted productive calling minutes for attributed work sessions.",
        ["ProspectingWorkSession"],
        "ProspectingWorkSession.work_date",
        "Uses the same availability rules as paid minutes.",
    )
    add(
        "labor_cost_cents",
        "Labor cost",
        "Sum of attributed va_labor ledger records.",
        ["CampaignCost"],
        "CampaignCost.incurred_on",
        "Unknown when dialer labor applies without a ledger; hidden without financials:view.",
    )
    add(
        "provider_cost_cents",
        "Provider cost",
        "Actual dial-leg cost plus fixed provider cost; voice_usage ledger is the fallback. "
        "Reserved cost is never reported.",
        ["ProspectingDialLeg", "CampaignCost"],
        "Attempt dial_started_at and CampaignCost.incurred_on",
        "Unknown without complete actual leg cost or voice fallback; hidden without "
        "financials:view.",
    )
    add(
        "list_cost_cents",
        "List cost",
        "Sum of attributed list_purchase ledger records.",
        ["CampaignCost"],
        "CampaignCost.incurred_on",
        "Unknown for active dialer cohorts without a list ledger; hidden without "
        "financials:view.",
    )
    add(
        "other_cost_cents",
        "Other cost",
        "Other attributed ledger cost plus paid marketing spend from complete UTC months.",
        ["CampaignCost", "MarketingSpend"],
        "CampaignCost.incurred_on or MarketingSpend.spend_month_at",
        "Partial for an incomplete paid-spend month; hidden without financials:view.",
    )
    add(
        "total_cost_cents",
        "Total attributed cost",
        "Labor, provider, list, and other attributed cost with complete-month paid spend.",
        ["CampaignCost", "ProspectingWorkSession", "MarketingSpend"],
        "Cost ledger date, work date, or spend month",
        "Unknown with incomplete dialer cost coverage and partial for incomplete paid-spend "
        "months; hidden without financials:view.",
    )
    add(
        "gross_revenue_cents",
        "Collected revenue",
        "Collected revenue linked to counted closed assignment transactions; projected gross "
        "is excluded.",
        ["RevenueRecord", "Transaction", "DispositionCase"],
        origin_time,
        "Null until every counted close has linked collected revenue; hidden without "
        "financials:view.",
    )
    add(
        "contribution_profit_cents",
        "Contribution profit",
        "Approved reconciliation company profit for counted closed assignment transactions.",
        ["DealReconciliation", "Transaction", "DispositionCase"],
        origin_time,
        "Null until every counted close has an approved reconciliation; hidden without "
        "financials:view.",
    )

    efficiency = [
        (
            "attempts_per_paid_hour_x100",
            "Attempts per paid hour",
            "Native attempts divided by paid hours, stored at two-decimal precision.",
            ["ProspectingAttempt", "ProspectingWorkSession"],
            "Unknown when native attempts exist without positive paid minutes.",
        ),
        (
            "human_conversations_per_paid_hour_x100",
            "Human conversations per paid hour",
            "Unique live-person prospects divided by paid hours, at two-decimal precision.",
            ["ProspectingAttempt", "ProspectingWorkSession"],
            "Unknown when native attempts exist without positive paid minutes.",
        ),
        (
            "profit_per_paid_hour_cents",
            "Profit per paid hour",
            "Approved contribution profit divided by attributed paid hours.",
            ["DealReconciliation", "ProspectingWorkSession"],
            "Unknown without approved profit or positive paid minutes; hidden without "
            "financials:view.",
        ),
        (
            "cost_per_qualified_seller_cents",
            "Cost per qualified seller",
            "Total attributed cost divided by unique qualified sellers.",
            ["CampaignCost", "MarketingSpend", "ProspectingAttempt"],
            "Not applicable without qualified sellers; hidden without financials:view.",
        ),
        (
            "cost_per_contract_cents",
            "Cost per contract",
            "Total attributed cost divided by unique signed contracts.",
            ["CampaignCost", "MarketingSpend", "Transaction"],
            "Not applicable without signed contracts; hidden without financials:view.",
        ),
    ]
    for key, label, definition, sources, unavailable in efficiency:
        add(key, label, definition, sources, origin_time, unavailable)

    rates = [
        (
            "human_contact_rate_basis_points",
            "Human contact rate",
            "Unique live-person prospects divided by native attempts.",
            ["ProspectingAttempt"],
            "Unavailable outside native rows; not applicable with zero attempts.",
        ),
        (
            "right_party_contact_rate_basis_points",
            "Right-party contact rate",
            "Unique right-party contacts divided by unique live-person prospects.",
            ["ProspectingAttempt", "ProspectingQualificationResponse"],
            "Unavailable outside native rows; not applicable with zero human contacts.",
        ),
        (
            "qualified_seller_rate_basis_points",
            "Qualified seller rate",
            "Unique qualified sellers divided by unique right-party contacts.",
            ["ProspectingAttempt", "ProspectingQualificationResponse"],
            "Unavailable outside native rows; not applicable with zero right parties.",
        ),
        (
            "accepted_handoff_rate_basis_points",
            "Accepted handoff rate",
            "Accepted acquisitions handoffs divided by submitted handoffs.",
            ["ProspectHandoff", "AttributionTouch"],
            "Not applicable with zero submitted handoffs.",
        ),
        (
            "appointment_held_rate_basis_points",
            "Appointment held rate",
            "Held or completed appointments divided by appointments set.",
            ["Appointment"],
            "Partial until every counted appointment has a final outcome.",
        ),
        (
            "contract_rate_basis_points",
            "Contract rate",
            "Unique signed contracts divided by unique entered leads.",
            ["Lead", "ProspectHandoff", "Transaction"],
            "Not applicable with zero entered leads.",
        ),
        (
            "close_rate_basis_points",
            "Assignment close rate",
            "Unique closed assignments divided by unique signed contracts.",
            ["Transaction", "DispositionCase"],
            "Not applicable with zero signed contracts.",
        ),
    ]
    for key, label, definition, sources, unavailable in rates:
        add(key, label, definition, sources, origin_time, unavailable)

    add(
        "short_calls",
        "Short calls",
        "Answered live-person native calls lasting 15 seconds or less.",
        native_sources,
        native_time,
        native_unavailable,
    )
    add(
        "silent_or_dead_air_calls",
        "Silent or dead-air calls",
        "Native calls classified by durable dead-air detector telemetry.",
        ["ProspectingAttempt.measurement_metadata"],
        native_time,
        "Currently unknown with native activity because detector telemetry is not persisted.",
    )
    add(
        "blocked_or_failed_calls",
        "Blocked or failed calls",
        "Native dial legs ending in a failed state or carrying a provider error.",
        ["ProspectingDialLeg"],
        native_time,
        native_unavailable,
    )
    add(
        "no_answer_calls",
        "No-answer calls",
        "Native dial legs with a no-answer status or terminal result.",
        ["ProspectingDialLeg"],
        native_time,
        native_unavailable,
    )
    add(
        "voicemail_calls",
        "Voicemail calls",
        "Native attempts completed as voicemail, answering machine, or left voicemail.",
        ["ProspectingAttempt"],
        native_time,
        native_unavailable,
    )
    add(
        "duplicate_call_incidents",
        "Duplicate-call incidents",
        "Calls flagged by durable duplicate-call safety telemetry.",
        ["ProspectingAttempt.measurement_metadata"],
        native_time,
        "Currently unknown with native activity because detector telemetry is not persisted.",
    )
    add(
        "seller_complaints",
        "Seller complaints",
        "Native quality records carrying a durable seller-complaint compliance flag.",
        ["ProspectingCallQualityReview"],
        native_time,
        native_unavailable,
    )
    add(
        "dnc_requests",
        "DNC requests",
        "Native attempts completed with a do-not-call outcome.",
        ["ProspectingAttempt"],
        native_time,
        native_unavailable,
    )
    add(
        "abandoned_calls",
        "Abandoned calls",
        "Answered multi-line calls not connected to an available agent.",
        ["ProspectingDialLeg"],
        native_time,
        "Not applicable while production remains one-line only.",
    )
    add(
        "average_connection_time_seconds",
        "Average connection time",
        "Average seconds from dial-leg dialing_at to connected_at.",
        ["ProspectingDialLeg"],
        native_time,
        "Unknown when native attempts exist without a connection-time sample.",
    )
    add(
        "number_reputation_score",
        "Number reputation score",
        "Average validated 0-100 reputation value persisted in attempt measurement metadata.",
        ["ProspectingAttempt.measurement_metadata"],
        native_time,
        "Unknown or partial when native attempts lack reputation telemetry.",
    )
    add(
        "answer_rate_trend_basis_points",
        "Answer-rate trend",
        "Later-half native answer rate minus earlier-half answer rate in basis points.",
        ["ProspectingAttempt"],
        native_time,
        "Not applicable with fewer than two native attempts.",
    )

    coverage = [
        (
            "coverage.raw_attempts_basis_points",
            "Raw-attempt coverage",
            "Share backed by durable native attempt telemetry.",
            ["ProspectingAttempt"],
            "Null for mixed or non-native source rows.",
        ),
        (
            "coverage.paid_hours_basis_points",
            "Paid-hours coverage",
            "Whether applicable calling work has persisted paid-time records.",
            ["ProspectingWorkSession"],
            "Null when paid time is not applicable.",
        ),
        (
            "coverage.provider_cost_basis_points",
            "Provider-cost coverage",
            "Share of dial legs with actual cost, or complete voice-ledger fallback coverage.",
            ["ProspectingDialLeg", "CampaignCost"],
            "Null when provider cost is not applicable or hidden.",
        ),
        (
            "coverage.appointment_outcomes_basis_points",
            "Appointment-outcome coverage",
            "Share of appointments with a final held, cancelled, or no-show outcome.",
            ["Appointment"],
            "Null with zero appointments.",
        ),
        (
            "coverage.profit_basis_points",
            "Profit coverage",
            "Share of closed assignments with an approved reconciliation.",
            ["DealReconciliation", "Transaction"],
            "Null with zero closes or when financial data is hidden.",
        ),
        (
            "coverage.reputation_basis_points",
            "Reputation coverage",
            "Share of native attempts with validated number-reputation telemetry.",
            ["ProspectingAttempt.measurement_metadata"],
            "Null with zero native attempts.",
        ),
    ]
    for key, label, definition, sources, unavailable in coverage:
        add(key, label, definition, sources, origin_time, unavailable)
    return definitions
