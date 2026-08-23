from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    Appointment,
    AuditEvent,
    BatchDialerAgentIdentity,
    BatchDialerCallFact,
    BatchDialerSyncCheckpoint,
    Transaction,
    User,
)
from app.schemas.prospecting import (
    BatchDialerAgentMappingListRead,
    BatchDialerAgentMappingRead,
    BatchDialerAgentMappingUserRead,
    BatchDialerCampaignScorecardRead,
    BatchDialerVaDailyActivityRead,
    BatchDialerVaHourlyActivityRead,
    BatchDialerVaMetricsRead,
    BatchDialerVaPerformanceRead,
    BatchDialerVaScorecardRead,
)

MAX_REPORT_DAYS = 366
MAX_CALL_FACTS = 50_000
ACTIVITY_GAP = timedelta(minutes=15)
HELD_APPOINTMENT_STATUSES = {"completed", "held"}
_NO_HUMAN_DISPOSITIONS = (
    "no answer",
    "voicemail",
    "answering machine",
    "busy",
    "disconnected",
    "unavailable",
    "failed",
)
_HUMAN_DISPOSITIONS = (
    "qualified seller",
    "appointment",
    "not interested",
    "do not call",
    "wrong number",
    "call back",
    "callback",
    "successful sale",
)


@dataclass(frozen=True)
class _Downstream:
    appointment_ids: frozenset[UUID] = frozenset()
    held_appointment_ids: frozenset[UUID] = frozenset()
    signed_transaction_ids: frozenset[UUID] = frozenset()
    closed_transaction_ids: frozenset[UUID] = frozenset()


@dataclass
class _Accumulator:
    call_ids: set[UUID] = field(default_factory=set)
    contact_keys: set[str] = field(default_factory=set)
    identified_contact_call_ids: set[UUID] = field(default_factory=set)
    human_call_ids: set[UUID] = field(default_factory=set)
    qualified_candidate_ids: set[UUID] = field(default_factory=set)
    evidence_accepted_candidate_ids: set[UUID] = field(default_factory=set)
    verified_handoff_ids: set[UUID] = field(default_factory=set)
    false_positive_ids: set[UUID] = field(default_factory=set)
    provider_appointment_ids: set[UUID] = field(default_factory=set)
    appointment_ids: set[UUID] = field(default_factory=set)
    appointment_entered_handoff_ids: set[UUID] = field(default_factory=set)
    held_appointment_ids: set[UUID] = field(default_factory=set)
    signed_transaction_ids: set[UUID] = field(default_factory=set)
    closed_transaction_ids: set[UUID] = field(default_factory=set)
    dnc_ids: set[UUID] = field(default_factory=set)
    not_interested_ids: set[UUID] = field(default_factory=set)
    voicemail_ids: set[UUID] = field(default_factory=set)
    no_answer_ids: set[UUID] = field(default_factory=set)
    recorded_duration_call_ids: set[UUID] = field(default_factory=set)
    recorded_call_seconds: int = 0
    first_call_at: datetime | None = None
    last_call_at: datetime | None = None
    intervals_by_agent: dict[str, list[tuple[datetime, datetime]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, fact: BatchDialerCallFact, downstream: _Downstream) -> None:
        self.call_ids.add(fact.id)
        if fact.provider_contact_id:
            self.contact_keys.add(fact.provider_contact_id)
            self.identified_contact_call_ids.add(fact.id)
        duration = max(int(fact.duration_seconds or 0), 0)
        if fact.duration_seconds is not None:
            self.recorded_duration_call_ids.add(fact.id)
            self.recorded_call_seconds += duration
        occurred_at = _fact_occurred_at(fact)
        ended_at = _as_utc(fact.ended_at) if fact.ended_at is not None else None
        if ended_at is None or ended_at < occurred_at:
            ended_at = occurred_at + timedelta(seconds=duration)
        agent_key = fact.provider_agent_id or "unmapped-provider-agent"
        self.intervals_by_agent[agent_key].append((occurred_at, ended_at))
        self.first_call_at = (
            min(self.first_call_at, occurred_at) if self.first_call_at else occurred_at
        )
        self.last_call_at = (
            max(self.last_call_at, occurred_at) if self.last_call_at else occurred_at
        )

        raw = _normalized_label(fact.raw_disposition)
        if _is_human_contact(fact, raw):
            self.human_call_ids.add(fact.id)
        if fact.disposition_classification in {"interested", "appointment_set"}:
            self.qualified_candidate_ids.add(fact.id)
        if fact.final_qualification_status == "accepted" and fact.lead_id is not None:
            self.evidence_accepted_candidate_ids.add(fact.id)
        if (
            fact.final_qualification_status == "accepted"
            and fact.lead_id is not None
            and fact.lead_created_by_event
        ):
            self.verified_handoff_ids.add(fact.id)
        if (
            fact.disposition_classification in {"interested", "appointment_set"}
            and fact.lead_id is None
            and (
                fact.final_qualification_status == "rejected_by_human"
                or (
                    fact.final_outcome == "needs_review"
                    and fact.final_processing_status in {"quarantined", "exhausted"}
                )
            )
        ):
            self.false_positive_ids.add(fact.id)
        if (
            fact.final_outcome == "appointment_set"
            and fact.final_qualification_status == "accepted"
        ):
            self.provider_appointment_ids.add(fact.id)
        if "do not call" in raw:
            self.dnc_ids.add(fact.id)
        if "not interested" in raw:
            self.not_interested_ids.add(fact.id)
        if "voicemail" in raw or "answering machine" in raw or fact.is_voicemail:
            self.voicemail_ids.add(fact.id)
        if "no answer" in raw:
            self.no_answer_ids.add(fact.id)

        self.appointment_ids.update(downstream.appointment_ids)
        if downstream.appointment_ids and fact.id in self.verified_handoff_ids:
            self.appointment_entered_handoff_ids.add(fact.id)
        self.held_appointment_ids.update(downstream.held_appointment_ids)
        self.signed_transaction_ids.update(downstream.signed_transaction_ids)
        self.closed_transaction_ids.update(downstream.closed_transaction_ids)

    def read(self) -> BatchDialerVaMetricsRead:
        calls = len(self.call_ids)
        identified_contact_calls = len(self.identified_contact_call_ids)
        candidates = len(self.qualified_candidate_ids)
        accepted_candidates = len(self.evidence_accepted_candidate_ids)
        verified = len(self.verified_handoff_ids)
        false_positives = len(self.false_positive_ids)
        duration_calls = len(self.recorded_duration_call_ids)
        return BatchDialerVaMetricsRead(
            calls=calls,
            unique_contacts=len(self.contact_keys),
            identified_contact_calls=identified_contact_calls,
            identified_contact_coverage_basis_points=_rate(
                identified_contact_calls,
                calls,
            ),
            human_contacts=len(self.human_call_ids),
            recorded_duration_calls=duration_calls,
            recorded_duration_coverage_basis_points=_rate(duration_calls, calls),
            recorded_call_seconds=(self.recorded_call_seconds if duration_calls else None),
            average_recorded_call_seconds=(
                round(self.recorded_call_seconds / duration_calls) if duration_calls else None
            ),
            qualified_candidates=candidates,
            evidence_accepted_candidates=accepted_candidates,
            verified_handoffs=verified,
            qualification_false_positives=false_positives,
            appointments_set=len(self.provider_appointment_ids),
            appointments_entered=len(self.appointment_ids),
            handoffs_with_appointment_entered=len(self.appointment_entered_handoff_ids),
            appointments_held=len(self.held_appointment_ids),
            signed_contracts=len(self.signed_transaction_ids),
            closed_transactions=len(self.closed_transaction_ids),
            dnc=len(self.dnc_ids),
            not_interested=len(self.not_interested_ids),
            voicemails=len(self.voicemail_ids),
            no_answers=len(self.no_answer_ids),
            first_call_at=self.first_call_at,
            last_call_at=self.last_call_at,
            inferred_calling_minutes=_inferred_activity_minutes(self.intervals_by_agent),
            human_contact_rate_basis_points=_rate(len(self.human_call_ids), calls),
            evidence_acceptance_rate_basis_points=_rate(accepted_candidates, candidates),
            false_positive_rate_basis_points=_rate(false_positives, candidates),
            appointments_entered_rate_basis_points=_rate(
                len(self.appointment_entered_handoff_ids),
                verified,
            ),
        )


def get_batchdialer_va_performance(
    db: Session,
    principal: Principal,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> BatchDialerVaPerformanceRead:
    _require_manager(principal)
    settings = get_settings()
    timezone = ZoneInfo(settings.batchdialer_account_timezone)
    now = datetime.now(UTC)
    local_today = now.astimezone(timezone).date()
    end_date = date_to or local_today
    if date_from is not None:
        start_date = date_from
    elif end_date <= date.min + timedelta(days=6):
        start_date = date.min
    else:
        start_date = end_date - timedelta(days=6)
    if start_date > end_date:
        raise ValueError("date_from must be on or before date_to.")
    if (end_date - start_date).days + 1 > MAX_REPORT_DAYS:
        raise ValueError(f"BatchDialer VA reports cannot exceed {MAX_REPORT_DAYS} days.")
    start_at = datetime.combine(start_date, time.min, timezone).astimezone(UTC)
    if end_date == date.max:
        raise ValueError("date_to is outside the supported reporting range.")
    end_at = datetime.combine(end_date + timedelta(days=1), time.min, timezone).astimezone(UTC)
    activity_at = func.coalesce(
        BatchDialerCallFact.started_at,
        BatchDialerCallFact.occurred_at,
        BatchDialerCallFact.received_at,
    )
    earliest_archived_call_at = db.scalar(
        select(func.min(activity_at)).where(
            BatchDialerCallFact.organization_id == principal.organization_id,
            BatchDialerCallFact.direction == "outbound",
        )
    )
    earliest_archived_call_at = (
        _as_utc(earliest_archived_call_at)
        if earliest_archived_call_at is not None
        else None
    )
    provider_checkpoint = db.scalar(
        select(BatchDialerSyncCheckpoint).where(
            BatchDialerSyncCheckpoint.organization_id == principal.organization_id,
            BatchDialerSyncCheckpoint.stream == "cdrs",
        )
    )
    provider_sync_status, provider_sync_freshness = _provider_sync_health(
        provider_checkpoint,
        now=now,
        poll_interval_seconds=settings.batchdialer_poll_seconds,
    )
    provider_sync_last_success_at = (
        _as_utc(provider_checkpoint.last_success_at)
        if provider_checkpoint is not None and provider_checkpoint.last_success_at is not None
        else None
    )
    provider_sync_error_present = bool(
        provider_checkpoint is not None and provider_checkpoint.last_error
    )
    statement = (
        select(BatchDialerCallFact)
        .where(
            BatchDialerCallFact.organization_id == principal.organization_id,
            BatchDialerCallFact.direction == "outbound",
            activity_at >= start_at,
            activity_at < min(end_at, now),
        )
        .order_by(activity_at, BatchDialerCallFact.id)
        .limit(MAX_CALL_FACTS + 1)
    )
    facts = list(db.scalars(statement).all())
    if len(facts) > MAX_CALL_FACTS:
        raise ValueError(
            f"The selected range exceeds the {MAX_CALL_FACTS:,}-call evidence limit. "
            "Choose a smaller date range."
        )

    identities = list(
        db.scalars(
            select(BatchDialerAgentIdentity).where(
                BatchDialerAgentIdentity.organization_id == principal.organization_id
            )
        ).all()
    )
    identity_by_id = {row.id: row for row in identities}
    user_ids = {row.mapped_user_id for row in identities if row.mapped_user_id is not None}
    users = (
        list(
            db.scalars(
                select(User).where(
                    User.organization_id == principal.organization_id,
                    User.id.in_(user_ids),
                )
            ).all()
        )
        if user_ids
        else []
    )
    user_by_id = {row.id: row for row in users}
    downstream_by_fact = _downstream_by_fact(db, principal.organization_id, facts)

    summary = _Accumulator()
    agents: dict[str, _Accumulator] = defaultdict(_Accumulator)
    campaigns: dict[str, _Accumulator] = defaultdict(_Accumulator)
    campaign_names: dict[str, str] = {}
    days: dict[tuple[date, str], _Accumulator] = defaultdict(_Accumulator)
    hours: dict[tuple[datetime, str], _Accumulator] = defaultdict(_Accumulator)

    for fact in facts:
        downstream = downstream_by_fact.get(fact.id, _Downstream())
        agent_key = fact.provider_agent_id or "unmapped-provider-agent"
        campaign_key = fact.provider_campaign_id or "unknown-campaign"
        campaign_names[campaign_key] = fact.provider_campaign_name or campaign_names.get(
            campaign_key,
            "Unknown campaign",
        )
        local_occurred = _fact_occurred_at(fact).astimezone(timezone)
        hour_start_at = local_occurred.replace(minute=0, second=0, microsecond=0)
        for accumulator in (
            summary,
            agents[agent_key],
            campaigns[campaign_key],
            days[(local_occurred.date(), agent_key)],
            hours[(hour_start_at, agent_key)],
        ):
            accumulator.add(fact, downstream)

    facts_by_agent: dict[str, list[BatchDialerCallFact]] = defaultdict(list)
    for fact in facts:
        facts_by_agent[fact.provider_agent_id or "unmapped-provider-agent"].append(fact)

    agent_rows: list[BatchDialerVaScorecardRead] = []
    for provider_agent_id, accumulator in agents.items():
        sample = facts_by_agent[provider_agent_id][-1]
        identity = (
            identity_by_id.get(sample.agent_identity_id) if sample.agent_identity_id else None
        )
        mapped_user = (
            user_by_id.get(identity.mapped_user_id)
            if identity is not None and identity.mapped_user_id is not None
            else None
        )
        agent_rows.append(
            BatchDialerVaScorecardRead(
                mapping_id=identity.id if identity else None,
                provider_agent_id=provider_agent_id,
                provider_agent_name=sample.provider_agent_name or "Unknown BatchDialer agent",
                user_id=mapped_user.id if mapped_user else None,
                user_name=mapped_user.display_name if mapped_user else None,
                metrics=accumulator.read(),
            )
        )

    unresolved = sum(
        1
        for fact in facts
        if fact.disposition_classification in {"interested", "appointment_set"}
        and fact.final_qualification_status in {None, "pending", "needs_review"}
        and fact.final_processing_status not in {"quarantined", "exhausted"}
    )
    unmapped = sum(1 for row in agent_rows if row.user_id is None)
    warnings = [
        (
            "Calling minutes are inferred from BatchDialer call timestamps with idle gaps removed. "
            "They are not login time, paid hours, or a timeclock."
        ),
        (
            "Qualification false positives are provider-selected candidates that failed "
            "Stonegate's evidence gate or were rejected by an authorized reviewer; they are not "
            "disciplinary findings."
        ),
        (
            f"BatchDialer direct sync scans a rolling {settings.batchdialer_scan_days}-day "
            "provider window. This report only includes calls already archived by Stonegate "
            "and does not prove continuous historical coverage."
        ),
        (
            "Appointments, contracts, and closures are current cohort outcomes as of this "
            "snapshot for handoffs whose calls fall in the selected range. Those outcomes may "
            "mature after the calling period, and recent cohorts are not maturity-normalized."
        ),
    ]
    if provider_sync_freshness == "incomplete":
        if provider_sync_status == "missing":
            warnings.append(
                "The BatchDialer provider CDR sync has no checkpoint yet. Recent call coverage "
                "is incomplete until a successful provider poll is recorded."
            )
        elif provider_sync_status == "failed" or provider_sync_error_present:
            warnings.append(
                "The latest BatchDialer provider CDR sync is in a failed/error state. Recent "
                "calls may be missing; the provider error text is intentionally not exposed "
                "in this manager report."
            )
        else:
            warnings.append(
                "The BatchDialer provider CDR sync has not completed successfully yet. Recent "
                "call coverage is incomplete."
            )
    elif provider_sync_freshness == "stale":
        warnings.append(
            "The last successful BatchDialer provider CDR sync is more than two configured "
            f"poll intervals old ({settings.batchdialer_poll_seconds} seconds per interval). "
            "Recent calls may be missing."
        )
    if earliest_archived_call_at is None:
        archive_history_status = "no_archived_calls"
        warnings.append(
            "No archived BatchDialer call is currently available. Zero values do not prove "
            "that no provider calls occurred."
        )
    elif start_at < earliest_archived_call_at:
        archive_history_status = "selected_range_may_be_incomplete"
        warnings.append(
            "The selected range begins before the earliest call currently archived by "
            "Stonegate. Earlier dates may be incomplete rather than zero."
        )
    elif provider_sync_freshness != "current":
        archive_history_status = "selected_range_may_be_incomplete"
    else:
        archive_history_status = "archived_calls_available"
    if unresolved:
        warnings.append(
            f"{unresolved} provider candidate(s) are still awaiting final qualification and are "
            "excluded from verified-handoff and false-positive totals."
        )
    if unmapped:
        warnings.append(
            f"{unmapped} observed BatchDialer agent identity/identities are not mapped to a "
            "Stonegate user. Calls remain visible under the provider name."
        )
    missing_duration_count = len(facts) - len(summary.recorded_duration_call_ids)
    if missing_duration_count:
        warnings.append(
            f"{missing_duration_count} call(s) lack provider duration. Total and average "
            "recorded duration exclude those calls instead of treating them as zero."
        )
    missing_contact_id_count = len(facts) - len(summary.identified_contact_call_ids)
    if missing_contact_id_count:
        warnings.append(
            f"{missing_contact_id_count} call(s) lack a provider contact ID. Unique-contact "
            "totals exclude those calls instead of treating each call as a different person."
        )
    uncertain_human_contact_count = sum(
        _human_contact_evidence(fact, _normalized_label(fact.raw_disposition)) is None
        for fact in facts
    )
    if uncertain_human_contact_count:
        warnings.append(
            f"{uncertain_human_contact_count} call(s) lack explicit human-contact evidence. "
            "They are excluded from human-contact totals; a generic completed status is not "
            "treated as proof that a person answered."
        )

    return BatchDialerVaPerformanceRead(
        timezone=settings.batchdialer_account_timezone,
        date_from=start_date,
        date_to=end_date,
        as_of=now,
        earliest_archived_call_at=earliest_archived_call_at,
        archive_history_status=archive_history_status,
        provider_scan_window_days=settings.batchdialer_scan_days,
        provider_sync_status=provider_sync_status,
        provider_sync_freshness=provider_sync_freshness,
        provider_sync_last_success_at=provider_sync_last_success_at,
        provider_sync_error_present=provider_sync_error_present,
        provider_sync_poll_interval_seconds=settings.batchdialer_poll_seconds,
        summary=summary.read(),
        agents=sorted(
            agent_rows,
            key=lambda row: (
                -row.metrics.verified_handoffs,
                -row.metrics.human_contacts,
                row.provider_agent_name.casefold(),
            ),
        ),
        campaigns=[
            BatchDialerCampaignScorecardRead(
                provider_campaign_id=campaign_id,
                campaign_name=campaign_names[campaign_id],
                metrics=accumulator.read(),
            )
            for campaign_id, accumulator in sorted(campaigns.items())
        ],
        daily_activity=[
            BatchDialerVaDailyActivityRead(
                date=day,
                provider_agent_id=agent_id,
                provider_agent_name=(
                    facts_by_agent[agent_id][-1].provider_agent_name or "Unknown BatchDialer agent"
                ),
                metrics=accumulator.read(),
            )
            for (day, agent_id), accumulator in sorted(days.items())
        ],
        hourly_activity=[
            BatchDialerVaHourlyActivityRead(
                hour_start_at=hour,
                provider_agent_id=agent_id,
                provider_agent_name=(
                    facts_by_agent[agent_id][-1].provider_agent_name or "Unknown BatchDialer agent"
                ),
                calls=(metrics := accumulator.read()).calls,
                human_contacts=metrics.human_contacts,
                verified_handoffs=metrics.verified_handoffs,
                recorded_call_seconds=metrics.recorded_call_seconds,
            )
            for (hour, agent_id), accumulator in sorted(hours.items())
        ],
        coverage_warnings=warnings,
    )


def list_batchdialer_agent_mappings(
    db: Session,
    principal: Principal,
) -> BatchDialerAgentMappingListRead:
    _require_manager(principal)
    identities = list(
        db.scalars(
            select(BatchDialerAgentIdentity)
            .where(BatchDialerAgentIdentity.organization_id == principal.organization_id)
            .order_by(
                BatchDialerAgentIdentity.display_name, BatchDialerAgentIdentity.provider_agent_id
            )
        ).all()
    )
    mapped_user_ids = {
        identity.mapped_user_id
        for identity in identities
        if identity.mapped_user_id is not None
    }
    user_scope = [User.is_active.is_(True)]
    if mapped_user_ids:
        user_scope.append(User.id.in_(mapped_user_ids))
    users = list(
        db.scalars(
            select(User)
            .where(
                User.organization_id == principal.organization_id,
                or_(*user_scope),
            )
            .order_by(User.display_name, User.email)
        ).all()
    )
    user_by_id = {row.id: row for row in users}
    return BatchDialerAgentMappingListRead(
        items=[
            BatchDialerAgentMappingRead(
                id=identity.id,
                provider_agent_id=identity.provider_agent_id,
                provider_agent_name=(identity.display_name or identity.provider_agent_id),
                user_id=identity.mapped_user_id,
                user_name=(
                    user_by_id[identity.mapped_user_id].display_name
                    if identity.mapped_user_id in user_by_id
                    else None
                ),
                last_seen_at=identity.last_seen_at,
            )
            for identity in identities
        ],
        users=[
            BatchDialerAgentMappingUserRead(
                id=user.id,
                name=user.display_name,
                email=user.email,
                is_active=user.is_active,
            )
            for user in users
        ],
    )


def get_batchdialer_va_coaching_input(
    db: Session,
    principal: Principal,
    *,
    provider_agent_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[BatchDialerVaPerformanceRead, datetime, datetime, dict[str, object]]:
    """Build a bounded, deterministic evidence snapshot for the AI coach.

    Metrics are calculated by the scorecard service. The AI receives those immutable
    numbers and a small set of provider event references; it is never asked to derive
    operational totals itself.
    """

    performance = get_batchdialer_va_performance(
        db,
        principal,
        date_from=date_from,
        date_to=date_to,
    )
    normalized_agent_id = provider_agent_id.strip()
    agent = next(
        (row for row in performance.agents if row.provider_agent_id == normalized_agent_id),
        None,
    )
    if agent is None:
        raise ValueError("No BatchDialer call evidence exists for that agent and date range.")
    timezone = ZoneInfo(performance.timezone)
    range_start = datetime.combine(performance.date_from, time.min, timezone).astimezone(UTC)
    range_end = min(
        datetime.combine(
            performance.date_to + timedelta(days=1),
            time.min,
            timezone,
        ).astimezone(UTC),
        performance.as_of,
    )
    activity_at = func.coalesce(
        BatchDialerCallFact.started_at,
        BatchDialerCallFact.occurred_at,
        BatchDialerCallFact.received_at,
    )
    facts = list(
        db.scalars(
            select(BatchDialerCallFact)
            .where(
                BatchDialerCallFact.organization_id == principal.organization_id,
                BatchDialerCallFact.provider_agent_id == normalized_agent_id,
                BatchDialerCallFact.direction == "outbound",
                activity_at >= range_start,
                activity_at < range_end,
            )
            .order_by(activity_at.desc(), BatchDialerCallFact.id.desc())
        ).all()
    )
    prioritized_facts = sorted(
        facts,
        key=lambda fact: (
            0
            if fact.final_qualification_status == "rejected_by_human"
            or fact.final_outcome == "needs_review"
            else 1
            if fact.disposition_classification in {"interested", "appointment_set"}
            else 2,
            -_fact_occurred_at(fact).timestamp(),
        ),
    )[:40]
    peer_metrics = {
        row.provider_agent_id: row.metrics.model_dump(mode="json")
        for row in performance.agents
        if row.provider_agent_id != normalized_agent_id
    }
    snapshot: dict[str, object] = {
        "provider_agent": {
            "provider_agent_id": agent.provider_agent_id,
            "provider_agent_name": agent.provider_agent_name,
            "stonegate_user_id": str(agent.user_id) if agent.user_id else None,
            "stonegate_user_name": agent.user_name,
        },
        "reporting_range": {
            "timezone": performance.timezone,
            "date_from": performance.date_from.isoformat(),
            "date_to": performance.date_to.isoformat(),
            "as_of": performance.as_of.isoformat(),
        },
        "metrics": agent.metrics.model_dump(mode="json"),
        "comparison_metrics": {
            "team_summary": performance.summary.model_dump(mode="json"),
            "peer_agents": peer_metrics,
        },
        "coverage_metrics": {
            "selected_agent_call_facts": len(facts),
            "provider_events_supplied": len(prioritized_facts),
            "peer_agent_count": len(peer_metrics),
            "campaign_mix_normalized": False,
            "paid_hours_available": False,
            "archive_history_status": performance.archive_history_status,
            "earliest_archived_call_at": (
                performance.earliest_archived_call_at.isoformat()
                if performance.earliest_archived_call_at
                else None
            ),
            "provider_scan_window_days": performance.provider_scan_window_days,
            "provider_sync_status": performance.provider_sync_status,
            "provider_sync_freshness": performance.provider_sync_freshness,
            "provider_sync_last_success_at": (
                performance.provider_sync_last_success_at.isoformat()
                if performance.provider_sync_last_success_at
                else None
            ),
            "provider_sync_error_present": performance.provider_sync_error_present,
            "provider_sync_poll_interval_seconds": (
                performance.provider_sync_poll_interval_seconds
            ),
            "provider_sync_coverage_complete": (
                performance.provider_sync_freshness == "current"
            ),
            "continuous_archive_history_proven": False,
            "outcome_maturity_normalized": False,
            "downstream_outcomes_as_of": performance.as_of.isoformat(),
        },
        "provider_events": [
            {
                "provider_event_id": str(fact.provider_event_id),
                "occurred_at": _fact_occurred_at(fact).isoformat(),
                "raw_disposition": fact.raw_disposition,
                "disposition_classification": fact.disposition_classification,
                "final_outcome": fact.final_outcome,
                "final_qualification_status": fact.final_qualification_status,
                "final_processing_status": fact.final_processing_status,
                "duration_seconds": fact.duration_seconds,
                "transcript_available": fact.transcript_available,
                "qualification_evidence_present": fact.qualification_evidence_present,
            }
            for fact in prioritized_facts
        ],
        "comparison_context": {
            "note": (
                "Peer rows are descriptive only. Campaign, list difficulty, shift coverage, and "
                "sample sizes are not normalized. Calling spans are not paid hours."
            )
        },
        "metric_definitions": {
            "verified_handoffs": (
                "Evidence-accepted provider candidates that created a new Stonegate lead. "
                "Later accepted calls attached to an existing lead are not counted again."
            ),
            "evidence_accepted_candidates": (
                "Provider-selected candidates accepted by Stonegate's evidence gate, including "
                "accepted later calls attached to an existing lead."
            ),
            "qualification_false_positives": (
                "Provider-selected qualified candidates that did not pass Stonegate's evidence "
                "gate or were rejected by an authorized reviewer. This is a workflow-quality "
                "signal, not proof that the VA made an error."
            ),
            "recorded_duration": (
                "Total and average duration use only calls with provider-recorded duration; "
                "missing durations are excluded rather than treated as zero."
            ),
            "unique_contacts": (
                "Unique contacts use provider contact IDs only. Calls without a provider contact "
                "ID are excluded and reported through contact-ID coverage."
            ),
            "downstream_outcomes": (
                "Appointments, contracts, and closures are current as-of outcomes for handoffs "
                "whose calls occurred in the selected range. They may mature later and are not "
                "normalized for cohort age."
            ),
        },
    }
    return performance, range_start, range_end, snapshot


def update_batchdialer_agent_mapping(
    db: Session,
    principal: Principal,
    *,
    mapping_id: UUID,
    user_id: UUID | None,
) -> BatchDialerAgentMappingRead | None:
    _require_manager(principal)
    identity = db.scalar(
        select(BatchDialerAgentIdentity)
        .where(
            BatchDialerAgentIdentity.organization_id == principal.organization_id,
            BatchDialerAgentIdentity.id == mapping_id,
        )
        .with_for_update(of=BatchDialerAgentIdentity)
    )
    if identity is None:
        return None
    previous_user_id = identity.mapped_user_id
    user: User | None = None
    if previous_user_id == user_id:
        if user_id is not None:
            user = db.scalar(
                select(User).where(
                    User.organization_id == principal.organization_id,
                    User.id == user_id,
                )
            )
        db.commit()
        return BatchDialerAgentMappingRead(
            id=identity.id,
            provider_agent_id=identity.provider_agent_id,
            provider_agent_name=identity.display_name or identity.provider_agent_id,
            user_id=user.id if user else None,
            user_name=user.display_name if user else None,
            last_seen_at=identity.last_seen_at,
        )
    if user_id is not None:
        user = db.scalar(
            select(User).where(
                User.organization_id == principal.organization_id,
                User.id == user_id,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise ValueError("The selected Stonegate user is not active in this workspace.")
        existing_mapping = db.scalar(
            select(BatchDialerAgentIdentity.id).where(
                BatchDialerAgentIdentity.organization_id == principal.organization_id,
                BatchDialerAgentIdentity.mapped_user_id == user.id,
                BatchDialerAgentIdentity.id != identity.id,
            )
        )
        if existing_mapping is not None:
            raise ValueError(
                "That Stonegate user is already mapped to another BatchDialer agent. "
                "Clear the existing mapping before assigning this identity."
            )
    next_user_id = user.id if user else None
    now = datetime.now(UTC)
    identity.mapped_user_id = next_user_id
    identity.mapped_by_user_id = principal.user_id
    identity.mapped_at = now
    if previous_user_id is None:
        audit_action = "prospecting.batchdialer_agent_mapping_set"
        audit_reason = "BatchDialer agent mapping set"
    elif next_user_id is None:
        audit_action = "prospecting.batchdialer_agent_mapping_cleared"
        audit_reason = "BatchDialer agent mapping cleared"
    else:
        audit_action = "prospecting.batchdialer_agent_mapping_changed"
        audit_reason = "BatchDialer agent mapping changed"
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=audit_action,
            entity_type="batchdialer_agent_identity",
            entity_id=identity.id,
            previous_value={
                "provider_agent_id": identity.provider_agent_id,
                "mapped_user_id": str(previous_user_id) if previous_user_id else None,
            },
            new_value={
                "provider_agent_id": identity.provider_agent_id,
                "mapped_user_id": str(next_user_id) if next_user_id else None,
            },
            reason=audit_reason,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            "That Stonegate user is already mapped to another BatchDialer agent. "
            "Clear the existing mapping before assigning this identity."
        ) from exc
    db.refresh(identity)
    return BatchDialerAgentMappingRead(
        id=identity.id,
        provider_agent_id=identity.provider_agent_id,
        provider_agent_name=identity.display_name or identity.provider_agent_id,
        user_id=user.id if user else None,
        user_name=user.display_name if user else None,
        last_seen_at=identity.last_seen_at,
    )


def _downstream_by_fact(
    db: Session,
    organization_id: UUID,
    facts: list[BatchDialerCallFact],
) -> dict[UUID, _Downstream]:
    accepted = [
        fact
        for fact in facts
        if fact.lead_id is not None
        and fact.final_qualification_status == "accepted"
        and fact.lead_created_by_event
    ]
    winner_by_lead: dict[UUID, BatchDialerCallFact] = {}
    for fact in sorted(accepted, key=lambda row: (_fact_occurred_at(row), row.id)):
        if fact.lead_id is not None:
            winner_by_lead.setdefault(fact.lead_id, fact)
    lead_ids = set(winner_by_lead)
    if not lead_ids:
        return {}
    appointments = list(
        db.scalars(
            select(Appointment).where(
                Appointment.organization_id == organization_id,
                Appointment.lead_id.in_(lead_ids),
            )
        ).all()
    )
    transactions = list(
        db.scalars(
            select(Transaction).where(
                Transaction.organization_id == organization_id,
                Transaction.lead_id.in_(lead_ids),
            )
        ).all()
    )
    appointments_by_lead: dict[UUID, list[Appointment]] = defaultdict(list)
    transactions_by_lead: dict[UUID, list[Transaction]] = defaultdict(list)
    for appointment in appointments:
        appointments_by_lead[appointment.lead_id].append(appointment)
    for transaction in transactions:
        transactions_by_lead[transaction.lead_id].append(transaction)
    result: dict[UUID, _Downstream] = {}
    for lead_id, fact in winner_by_lead.items():
        handoff_at = _fact_occurred_at(fact)
        lead_appointments = [
            row
            for row in appointments_by_lead.get(lead_id, [])
            if _as_utc(row.created_at) >= handoff_at
        ]
        lead_transactions = [
            row
            for row in transactions_by_lead.get(lead_id, [])
            if _as_utc(row.created_at) >= handoff_at
        ]
        result[fact.id] = _Downstream(
            appointment_ids=frozenset(row.id for row in lead_appointments),
            held_appointment_ids=frozenset(
                row.id
                for row in lead_appointments
                if _normalized_label(row.status) in HELD_APPOINTMENT_STATUSES
            ),
            signed_transaction_ids=frozenset(
                row.id
                for row in lead_transactions
                if row.contract_executed_at is not None
                and _as_utc(row.contract_executed_at) >= handoff_at
            ),
            closed_transaction_ids=frozenset(
                row.id
                for row in lead_transactions
                if (
                    row.closed_at is not None and _as_utc(row.closed_at) >= handoff_at
                )
                or (
                    row.funded_at is not None and _as_utc(row.funded_at) >= handoff_at
                )
            ),
        )
    return result


def _is_human_contact(fact: BatchDialerCallFact, raw_disposition: str) -> bool:
    return _human_contact_evidence(fact, raw_disposition) is True


def _human_contact_evidence(
    fact: BatchDialerCallFact,
    raw_disposition: str,
) -> bool | None:
    if fact.disposition_classification in {"interested", "appointment_set"}:
        return True
    if any(label in raw_disposition for label in _NO_HUMAN_DISPOSITIONS):
        return False
    if any(label in raw_disposition for label in _HUMAN_DISPOSITIONS):
        return True
    if _normalized_label(fact.provider_status) in {"answered", "connected"}:
        return True
    return None


def _inferred_activity_minutes(
    intervals_by_agent: dict[str, list[tuple[datetime, datetime]]],
) -> int | None:
    if not intervals_by_agent:
        return None
    total_seconds = 0.0
    for intervals in intervals_by_agent.values():
        if not intervals:
            continue
        ordered = sorted(intervals)
        block_start, block_end = ordered[0]
        for start_at, end_at in ordered[1:]:
            if start_at <= block_end + ACTIVITY_GAP:
                block_end = max(block_end, end_at)
                continue
            total_seconds += max((block_end - block_start).total_seconds(), 0)
            block_start, block_end = start_at, end_at
        total_seconds += max((block_end - block_start).total_seconds(), 0)
    return ceil(total_seconds / 60)


def _rate(numerator: int, denominator: int) -> int | None:
    return round(numerator * 10_000 / denominator) if denominator else None


def _normalized_label(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def _provider_sync_health(
    checkpoint: BatchDialerSyncCheckpoint | None,
    *,
    now: datetime,
    poll_interval_seconds: int,
) -> tuple[str, str]:
    """Return a sanitized provider state and a conservative coverage freshness verdict."""

    if checkpoint is None:
        return "missing", "incomplete"
    raw_status = _normalized_label(checkpoint.status).replace(" ", "_")
    normalized_status = (
        raw_status
        if raw_status in {"idle", "polling", "healthy", "failed"}
        else "unknown"
    )
    if raw_status in {"failed", "error"} or checkpoint.last_error:
        return "failed", "incomplete"
    # CDR pages commit incrementally. A recent prior success cannot make the
    # current page-by-page refresh complete until the provider scan finishes.
    if raw_status == "polling":
        return normalized_status, "incomplete"
    if checkpoint.last_success_at is None:
        return normalized_status, "incomplete"
    stale_after = timedelta(seconds=max(poll_interval_seconds, 1) * 2)
    if _as_utc(checkpoint.last_success_at) < now - stale_after:
        return normalized_status, "stale"
    return normalized_status, "current"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _fact_occurred_at(fact: BatchDialerCallFact) -> datetime:
    return _as_utc(fact.started_at or fact.occurred_at or fact.received_at)


def _require_manager(principal: Principal) -> None:
    if PermissionKeys.MANAGE_ACQUISITION_OPERATIONS not in principal.permission_keys:
        raise PermissionError("Acquisition operations management permission is required.")
