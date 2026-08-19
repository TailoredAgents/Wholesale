import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, case, exists, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    AuditEvent,
    CallRecord,
    Campaign,
    Market,
    Organization,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectingAttempt,
    ProspectingCohort,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingProviderEvent,
    ProspectingScriptVersion,
    SuppressionRecord,
    Territory,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.prospecting import (
    DialerContextRead,
    DialerLegStatus,
    DialerProfileStatus,
    DialerSessionState,
    ProspectingDialerProfileRead,
    ProspectingDialerProfileUpsert,
    ProspectingDialerSwitchRead,
    ProspectingDialerSwitchUpdate,
    ProspectingDialLegRead,
    ProspectingDialSessionControlRead,
    ProspectingDialSessionEndCommand,
    ProspectingDialSessionLeaseCommand,
    ProspectingDialSessionRead,
    ProspectingDialSessionRecoveryCommand,
    ProspectingDialSessionSnapshotRead,
    ProspectingDialSessionStart,
)
from app.services.communication_compliance import format_e164

DIAL_LEG_STATUSES = {
    "queued",
    "dialing",
    "ringing",
    "answered",
    "connected",
    "cancelling",
    "cancelled",
    "no_answer",
    "busy",
    "failed",
    "completed",
}
DIAL_LEG_TERMINAL_STATUSES = {"cancelled", "no_answer", "busy", "failed", "completed"}
PROSPECTING_VOICE_LINE_PURPOSE = "prospecting_outbound"
DIAL_LEG_TERMINAL_REGRESSIONS = {
    "cancelled": {"answered", "connected"},
    "no_answer": {"answered", "connected", "cancelling"},
    "busy": {"answered", "connected", "cancelling"},
}
DIAL_LEG_PROGRESS_RANK = {
    "queued": 0,
    "dialing": 1,
    "ringing": 2,
    "answered": 3,
    "connected": 4,
    "cancelling": 5,
}
ACTIVE_DIAL_SESSION_STATES = {
    "ready",
    "dialing",
    "ringing",
    "connected",
    "wrap_up",
    "paused",
    "reconnecting",
}
TERMINAL_DIAL_SESSION_STATES = {"ended", "stopped", "failed", "expired"}
ACTIVE_DIAL_LEG_STATUSES = DIAL_LEG_STATUSES - DIAL_LEG_TERMINAL_STATUSES
CALLBACK_DISPOSITIONS = {"callback_requested", "follow_up"}
RETRY_DISPOSITIONS = {
    "no_answer",
    "left_voicemail",
    "technical_failure",
    "wrong_number",
}
VALID_PHONE_STATUSES = {"valid", "verified"}
ACTIVE_BATCH_STATUSES = {"active", "ready", "in_progress"}
RECOVERY_REPLAY_DIGEST_VERSION = "hmac-sha256-v1"


class ProspectingDialerConflictError(RuntimeError):
    """The requested session mutation conflicts with durable dialer state."""


class ProspectingDialerConfigurationError(RuntimeError):
    """A hard dialer policy or launch control prevents the requested action."""


@dataclass(frozen=True)
class DialerRuntimeGraph:
    organization: Organization
    caller: User
    profile: ProspectingDialerProfile
    campaign: Campaign
    market: Market
    territory: Territory | None
    cohort: ProspectingCohort
    batch: ProspectCallingBatch
    line: VoiceLine


def start_dial_session(
    db: Session,
    principal: Principal,
    payload: ProspectingDialSessionStart,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    """Create one durable VA session and atomically reserve its first record."""

    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    require_dialer_work_permission(principal)

    existing = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialSession.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        _validate_start_replay(existing, principal, payload)
        return session_control_read(
            db,
            existing,
            lease_token=existing.lease_token,
            queue_status="unchanged" if existing.current_attempt_id else "none",
            replayed=True,
        )

    active = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialSession.caller_user_id == principal.user_id,
            ProspectingDialSession.ended_at.is_(None),
        )
    )
    if active is not None:
        raise ProspectingDialerConflictError(
            "Finish or recover the current dialer session before starting another."
        )

    graph = load_runtime_graph(
        db,
        principal,
        campaign_id=payload.campaign_id,
        cohort_id=payload.cohort_id,
        batch_id=payload.calling_batch_id,
    )
    if graph is None:
        return None
    validate_runtime_policy(db, graph, active_settings, now=current, for_reservation=True)

    effective_lines = min(
        payload.requested_line_count,
        graph.organization.prospecting_dialer_max_concurrent_legs,
        graph.profile.max_line_count,
        graph.campaign.prospecting_dialer_max_concurrent_legs,
        graph.line.prospecting_dialer_max_concurrent_legs,
        active_settings.prospecting_native_dialer_effective_line_cap,
    )
    if effective_lines != 1:
        raise ProspectingDialerConfigurationError(
            "The current native dialer release supports exactly one controlled line."
        )

    lease_token = secrets.token_urlsafe(32)
    session = ProspectingDialSession(
        organization_id=principal.organization_id,
        dialer_profile_id=graph.profile.id,
        caller_user_id=principal.user_id,
        campaign_id=graph.campaign.id,
        cohort_id=graph.cohort.id,
        prospect_calling_batch_id=graph.batch.id,
        voice_line_id=graph.line.id,
        current_prospect_id=None,
        current_batch_entry_id=None,
        current_attempt_id=None,
        state="ready",
        requested_line_count=payload.requested_line_count,
        effective_line_count=effective_lines,
        organization_line_limit=graph.organization.prospecting_dialer_max_concurrent_legs,
        va_line_limit=graph.profile.max_line_count,
        campaign_line_limit=graph.campaign.prospecting_dialer_max_concurrent_legs,
        voice_line_limit=graph.line.prospecting_dialer_max_concurrent_legs,
        feature_line_limit=active_settings.prospecting_native_dialer_effective_line_cap,
        idempotency_key=payload.idempotency_key,
        browser_session_id=payload.browser_session_id,
        provider_session_id=None,
        lease_token=lease_token,
        lease_expires_at=current
        + timedelta(seconds=active_settings.prospecting_native_dialer_lease_seconds),
        started_at=current,
        paused_at=None,
        resumed_at=None,
        heartbeat_at=current,
        ended_at=None,
        stop_reason=None,
        recovery_metadata={},
        session_metadata={"coordinator_version": "d3", "pause_after_current": False},
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
    )
    db.add(session)
    try:
        db.flush()
        queue_status = reserve_next_locked(
            db,
            principal,
            session,
            graph,
            active_settings,
            now=current,
        )
        add_session_audit(
            db,
            principal,
            session,
            action="prospecting.dial_session_started",
            previous=None,
            reason="Native prospecting calling session started",
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(ProspectingDialSession).where(
                ProspectingDialSession.organization_id == principal.organization_id,
                ProspectingDialSession.idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            _validate_start_replay(replay, principal, payload)
            return session_control_read(
                db,
                replay,
                lease_token=replay.lease_token,
                queue_status="unchanged" if replay.current_attempt_id else "none",
                replayed=True,
            )
        raise ProspectingDialerConflictError(
            "A dialer session or prospect reservation was created concurrently."
        ) from exc
    return session_control_read(
        db,
        session,
        lease_token=lease_token,
        queue_status=queue_status,
        replayed=False,
    )


def read_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
) -> ProspectingDialSessionSnapshotRead | None:
    session = authorized_session(db, principal, session_id)
    return session_snapshot_read(db, session) if session is not None else None


def heartbeat_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    validate_session_lease(session, payload, now=current)
    reconcile_session_current_leg(db, session, now=current)
    apply_runtime_kill_if_needed(db, session, active_settings, now=current)
    if session.ended_at is None:
        session.heartbeat_at = current
        session.lease_expires_at = current + timedelta(
            seconds=active_settings.prospecting_native_dialer_lease_seconds
        )
        session.updated_by_user_id = principal.user_id
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status="unchanged" if session.current_attempt_id else "none",
        replayed=False,
    )


def pause_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    validate_session_lease(session, payload, now=current)
    if session.state in TERMINAL_DIAL_SESSION_STATES:
        raise ProspectingDialerConflictError("This dialer session has already ended.")
    previous = session_snapshot(session)
    leg = current_session_leg(db, session)
    if (
        leg is not None and leg.status not in {"queued"} | DIAL_LEG_TERMINAL_STATUSES
    ) or session.state == "wrap_up":
        metadata = dict(session.session_metadata)
        metadata["pause_after_current"] = True
        session.session_metadata = metadata
    else:
        session.state = "paused"
        session.paused_at = session.paused_at or current
    session.heartbeat_at = current
    session.lease_expires_at = current + timedelta(
        seconds=active_settings.prospecting_native_dialer_lease_seconds
    )
    session.updated_by_user_id = principal.user_id
    add_session_audit(
        db,
        principal,
        session,
        action="prospecting.dial_session_paused",
        previous=previous,
        reason="Caller paused native prospecting",
    )
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status="unchanged" if session.current_attempt_id else "none",
        replayed=False,
    )


def resume_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    validate_session_lease(session, payload, now=current)
    if session.state not in {"paused", "reconnecting"}:
        if session.state in TERMINAL_DIAL_SESSION_STATES:
            raise ProspectingDialerConflictError("This dialer session has already ended.")
        return session_control_read(
            db,
            session,
            lease_token=session.lease_token,
            queue_status="unchanged" if session.current_attempt_id else "none",
            replayed=True,
        )
    graph = load_session_runtime_graph(db, session)
    if graph is None:
        raise ProspectingDialerConfigurationError("The dialer session setup is incomplete.")
    validate_runtime_policy(db, graph, active_settings, now=current, for_reservation=False)
    previous = session_snapshot(session)
    metadata = dict(session.session_metadata)
    metadata["pause_after_current"] = False
    session.session_metadata = metadata
    session.resumed_at = current
    session.paused_at = None
    # Leave the paused/reconnecting state before reconciling or reserving. The
    # reconciliation helper intentionally preserves an explicit pause, and the
    # reservation path rejects paused sessions.
    session.state = "ready"
    session.heartbeat_at = current
    session.lease_expires_at = current + timedelta(
        seconds=active_settings.prospecting_native_dialer_lease_seconds
    )
    session.updated_by_user_id = principal.user_id
    if session.current_attempt_id is not None:
        reconcile_session_current_leg(db, session, now=current)
        queue_status = "unchanged"
    else:
        queue_status = reserve_next_locked(
            db,
            principal,
            session,
            graph,
            active_settings,
            now=current,
        )
    add_session_audit(
        db,
        principal,
        session,
        action="prospecting.dial_session_resumed",
        previous=previous,
        reason="Caller resumed native prospecting",
    )
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status=queue_status,
        replayed=False,
    )


def end_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionEndCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    if session.state in TERMINAL_DIAL_SESSION_STATES:
        return session_control_read(
            db,
            session,
            lease_token=None,
            queue_status="none",
            replayed=True,
        )
    validate_session_lease(session, payload, now=current)
    previous = session_snapshot(session)
    leg = current_session_leg(db, session)
    if leg is not None and (leg.status != "queued" or leg.call_record_id or leg.provider_call_id):
        metadata = dict(session.session_metadata)
        metadata["stop_after_current"] = True
        session.session_metadata = metadata
        session.stop_reason = payload.reason.strip()
        session.heartbeat_at = current
        session.lease_expires_at = current + timedelta(
            seconds=active_settings.prospecting_native_dialer_lease_seconds
        )
        queue_status = "unchanged"
    elif session.state == "wrap_up" and session.current_attempt_id is not None:
        metadata = dict(session.session_metadata)
        metadata["stop_after_current"] = True
        session.session_metadata = metadata
        session.stop_reason = payload.reason.strip()
        queue_status = "unchanged"
    else:
        if leg is not None:
            release_unstarted_reservation(db, session, leg, now=current, reason="session_ended")
        terminate_session(session, state="ended", now=current, reason=payload.reason.strip())
        queue_status = "none"
    session.updated_by_user_id = principal.user_id
    add_session_audit(
        db,
        principal,
        session,
        action="prospecting.dial_session_end_requested",
        previous=previous,
        reason=payload.reason.strip(),
    )
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status=queue_status,
        replayed=False,
    )


def recover_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionRecoveryCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    if session.state in TERMINAL_DIAL_SESSION_STATES:
        raise ProspectingDialerConflictError("This dialer session can no longer be recovered.")
    if exact_recovery_replay_matches(session, payload):
        return session_control_read(
            db,
            session,
            lease_token=session.lease_token,
            queue_status="unchanged",
            replayed=True,
        )
    if session.browser_session_id != payload.previous_browser_session_id:
        raise ProspectingDialerConflictError("The prior browser session does not match.")
    if payload.new_browser_session_id == payload.previous_browser_session_id:
        raise ProspectingDialerConflictError("Recovery requires a new browser session identifier.")
    browser_owner = db.scalar(
        select(ProspectingDialSession.id).where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialSession.browser_session_id == payload.new_browser_session_id,
            ProspectingDialSession.id != session.id,
        )
    )
    if browser_owner is not None:
        raise ProspectingDialerConflictError(
            "The new browser session identifier is already in use."
        )
    if not safe_token_match(session.lease_token, payload.lease_token):
        raise ProspectingDialerConflictError("The dialer lease token is invalid.")
    if session.lease_expires_at is None or as_utc(session.lease_expires_at) > current:
        raise ProspectingDialerConflictError("The current browser lease is still active.")
    previous = session_snapshot(session)
    recovered_state = session.state
    previous_lease_token = payload.lease_token
    recovered_at = current.isoformat()
    session.browser_session_id = payload.new_browser_session_id
    session.lease_token = secrets.token_urlsafe(32)
    session.lease_expires_at = current + timedelta(
        seconds=active_settings.prospecting_native_dialer_lease_seconds
    )
    session.heartbeat_at = current
    session.updated_by_user_id = principal.user_id
    reconcile_session_current_leg(db, session, now=current)
    if session.current_attempt_id is None:
        if recovered_state == "paused":
            session.state = "paused"
            queue_status = "none"
        else:
            session.state = "ready"
            graph = load_session_runtime_graph(db, session)
            if graph is None:
                raise ProspectingDialerConfigurationError("The dialer session setup is incomplete.")
            validate_runtime_policy(db, graph, active_settings, now=current, for_reservation=False)
            queue_status = reserve_next_locked(
                db,
                principal,
                session,
                graph,
                active_settings,
                now=current,
            )
    else:
        queue_status = "unchanged"
    recovery = dict(session.recovery_metadata)
    recovery["recovery_digest_version"] = RECOVERY_REPLAY_DIGEST_VERSION
    recovery["previous_browser_session_id"] = payload.previous_browser_session_id
    recovery["previous_lease_token_digest"] = recovery_replay_digest(
        current_lease_token=session.lease_token,
        session_id=session.id,
        previous_lease_token=previous_lease_token,
        previous_browser_session_id=payload.previous_browser_session_id,
        new_browser_session_id=payload.new_browser_session_id,
        recovered_at=recovered_at,
    )
    recovery["recovered_at"] = recovered_at
    recovery["recovered_browser_session_id"] = payload.new_browser_session_id
    session.recovery_metadata = recovery
    add_session_audit(
        db,
        principal,
        session,
        action="prospecting.dial_session_recovered",
        previous=previous,
        reason="Expired browser lease recovered by its assigned caller",
    )
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status=queue_status,
        replayed=False,
    )


def reserve_next_dial_record(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionControlRead | None:
    active_settings = settings or get_settings()
    current = as_utc(now or datetime.now(UTC))
    session = locked_control_session(db, principal, session_id)
    if session is None:
        return None
    validate_session_lease(session, payload, now=current)
    if session.state in {"paused", "reconnecting"} | TERMINAL_DIAL_SESSION_STATES:
        raise ProspectingDialerConflictError(
            "Resume or recover the dialer session before reserving another record."
        )
    if session.current_attempt_id is not None:
        return session_control_read(
            db,
            session,
            lease_token=session.lease_token,
            queue_status="unchanged",
            replayed=True,
        )
    graph = load_session_runtime_graph(db, session)
    if graph is None:
        raise ProspectingDialerConfigurationError("The dialer session setup is incomplete.")
    validate_runtime_policy(db, graph, active_settings, now=current, for_reservation=True)
    queue_status = reserve_next_locked(
        db,
        principal,
        session,
        graph,
        active_settings,
        now=current,
    )
    session.heartbeat_at = current
    session.lease_expires_at = (
        current + timedelta(seconds=active_settings.prospecting_native_dialer_lease_seconds)
        if session.ended_at is None
        else None
    )
    session.updated_by_user_id = principal.user_id
    db.commit()
    return session_control_read(
        db,
        session,
        lease_token=session.lease_token,
        queue_status=queue_status,
        replayed=False,
    )


def update_company_dialer_switch(
    db: Session,
    principal: Principal,
    payload: ProspectingDialerSwitchUpdate,
    *,
    now: datetime | None = None,
) -> ProspectingDialerSwitchRead | None:
    if not can_manage_dialer(principal):
        raise PermissionError("Only an acquisition manager can change the company dialer switch.")
    current = as_utc(now or datetime.now(UTC))
    organization = db.scalar(
        select(Organization).where(Organization.id == principal.organization_id).with_for_update()
    )
    if organization is None:
        return None
    previous = {"enabled": organization.prospecting_dialer_enabled}
    organization.prospecting_dialer_enabled = payload.enabled
    if not payload.enabled:
        stop_idle_sessions_for_scope(
            db,
            organization_id=organization.id,
            campaign_id=None,
            now=current,
            reason=payload.reason,
        )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="prospecting.company_dialer_switch_updated",
            entity_type="organization",
            entity_id=organization.id,
            previous_value=previous,
            new_value={"enabled": payload.enabled},
            reason=payload.reason.strip(),
        )
    )
    db.commit()
    return ProspectingDialerSwitchRead(
        scope="company",
        scope_id=organization.id,
        enabled=organization.prospecting_dialer_enabled,
        reason=payload.reason.strip(),
        updated_at=organization.updated_at,
    )


def update_campaign_dialer_switch(
    db: Session,
    principal: Principal,
    campaign_id: UUID,
    payload: ProspectingDialerSwitchUpdate,
    *,
    now: datetime | None = None,
) -> ProspectingDialerSwitchRead | None:
    if not can_manage_dialer(principal):
        raise PermissionError("Only an acquisition manager can change a campaign dialer switch.")
    current = as_utc(now or datetime.now(UTC))
    campaign = db.scalar(
        select(Campaign)
        .where(
            Campaign.id == campaign_id,
            Campaign.organization_id == principal.organization_id,
        )
        .with_for_update()
    )
    if campaign is None:
        return None
    previous = {"enabled": campaign.prospecting_dialer_enabled}
    campaign.prospecting_dialer_enabled = payload.enabled
    if not payload.enabled:
        stop_idle_sessions_for_scope(
            db,
            organization_id=principal.organization_id,
            campaign_id=campaign.id,
            now=current,
            reason=payload.reason,
        )
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action="prospecting.campaign_dialer_switch_updated",
            entity_type="campaign",
            entity_id=campaign.id,
            previous_value=previous,
            new_value={"enabled": payload.enabled},
            reason=payload.reason.strip(),
        )
    )
    db.commit()
    return ProspectingDialerSwitchRead(
        scope="campaign",
        scope_id=campaign.id,
        enabled=campaign.prospecting_dialer_enabled,
        reason=payload.reason.strip(),
        updated_at=campaign.updated_at,
    )


def load_runtime_graph(
    db: Session,
    principal: Principal,
    *,
    campaign_id: UUID,
    cohort_id: UUID,
    batch_id: UUID,
) -> DialerRuntimeGraph | None:
    organization = db.scalar(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    caller = db.scalar(
        select(User).where(
            User.id == principal.user_id,
            User.organization_id == principal.organization_id,
        )
    )
    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == principal.organization_id,
            ProspectingDialerProfile.user_id == principal.user_id,
        )
    )
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.organization_id == principal.organization_id,
        )
    )
    cohort = db.scalar(
        select(ProspectingCohort).where(
            ProspectingCohort.id == cohort_id,
            ProspectingCohort.organization_id == principal.organization_id,
        )
    )
    batch = db.scalar(
        select(ProspectCallingBatch).where(
            ProspectCallingBatch.id == batch_id,
            ProspectCallingBatch.organization_id == principal.organization_id,
        )
    )
    if any(value is None for value in (organization, caller, profile, campaign, cohort, batch)):
        return None
    assert organization is not None
    assert caller is not None
    assert profile is not None
    assert campaign is not None
    assert cohort is not None
    assert batch is not None
    if batch.assigned_user_id != principal.user_id:
        raise PermissionError("This calling batch is assigned to another caller.")
    if campaign.id != cohort.campaign_id or campaign.id != batch.campaign_id:
        raise ProspectingDialerConfigurationError(
            "The campaign, cohort, and calling batch do not match."
        )
    if batch.cohort_id != cohort.id:
        raise ProspectingDialerConfigurationError(
            "The calling batch is not assigned to this cohort."
        )
    market = db.scalar(
        select(Market).where(
            Market.id == campaign.market_id,
            Market.organization_id == principal.organization_id,
        )
    )
    territory = (
        db.scalar(
            select(Territory).where(
                Territory.id == campaign.territory_id,
                Territory.organization_id == principal.organization_id,
            )
        )
        if campaign.territory_id is not None
        else None
    )
    line = dialer_voice_line(db, profile)
    if market is None or line is None or (campaign.territory_id is not None and territory is None):
        return None
    return DialerRuntimeGraph(
        organization=organization,
        caller=caller,
        profile=profile,
        campaign=campaign,
        market=market,
        territory=territory,
        cohort=cohort,
        batch=batch,
        line=line,
    )


def load_session_runtime_graph(
    db: Session,
    session: ProspectingDialSession,
) -> DialerRuntimeGraph | None:
    if session.cohort_id is None or session.prospect_calling_batch_id is None:
        return None
    principal = Principal(
        user_id=session.caller_user_id,
        organization_id=session.organization_id,
        email="dialer-session@stonegate.invalid",
        permission_keys=frozenset(),
    )
    return load_runtime_graph(
        db,
        principal,
        campaign_id=session.campaign_id,
        cohort_id=session.cohort_id,
        batch_id=session.prospect_calling_batch_id,
    )


def validate_runtime_policy(
    db: Session,
    graph: DialerRuntimeGraph,
    settings: Settings,
    *,
    now: datetime,
    for_reservation: bool,
) -> None:
    blockers = runtime_policy_blockers(
        db,
        graph,
        settings,
        now=now,
        for_reservation=for_reservation,
    )
    if blockers:
        raise ProspectingDialerConfigurationError(" ".join(blockers))


def runtime_policy_blockers(
    db: Session,
    graph: DialerRuntimeGraph,
    settings: Settings,
    *,
    now: datetime,
    for_reservation: bool,
) -> list[str]:
    blockers: list[str] = []
    local_date = cohort_local_date(graph.cohort, now)
    if not settings.prospecting_native_dialer_enabled:
        blockers.append("Native prospecting dialer is disabled by the launch flag.")
    if not graph.organization.is_active:
        blockers.append("The Stonegate workspace is inactive.")
    if not graph.organization.prospecting_dialer_enabled:
        blockers.append("The company prospecting dialer switch is off.")
    if not graph.caller.is_active or not graph.caller.calling_enabled:
        blockers.append("Cold calling is not enabled for this caller.")
    if graph.profile.status != "active":
        blockers.append("The caller's native dialer profile is not active.")
    if graph.campaign.status != "active":
        blockers.append("The prospecting campaign is not active.")
    if not graph.campaign.prospecting_dialer_enabled:
        blockers.append("The campaign prospecting dialer switch is off.")
    if graph.campaign.starts_on is not None and local_date < graph.campaign.starts_on:
        blockers.append("The campaign has not started yet.")
    if graph.campaign.ends_on is not None and local_date > graph.campaign.ends_on:
        blockers.append("The campaign has ended.")
    if graph.market.status != "active":
        blockers.append("The campaign market is not active.")
    if graph.territory is not None and graph.territory.status != "active":
        blockers.append("The campaign territory is not active.")
    if graph.cohort.status != "active":
        blockers.append("The calling cohort is not active.")
    if local_date < graph.cohort.starts_on:
        blockers.append("The calling cohort has not started yet.")
    if graph.cohort.ends_on is not None and local_date > graph.cohort.ends_on:
        blockers.append("The calling cohort has ended.")
    if not within_cohort_calling_window(graph.cohort, now):
        blockers.append("Calling is outside this cohort's approved local window.")
    if graph.batch.status not in ACTIVE_BATCH_STATUSES:
        blockers.append("The assigned calling batch is not active.")
    if graph.batch.assigned_user_id != graph.caller.id:
        blockers.append("The calling batch is assigned to another caller.")
    if graph.batch.campaign_id != graph.campaign.id or graph.batch.cohort_id != graph.cohort.id:
        blockers.append("The calling batch no longer matches this campaign and cohort.")
    if graph.profile.voice_line_id != graph.line.id:
        blockers.append("The caller's assigned prospecting line has changed.")
    if graph.line.status != "active" or graph.line.provider != "twilio":
        blockers.append("The assigned Twilio prospecting line is unavailable.")
    if (
        graph.line.department_key != "acquisitions"
        or graph.line.purpose_key != PROSPECTING_VOICE_LINE_PURPOSE
    ):
        blockers.append("A dedicated acquisitions prospecting-outbound line is required.")
    if not settings.twilio_voice_configured:
        blockers.append("Twilio Voice is not configured for controlled calling.")
    if (
        min(
            graph.organization.prospecting_dialer_max_concurrent_legs,
            graph.profile.max_line_count,
            graph.campaign.prospecting_dialer_max_concurrent_legs,
            graph.line.prospecting_dialer_max_concurrent_legs,
            settings.prospecting_native_dialer_effective_line_cap,
        )
        < 1
    ):
        blockers.append("No prospecting dial line is currently authorized.")

    active_legs = ProspectingDialLeg.completed_at.is_(None)
    organization_active_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                active_legs,
            )
        )
        or 0
    )
    campaign_active_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .join(
                ProspectingDialSession,
                ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
            )
            .where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                ProspectingDialSession.campaign_id == graph.campaign.id,
                active_legs,
            )
        )
        or 0
    )
    caller_active_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id))
            .join(
                ProspectingDialSession,
                ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
            )
            .where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                ProspectingDialSession.caller_user_id == graph.caller.id,
                active_legs,
            )
        )
        or 0
    )
    voice_line_active_legs = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                ProspectingDialLeg.voice_line_id == graph.line.id,
                active_legs,
            )
        )
        or 0
    )

    def capacity_reached(active_count: int, limit: int) -> bool:
        # Reservation adds a new leg. Runtime revalidation includes the session's
        # already-reserved leg, so equality remains valid in that path.
        return active_count >= limit if for_reservation else active_count > limit

    feature_line_cap = settings.prospecting_native_dialer_effective_line_cap
    if capacity_reached(
        organization_active_legs,
        min(
            graph.organization.prospecting_dialer_max_concurrent_legs,
            feature_line_cap,
        ),
    ):
        blockers.append("The company prospecting line capacity is already in use.")
    if capacity_reached(
        campaign_active_legs,
        min(
            graph.campaign.prospecting_dialer_max_concurrent_legs,
            feature_line_cap,
        ),
    ):
        blockers.append("The campaign prospecting line capacity is already in use.")
    if capacity_reached(
        caller_active_legs,
        min(graph.profile.max_line_count, feature_line_cap),
    ):
        blockers.append("The caller's prospecting line capacity is already in use.")
    if capacity_reached(
        voice_line_active_legs,
        min(
            graph.line.prospecting_dialer_max_concurrent_legs,
            feature_line_cap,
        ),
    ):
        blockers.append("The assigned Twilio line is already at capacity.")

    day_start, day_end = cohort_local_day_bounds(graph.cohort, now)
    dial_count = (
        db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                ProspectingDialLeg.dial_session_id.in_(
                    select(ProspectingDialSession.id).where(
                        ProspectingDialSession.organization_id == graph.organization.id,
                        ProspectingDialSession.caller_user_id == graph.caller.id,
                    )
                ),
                ProspectingDialLeg.queued_at >= day_start,
                ProspectingDialLeg.queued_at < day_end,
            )
        )
        or 0
    )
    if graph.profile.daily_dial_limit is not None:
        over_limit = (
            dial_count >= graph.profile.daily_dial_limit
            if for_reservation
            else dial_count > graph.profile.daily_dial_limit
        )
        if over_limit:
            blockers.append("The caller's daily dial limit has been reached.")

    spend = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            ProspectingDialLeg.actual_cost_cents,
                            ProspectingDialLeg.reserved_cost_cents,
                        )
                    ),
                    0,
                )
            ).where(
                ProspectingDialLeg.organization_id == graph.organization.id,
                ProspectingDialLeg.dial_session_id.in_(
                    select(ProspectingDialSession.id).where(
                        ProspectingDialSession.organization_id == graph.organization.id,
                        ProspectingDialSession.caller_user_id == graph.caller.id,
                    )
                ),
                ProspectingDialLeg.queued_at >= day_start,
                ProspectingDialLeg.queued_at < day_end,
            )
        )
        or 0
    )
    if graph.profile.daily_spend_limit_cents is not None:
        projected_spend = (
            spend + settings.prospecting_native_dialer_reserved_cost_cents
            if for_reservation
            else spend
        )
        if projected_spend > graph.profile.daily_spend_limit_cents:
            blockers.append("The caller's daily prospecting spend cap has been reached.")
    return blockers


def cohort_local_date(cohort: ProspectingCohort, now: datetime) -> date:
    try:
        return as_utc(now).astimezone(ZoneInfo(cohort.timezone)).date()
    except ZoneInfoNotFoundError as exc:
        raise ProspectingDialerConfigurationError(
            "The calling cohort has an invalid timezone."
        ) from exc


def within_cohort_calling_window(cohort: ProspectingCohort, now: datetime) -> bool:
    try:
        local = as_utc(now).astimezone(ZoneInfo(cohort.timezone))
    except ZoneInfoNotFoundError:
        return False
    hour = local.hour
    start = cohort.call_window_start_hour
    end = cohort.call_window_end_hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def cohort_local_day_bounds(
    cohort: ProspectingCohort,
    now: datetime,
) -> tuple[datetime, datetime]:
    try:
        timezone = ZoneInfo(cohort.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ProspectingDialerConfigurationError(
            "The calling cohort has an invalid timezone."
        ) from exc
    local_date = as_utc(now).astimezone(timezone).date()
    start = datetime.combine(local_date, time.min, tzinfo=timezone).astimezone(UTC)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=timezone).astimezone(
        UTC
    )
    return start, end


def reserve_next_locked(
    db: Session,
    principal: Principal,
    session: ProspectingDialSession,
    graph: DialerRuntimeGraph,
    settings: Settings,
    *,
    now: datetime,
) -> str:
    """Reserve one record while the caller session row remains locked by its transaction."""

    if session.current_attempt_id is not None:
        return "unchanged"
    if session.state in {"paused", "reconnecting"} | TERMINAL_DIAL_SESSION_STATES:
        raise ProspectingDialerConflictError("This dialer session cannot reserve a record.")
    serialize_reservation_capacity(db, session.organization_id)
    validate_runtime_policy(db, graph, settings, now=now, for_reservation=True)

    skipped_ids: list[UUID] = []
    while True:
        statement = candidate_entry_statement(
            organization_id=session.organization_id,
            caller_user_id=session.caller_user_id,
            campaign_id=session.campaign_id,
            batch_id=graph.batch.id,
            now=now,
            excluded_ids=skipped_ids,
        )
        candidates = list(db.scalars(statement.limit(25)))
        if not candidates:
            terminate_session(session, state="ended", now=now, reason="queue_exhausted")
            return "empty"

        for entry in candidates:
            prospect = db.scalar(
                select(Prospect).where(
                    Prospect.id == entry.prospect_id,
                    Prospect.organization_id == session.organization_id,
                )
            )
            if prospect is None:
                skipped_ids.append(entry.id)
                continue
            selected = select_ranked_phone(db, prospect)
            if selected is None:
                skipped_ids.append(entry.id)
                continue
            contact_point, recipient = selected
            script = approved_script_for_reservation(db, graph, prospect)
            if script is None:
                raise ProspectingDialerConfigurationError(
                    f"No approved {prospect.asset_class} caller script is available."
                )
            try:
                with db.begin_nested():
                    snapshot = reservation_snapshot(entry)
                    attempt = build_reserved_attempt(
                        principal,
                        graph,
                        entry,
                        prospect,
                        script,
                        now=now,
                    )
                    db.add(attempt)
                    db.flush()
                    leg = ProspectingDialLeg(
                        organization_id=session.organization_id,
                        dial_session_id=session.id,
                        prospect_id=prospect.id,
                        batch_entry_id=entry.id,
                        attempt_id=attempt.id,
                        contact_point_id=contact_point.id if contact_point is not None else None,
                        voice_line_id=graph.line.id,
                        call_record_id=None,
                        line_slot=1,
                        recipient=recipient,
                        provider=graph.line.provider,
                        provider_call_id=None,
                        provider_recording_id=None,
                        idempotency_key=f"reserve:{session.id}:{attempt.id}",
                        status="queued",
                        last_provider_event_sequence=0,
                        last_provider_event_at=None,
                        reserved_cost_cents=settings.prospecting_native_dialer_reserved_cost_cents,
                        actual_cost_cents=None,
                        queued_at=now,
                        answer_classification="unknown",
                        party_classification="unknown",
                        terminal_result=None,
                        provider_error_code=None,
                        provider_error_message=None,
                        cancellation_reason=None,
                        leg_metadata={
                            "reservation_snapshot": snapshot,
                            "queue_priority": queue_priority_label(entry, now),
                            "coordinator_version": "d3",
                        },
                    )
                    entry.status = "in_progress"
                    graph.batch.status = "in_progress"
                    session.current_prospect_id = prospect.id
                    session.current_batch_entry_id = entry.id
                    session.current_attempt_id = attempt.id
                    session.state = "ready"
                    session.updated_by_user_id = principal.user_id
                    db.add(leg)
                    db.flush()
                    add_audit(
                        db,
                        principal,
                        action="prospecting.dial_record_reserved",
                        entity_type="prospecting_dial_session",
                        entity_id=session.id,
                        previous={"current_attempt_id": None},
                        new={
                            "prospect_id": str(prospect.id),
                            "entry_id": str(entry.id),
                            "attempt_id": str(attempt.id),
                            "dial_leg_id": str(leg.id),
                            "queue_priority": queue_priority_label(entry, now),
                        },
                        reason="Server atomically reserved the next eligible prospect",
                    )
            except IntegrityError:
                skipped_ids.append(entry.id)
                continue
            return "reserved"

        skipped_ids.extend(entry.id for entry in candidates if entry.id not in skipped_ids)


def serialize_reservation_capacity(db: Session, organization_id: UUID) -> None:
    """Serialize capacity checks and leg creation for one PostgreSQL workspace.

    Row-level candidate locks prevent duplicate prospects. This transaction-level
    advisory lock separately prevents two callers from both observing spare company,
    campaign, or voice-line capacity before either creates its dial leg.
    """

    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:capacity_key))"),
        {"capacity_key": f"stonegate:prospecting-dial-capacity:{organization_id}"},
    )


def candidate_entry_statement(
    *,
    organization_id: UUID,
    caller_user_id: UUID,
    campaign_id: UUID,
    batch_id: UUID,
    now: datetime,
    excluded_ids: list[UUID] | None = None,
) -> Any:
    callback_due = and_(
        ProspectCallingBatchEntry.disposition.in_(CALLBACK_DISPOSITIONS),
        ProspectCallingBatchEntry.next_attempt_at.is_not(None),
        ProspectCallingBatchEntry.next_attempt_at <= now,
    )
    correction_due = ProspectCallingBatchEntry.status == "needs_correction"
    retry_due = and_(
        ProspectCallingBatchEntry.status.in_(("queued", "ready")),
        ProspectCallingBatchEntry.disposition.in_(RETRY_DISPOSITIONS),
        ProspectCallingBatchEntry.next_attempt_at.is_not(None),
        ProspectCallingBatchEntry.next_attempt_at <= now,
    )
    new_record = and_(
        ProspectCallingBatchEntry.status.in_(("queued", "ready")),
        ProspectCallingBatchEntry.next_attempt_at.is_(None),
        ProspectCallingBatchEntry.disposition.is_(None),
    )
    statement = (
        select(ProspectCallingBatchEntry)
        .join(Prospect, Prospect.id == ProspectCallingBatchEntry.prospect_id)
        .where(
            ProspectCallingBatchEntry.organization_id == organization_id,
            ProspectCallingBatchEntry.assigned_user_id == caller_user_id,
            ProspectCallingBatchEntry.prospect_calling_batch_id == batch_id,
            ProspectCallingBatchEntry.status.in_(("queued", "ready", "needs_correction")),
            Prospect.organization_id == organization_id,
            Prospect.campaign_id == campaign_id,
            Prospect.assigned_user_id == caller_user_id,
            # A manager-requested handoff correction remains callable even though
            # the original handoff already linked this prospect to a warm lead.
            # Every other queue class stays cold-only.
            or_(Prospect.converted_lead_id.is_(None), correction_due),
            Prospect.suppression_status == "clear",
            Prospect.call_eligibility == "eligible",
            or_(callback_due, correction_due, retry_due, new_record),
            ~exists().where(
                ProspectingAttempt.batch_entry_id == ProspectCallingBatchEntry.id,
                ProspectingAttempt.status == "in_progress",
            ),
            ~exists().where(
                ProspectingDialLeg.batch_entry_id == ProspectCallingBatchEntry.id,
                ProspectingDialLeg.completed_at.is_(None),
            ),
            ~exists().where(
                ProspectingDialLeg.organization_id == organization_id,
                ProspectingDialLeg.prospect_id == ProspectCallingBatchEntry.prospect_id,
                ProspectingDialLeg.completed_at.is_(None),
            ),
        )
        .order_by(
            case(
                (callback_due, 0),
                (correction_due, 1),
                (retry_due, 2),
                else_=3,
            ),
            ProspectCallingBatchEntry.next_attempt_at.asc().nulls_last(),
            ProspectCallingBatchEntry.sequence_number,
            ProspectCallingBatchEntry.id,
        )
        .with_for_update(of=ProspectCallingBatchEntry, skip_locked=True)
    )
    if excluded_ids:
        statement = statement.where(ProspectCallingBatchEntry.id.not_in(excluded_ids))
    return statement


def select_ranked_phone(
    db: Session,
    prospect: Prospect,
) -> tuple[ProspectContactPoint | None, str] | None:
    points = list(
        db.scalars(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.organization_id == prospect.organization_id,
                ProspectContactPoint.prospect_id == prospect.id,
                ProspectContactPoint.contact_type == "phone",
                ProspectContactPoint.validation_status.in_(VALID_PHONE_STATUSES),
            )
            .order_by(
                ProspectContactPoint.rank,
                ProspectContactPoint.is_primary.desc(),
                ProspectContactPoint.created_at,
                ProspectContactPoint.id,
            )
        )
    )
    for point in points:
        metadata = point.contact_metadata or {}
        if metadata.get("source_dnc") is True:
            continue
        recipient = format_e164(point.normalized_value or point.value)
        if recipient is not None and not is_phone_suppressed(
            db, prospect.organization_id, recipient
        ):
            return point, recipient
    if prospect.phone_validation_status not in VALID_PHONE_STATUSES:
        return None
    recipient = format_e164(prospect.normalized_phone or prospect.phone)
    if recipient is None or is_phone_suppressed(db, prospect.organization_id, recipient):
        return None
    return None, recipient


def is_phone_suppressed(db: Session, organization_id: UUID, recipient: str) -> bool:
    return (
        db.scalar(
            select(SuppressionRecord.id).where(
                SuppressionRecord.organization_id == organization_id,
                SuppressionRecord.channel.in_(("phone", "all")),
                SuppressionRecord.normalized_address == recipient,
                SuppressionRecord.status == "active",
            )
        )
        is not None
    )


def approved_script_for_reservation(
    db: Session,
    graph: DialerRuntimeGraph,
    prospect: Prospect,
) -> ProspectingScriptVersion | None:
    if graph.cohort.script_version_id is not None:
        return db.scalar(
            select(ProspectingScriptVersion).where(
                ProspectingScriptVersion.id == graph.cohort.script_version_id,
                ProspectingScriptVersion.organization_id == graph.organization.id,
                ProspectingScriptVersion.asset_class == prospect.asset_class,
                ProspectingScriptVersion.status == "approved",
            )
        )
    return db.scalar(
        select(ProspectingScriptVersion)
        .where(
            ProspectingScriptVersion.organization_id == graph.organization.id,
            ProspectingScriptVersion.asset_class == prospect.asset_class,
            ProspectingScriptVersion.status == "approved",
        )
        .order_by(ProspectingScriptVersion.version_number.desc())
    )


def build_reserved_attempt(
    principal: Principal,
    graph: DialerRuntimeGraph,
    entry: ProspectCallingBatchEntry,
    prospect: Prospect,
    script: ProspectingScriptVersion,
    *,
    now: datetime,
) -> ProspectingAttempt:
    questions = script.qualification_questions or []
    required_count = sum(bool(question.get("required_for_handoff")) for question in questions)
    return ProspectingAttempt(
        organization_id=principal.organization_id,
        batch_entry_id=entry.id,
        prospect_id=prospect.id,
        caller_user_id=principal.user_id,
        script_version_id=script.id,
        call_record_id=None,
        provider=None,
        provider_call_id=None,
        provider_recording_id=None,
        provider_agent_id=None,
        cohort_id=graph.cohort.id,
        status="in_progress",
        outcome=None,
        contact_made=None,
        dialer_mode="one_line_power",
        answer_classification="unknown",
        party_classification="unknown",
        interest_classification="not_assessed",
        follow_up_permission="not_recorded",
        classification_source="manual_outcome",
        dial_started_at=None,
        answered_at=None,
        right_party_confirmed_at=None,
        interest_confirmed_at=None,
        measurement_metadata={"reservation_source": "native_dialer_d3"},
        qualification_answers={},
        notes=None,
        callback_at=None,
        started_at=now,
        completed_at=None,
        required_answer_count=required_count,
        answered_required_count=0,
        quality_score_basis_points=None,
    )


def reservation_snapshot(entry: ProspectCallingBatchEntry) -> dict[str, object]:
    return {
        "status": entry.status,
        "disposition": entry.disposition,
        "next_attempt_at": (
            as_utc(entry.next_attempt_at).isoformat() if entry.next_attempt_at is not None else None
        ),
        "completed_at": (
            as_utc(entry.completed_at).isoformat() if entry.completed_at is not None else None
        ),
        "attempt_count": entry.attempt_count,
    }


def queue_priority_label(entry: ProspectCallingBatchEntry, now: datetime) -> str:
    if (
        entry.disposition in CALLBACK_DISPOSITIONS
        and entry.next_attempt_at is not None
        and as_utc(entry.next_attempt_at) <= now
    ):
        return "callback"
    if entry.status == "needs_correction":
        return "correction"
    if (
        entry.disposition in RETRY_DISPOSITIONS
        and entry.next_attempt_at is not None
        and as_utc(entry.next_attempt_at) <= now
    ):
        return "retry"
    return "new"


def require_dialer_work_permission(principal: Principal) -> None:
    if not (
        PermissionKeys.WORK_ASSIGNED_CALLING_LISTS in principal.permission_keys
        or can_manage_dialer(principal)
    ):
        raise PermissionError("Cold calling is not enabled for the current user.")


def _validate_start_replay(
    session: ProspectingDialSession,
    principal: Principal,
    payload: ProspectingDialSessionStart,
) -> None:
    expected = (
        principal.user_id,
        payload.campaign_id,
        payload.cohort_id,
        payload.calling_batch_id,
        payload.browser_session_id,
        payload.requested_line_count,
    )
    actual = (
        session.caller_user_id,
        session.campaign_id,
        session.cohort_id,
        session.prospect_calling_batch_id,
        session.browser_session_id,
        session.requested_line_count,
    )
    if actual != expected:
        raise ProspectingDialerConflictError(
            "The idempotency key was already used for a different dialer session."
        )


def authorized_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
) -> ProspectingDialSession | None:
    session = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.id == session_id,
            ProspectingDialSession.organization_id == principal.organization_id,
        )
    )
    if session is not None and (
        session.caller_user_id != principal.user_id and not can_manage_dialer(principal)
    ):
        raise PermissionError("This dialer session belongs to another caller.")
    return session


def locked_control_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
) -> ProspectingDialSession | None:
    session = db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.id == session_id,
            ProspectingDialSession.organization_id == principal.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is not None and session.caller_user_id != principal.user_id:
        raise PermissionError("Only the assigned caller can control this dialer session.")
    return session


def safe_token_match(expected: str | None, provided: str) -> bool:
    return bool(expected) and secrets.compare_digest(expected or "", provided)


def recovery_replay_digest(
    *,
    current_lease_token: str,
    session_id: UUID,
    previous_lease_token: str,
    previous_browser_session_id: str,
    new_browser_session_id: str,
    recovered_at: str,
) -> str:
    canonical_payload = json.dumps(
        {
            "session_id": str(session_id),
            "previous_lease_token": previous_lease_token,
            "previous_browser_session_id": previous_browser_session_id,
            "new_browser_session_id": new_browser_session_id,
            "recovered_at": recovered_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        current_lease_token.encode("utf-8"),
        canonical_payload,
        hashlib.sha256,
    ).hexdigest()


def exact_recovery_replay_matches(
    session: ProspectingDialSession,
    payload: ProspectingDialSessionRecoveryCommand,
) -> bool:
    """Authenticate only the most recent, exact recovery request after response loss."""

    metadata = session.recovery_metadata or {}
    previous_browser_session_id = metadata.get("previous_browser_session_id")
    recovered_browser_session_id = metadata.get("recovered_browser_session_id")
    recovered_at = metadata.get("recovered_at")
    stored_digest = metadata.get("previous_lease_token_digest")
    current_lease_token = session.lease_token
    if (
        metadata.get("recovery_digest_version") != RECOVERY_REPLAY_DIGEST_VERSION
        or not isinstance(previous_browser_session_id, str)
        or not isinstance(recovered_browser_session_id, str)
        or not isinstance(recovered_at, str)
        or not isinstance(stored_digest, str)
        or current_lease_token is None
        or session.browser_session_id != recovered_browser_session_id
        or payload.previous_browser_session_id != previous_browser_session_id
        or payload.new_browser_session_id != recovered_browser_session_id
    ):
        return False
    expected_digest = recovery_replay_digest(
        current_lease_token=current_lease_token,
        session_id=session.id,
        previous_lease_token=payload.lease_token,
        previous_browser_session_id=payload.previous_browser_session_id,
        new_browser_session_id=payload.new_browser_session_id,
        recovered_at=recovered_at,
    )
    return secrets.compare_digest(stored_digest, expected_digest)


def validate_session_lease(
    session: ProspectingDialSession,
    payload: ProspectingDialSessionLeaseCommand | ProspectingDialSessionEndCommand,
    *,
    now: datetime,
) -> None:
    if session.browser_session_id != payload.browser_session_id:
        raise ProspectingDialerConflictError("The browser session does not own this dialer lease.")
    if not safe_token_match(session.lease_token, payload.lease_token):
        raise ProspectingDialerConflictError("The dialer lease token is invalid.")
    if session.lease_expires_at is None or as_utc(session.lease_expires_at) <= now:
        raise ProspectingDialerConflictError("The dialer lease expired and must be recovered.")


def current_session_leg(
    db: Session,
    session: ProspectingDialSession,
    *,
    lock: bool = False,
) -> ProspectingDialLeg | None:
    if session.current_attempt_id is None:
        return None
    statement = (
        select(ProspectingDialLeg)
        .where(
            ProspectingDialLeg.organization_id == session.organization_id,
            ProspectingDialLeg.dial_session_id == session.id,
            ProspectingDialLeg.attempt_id == session.current_attempt_id,
        )
        .order_by(ProspectingDialLeg.created_at.desc(), ProspectingDialLeg.id.desc())
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement.execution_options(populate_existing=True))


def session_snapshot_read(
    db: Session,
    session: ProspectingDialSession,
) -> ProspectingDialSessionSnapshotRead:
    return ProspectingDialSessionSnapshotRead(
        session=dial_session_read(session),
        current_leg=(
            dial_leg_read(leg) if (leg := current_session_leg(db, session)) is not None else None
        ),
    )


def session_control_read(
    db: Session,
    session: ProspectingDialSession,
    *,
    lease_token: str | None,
    queue_status: str,
    replayed: bool,
) -> ProspectingDialSessionControlRead:
    normalized_queue_status = cast(
        Any,
        queue_status if queue_status in {"reserved", "unchanged", "empty", "none"} else "none",
    )
    return ProspectingDialSessionControlRead(
        snapshot=session_snapshot_read(db, session),
        lease_token=(lease_token if session.state not in TERMINAL_DIAL_SESSION_STATES else None),
        queue_status=normalized_queue_status,
        replayed=replayed,
    )


def session_snapshot(session: ProspectingDialSession) -> dict[str, object]:
    return {
        "state": session.state,
        "current_prospect_id": (
            str(session.current_prospect_id) if session.current_prospect_id else None
        ),
        "current_batch_entry_id": (
            str(session.current_batch_entry_id) if session.current_batch_entry_id else None
        ),
        "current_attempt_id": (
            str(session.current_attempt_id) if session.current_attempt_id else None
        ),
        "browser_session_id": session.browser_session_id,
        "lease_expires_at": (
            as_utc(session.lease_expires_at).isoformat()
            if session.lease_expires_at is not None
            else None
        ),
        "ended_at": as_utc(session.ended_at).isoformat() if session.ended_at else None,
        "stop_reason": session.stop_reason,
        "metadata": dict(session.session_metadata),
    }


def add_session_audit(
    db: Session,
    principal: Principal,
    session: ProspectingDialSession,
    *,
    action: str,
    previous: dict[str, object] | None,
    reason: str,
) -> None:
    add_audit(
        db,
        principal,
        action=action,
        entity_type="prospecting_dial_session",
        entity_id=session.id,
        previous=previous,
        new=session_snapshot(session),
        reason=reason,
    )


def add_system_session_audit(
    db: Session,
    session: ProspectingDialSession,
    *,
    action: str,
    previous: dict[str, object] | None,
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=session.organization_id,
            actor_user_id=None,
            actor_type="system",
            action=action,
            entity_type="prospecting_dial_session",
            entity_id=session.id,
            previous_value=previous,
            new_value=session_snapshot(session),
            reason=reason,
        )
    )


def terminate_session(
    session: ProspectingDialSession,
    *,
    state: str,
    now: datetime,
    reason: str,
) -> None:
    if state not in TERMINAL_DIAL_SESSION_STATES:
        raise ValueError("A terminal dialer state is required.")
    session.state = state
    session.current_prospect_id = None
    session.current_batch_entry_id = None
    session.current_attempt_id = None
    session.ended_at = now
    session.stop_reason = reason[:255]
    session.lease_token = None
    session.lease_expires_at = None


def _snapshot_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def release_unstarted_reservation(
    db: Session,
    session: ProspectingDialSession,
    leg: ProspectingDialLeg,
    *,
    now: datetime,
    reason: str,
    prepared_call_record_id: UUID | None = None,
) -> None:
    has_unexpected_call_evidence = leg.call_record_id is not None and (
        prepared_call_record_id is None or leg.call_record_id != prepared_call_record_id
    )
    if leg.status != "queued" or leg.provider_call_id is not None or has_unexpected_call_evidence:
        raise ProspectingDialerConflictError(
            "A provider-started call reservation cannot be released."
        )
    entry = db.get(ProspectCallingBatchEntry, leg.batch_entry_id)
    attempt = db.get(ProspectingAttempt, leg.attempt_id) if leg.attempt_id else None
    snapshot = (leg.leg_metadata or {}).get("reservation_snapshot")
    if entry is not None:
        if isinstance(snapshot, dict):
            status_value = snapshot.get("status")
            disposition_value = snapshot.get("disposition")
            attempt_count_value = snapshot.get("attempt_count")
            entry.status = status_value if isinstance(status_value, str) else "queued"
            entry.disposition = disposition_value if isinstance(disposition_value, str) else None
            entry.next_attempt_at = _snapshot_datetime(snapshot.get("next_attempt_at"))
            entry.completed_at = _snapshot_datetime(snapshot.get("completed_at"))
            if isinstance(attempt_count_value, int) and attempt_count_value >= 0:
                entry.attempt_count = attempt_count_value
        else:
            entry.status = "queued"
            entry.completed_at = None
    if attempt is not None and attempt.status == "in_progress":
        attempt.status = "cancelled"
        attempt.outcome = "technical_failure"
        attempt.contact_made = False
        attempt.completed_at = now
        attempt.notes = f"Reservation released before provider start: {reason}"[:2000]
    leg.status = "cancelled"
    leg.cancelled_at = now
    leg.completed_at = now
    leg.terminal_result = "cancelled"
    leg.cancellation_reason = reason[:255]
    leg.reserved_cost_cents = 0
    leg.actual_cost_cents = 0
    leg_metadata = dict(leg.leg_metadata)
    leg_metadata["reservation_released_at"] = now.isoformat()
    leg_metadata["reservation_release_reason"] = reason
    leg.leg_metadata = leg_metadata
    session.current_prospect_id = None
    session.current_batch_entry_id = None
    session.current_attempt_id = None


def reconcile_session_current_leg(
    db: Session,
    session: ProspectingDialSession,
    *,
    now: datetime,
) -> ProspectingDialLeg | None:
    del now
    if session.state in TERMINAL_DIAL_SESSION_STATES:
        return None
    if session.current_attempt_id is None:
        if session.state not in {"paused", "reconnecting"}:
            session.state = "ready"
        return None
    leg = current_session_leg(db, session, lock=True)
    if leg is None:
        raise ProspectingDialerConfigurationError(
            "The dialer session's current attempt has no dial leg."
        )
    if leg.status == "queued":
        if session.state != "paused":
            session.state = "ready"
    elif leg.status in {"dialing", "cancelling"}:
        session.state = "dialing"
    elif leg.status == "ringing":
        session.state = "ringing"
    elif leg.status in {"answered", "connected"}:
        session.state = "connected"
    elif leg.status in DIAL_LEG_TERMINAL_STATUSES:
        session.state = "wrap_up"
    return leg


def reconcile_dial_session_from_leg(
    db: Session,
    leg: ProspectingDialLeg,
    *,
    now: datetime,
) -> ProspectingDialSession | None:
    # D2 deliberately supports sessions with autoflush disabled. Persist the provider
    # transition before reloading the session graph so populate_existing cannot restore
    # the leg's previous database state over the callback we are reconciling.
    db.flush([leg])
    session = db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.id == leg.dial_session_id,
            ProspectingDialSession.organization_id == leg.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None or session.state in TERMINAL_DIAL_SESSION_STATES:
        return session
    if (
        session.current_attempt_id != leg.attempt_id
        or session.current_batch_entry_id != leg.batch_entry_id
        or session.current_prospect_id != leg.prospect_id
    ):
        return session
    reconcile_session_current_leg(db, session, now=as_utc(now))
    return session


def validate_native_attempt_write_lease(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    *,
    browser_session_id: str | None,
    lease_token: str | None,
    now: datetime,
) -> ProspectingDialSession | None:
    """Lock the native session before its attempt and validate the live browser lease."""

    session = db.scalar(
        select(ProspectingDialSession)
        .join(
            ProspectingDialLeg,
            ProspectingDialLeg.dial_session_id == ProspectingDialSession.id,
        )
        .where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialLeg.organization_id == principal.organization_id,
            ProspectingDialLeg.attempt_id == attempt_id,
        )
        .order_by(ProspectingDialSession.created_at.desc())
        .with_for_update(of=ProspectingDialSession)
        .execution_options(populate_existing=True)
    )
    if session is None:
        native_leg = db.scalar(
            select(ProspectingDialLeg.id)
            .where(
                ProspectingDialLeg.organization_id == principal.organization_id,
                ProspectingDialLeg.attempt_id == attempt_id,
            )
            .limit(1)
        )
        if native_leg is not None:
            raise ProspectingDialerConflictError(
                "The native dialer session must be recovered before qualification "
                "answers can be saved."
            )
        return None
    if session.caller_user_id != principal.user_id:
        raise PermissionError("Only the assigned caller can update this dialer attempt.")
    if (
        session.ended_at is not None
        or session.current_attempt_id != attempt_id
        or session.state not in ACTIVE_DIAL_SESSION_STATES
    ):
        raise ProspectingDialerConflictError(
            "The dialer session changed before the qualification answer could be saved."
        )
    if browser_session_id is None or lease_token is None:
        raise ProspectingDialerConflictError(
            "The active dialer lease is required to save qualification answers."
        )
    if session.browser_session_id != browser_session_id:
        raise ProspectingDialerConflictError("The browser session does not own this dialer lease.")
    if not safe_token_match(session.lease_token, lease_token):
        raise ProspectingDialerConflictError("The dialer lease token is invalid.")
    if session.lease_expires_at is None or as_utc(session.lease_expires_at) <= as_utc(now):
        raise ProspectingDialerConflictError("The dialer lease expired and must be recovered.")
    return session


def validate_native_attempt_can_complete(
    db: Session,
    principal: Principal,
    attempt_id: UUID,
    *,
    browser_session_id: str | None,
    lease_token: str | None,
    now: datetime,
) -> tuple[ProspectingDialSession | None, bool]:
    """Lock the associated native session before the attempt completion transaction."""

    session = db.scalar(
        select(ProspectingDialSession)
        .join(
            ProspectingDialLeg,
            ProspectingDialLeg.dial_session_id == ProspectingDialSession.id,
        )
        .where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialLeg.organization_id == principal.organization_id,
            ProspectingDialLeg.attempt_id == attempt_id,
        )
        .order_by(ProspectingDialSession.created_at.desc())
        .with_for_update(of=ProspectingDialSession)
        .execution_options(populate_existing=True)
    )
    if session is not None:
        if session.caller_user_id != principal.user_id:
            raise PermissionError("Only the assigned caller can complete this dialer attempt.")
        active = session.ended_at is None and session.current_attempt_id == attempt_id
        if active:
            if browser_session_id is None or lease_token is None:
                raise ProspectingDialerConflictError(
                    "The active dialer lease is required to complete this disposition."
                )
            if session.browser_session_id != browser_session_id:
                raise ProspectingDialerConflictError(
                    "The browser session does not own this dialer lease."
                )
            if not safe_token_match(session.lease_token, lease_token):
                raise ProspectingDialerConflictError("The dialer lease token is invalid.")
            if session.lease_expires_at is None or as_utc(session.lease_expires_at) <= now:
                raise ProspectingDialerConflictError(
                    "The dialer lease expired and must be recovered."
                )
        return (session if active else None), True

    leg = db.scalar(
        select(ProspectingDialLeg.id)
        .where(
            ProspectingDialLeg.organization_id == principal.organization_id,
            ProspectingDialLeg.attempt_id == attempt_id,
        )
        .limit(1)
    )
    if leg is not None:
        raise ProspectingDialerConfigurationError(
            "The native dialer attempt has no associated session."
        )
    return None, False


def validate_native_attempt_terminal(
    db: Session,
    organization_id: UUID,
    attempt_id: UUID,
    *,
    native_attempt: bool,
) -> ProspectingDialLeg | None:
    if not native_attempt:
        return None
    leg = db.scalar(
        select(ProspectingDialLeg)
        .where(
            ProspectingDialLeg.organization_id == organization_id,
            ProspectingDialLeg.attempt_id == attempt_id,
        )
        .order_by(ProspectingDialLeg.created_at.desc(), ProspectingDialLeg.id.desc())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if leg is None:
        raise ProspectingDialerConfigurationError(
            "The native dialer attempt has no associated dial leg."
        )
    if leg.status not in DIAL_LEG_TERMINAL_STATUSES:
        raise ValueError("End the active call before recording its final disposition.")
    return leg


def complete_native_wrap_up(
    db: Session,
    principal: Principal,
    attempt: ProspectingAttempt,
    *,
    session: ProspectingDialSession | None,
    now: datetime,
    settings: Settings | None = None,
) -> None:
    if session is None:
        return
    if session.current_attempt_id != attempt.id or session.ended_at is not None:
        raise ProspectingDialerConflictError(
            "The dialer session changed before this disposition could be saved."
        )
    leg = current_session_leg(db, session, lock=True)
    if leg is None or leg.status not in DIAL_LEG_TERMINAL_STATUSES:
        raise ValueError("The dialer call must finish before its disposition is saved.")
    previous = session_snapshot(session)
    session.current_prospect_id = None
    session.current_batch_entry_id = None
    session.current_attempt_id = None
    session.updated_by_user_id = principal.user_id
    metadata = dict(session.session_metadata)
    stop_after_current = bool(metadata.pop("stop_after_current", False))
    pause_after_current = bool(metadata.pop("pause_after_current", False))
    metadata.pop("reservation_blocker", None)
    session.session_metadata = metadata
    completed_by_manager = principal.user_id != session.caller_user_id
    active_settings = settings or get_settings()
    if not completed_by_manager:
        # Saving wrap-up is an authenticated browser heartbeat. Renew the lease before
        # exposing another reservation so the next prospect is not born orphaned.
        session.heartbeat_at = now
        session.lease_expires_at = now + timedelta(
            seconds=active_settings.prospecting_native_dialer_lease_seconds
        )

    if stop_after_current:
        terminate_session(
            session,
            state="stopped",
            now=now,
            reason=session.stop_reason or "Stopped after the current call",
        )
    elif completed_by_manager:
        session.state = "paused"
        session.paused_at = now
        metadata = dict(session.session_metadata)
        metadata["reservation_blocker"] = (
            "A manager completed the prior disposition. Resume to continue calling."
        )
        session.session_metadata = metadata
    elif pause_after_current:
        session.state = "paused"
        session.paused_at = now
    else:
        graph = load_session_runtime_graph(db, session)
        if graph is None:
            session.state = "paused"
            session.paused_at = now
            metadata = dict(session.session_metadata)
            metadata["reservation_blocker"] = "The dialer session setup is incomplete."
            session.session_metadata = metadata
        else:
            caller_principal = Principal(
                user_id=session.caller_user_id,
                organization_id=session.organization_id,
                email=graph.caller.email,
                permission_keys=frozenset({PermissionKeys.WORK_ASSIGNED_CALLING_LISTS}),
            )
            try:
                reserve_next_locked(
                    db,
                    caller_principal,
                    session,
                    graph,
                    active_settings,
                    now=now,
                )
            except ProspectingDialerConfigurationError as exc:
                session.state = "paused"
                session.paused_at = now
                metadata = dict(session.session_metadata)
                metadata["reservation_blocker"] = str(exc)
                session.session_metadata = metadata
    add_session_audit(
        db,
        principal,
        session,
        action="prospecting.dial_session_wrap_up_completed",
        previous=previous,
        reason=(
            "Manager completed the disposition without advancing the caller queue"
            if completed_by_manager
            else "Caller disposition completed and the coordinator advanced safely"
        ),
    )


def validate_reserved_dial_leg_policy(
    db: Session,
    principal: Principal,
    leg: ProspectingDialLeg,
    settings: Settings,
    *,
    now: datetime,
    expected_call_record_id: UUID | None = None,
) -> None:
    require_dialer_work_permission(principal)
    session = db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.id == leg.dial_session_id,
            ProspectingDialSession.organization_id == principal.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None:
        raise ProspectingDialerConflictError("The dialer session no longer exists.")
    locked_leg = db.scalar(
        select(ProspectingDialLeg)
        .where(
            ProspectingDialLeg.id == leg.id,
            ProspectingDialLeg.organization_id == principal.organization_id,
            ProspectingDialLeg.dial_session_id == session.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_leg is None:
        raise ProspectingDialerConflictError("The reserved dial record no longer exists.")
    leg = locked_leg
    if session.caller_user_id != principal.user_id:
        raise PermissionError("This dial record is assigned to another caller.")
    if session.state != "ready" or leg.status != "queued":
        raise ProspectingDialerConflictError("This dial record is not ready to start.")
    if (
        session.current_prospect_id != leg.prospect_id
        or session.current_batch_entry_id != leg.batch_entry_id
        or session.current_attempt_id != leg.attempt_id
    ):
        raise ProspectingDialerConflictError("The session no longer owns this dial record.")
    if session.lease_expires_at is None or as_utc(session.lease_expires_at) <= now:
        raise ProspectingDialerConflictError("The dialer lease expired and must be recovered.")
    if leg.provider_call_id is not None or leg.call_record_id not in {
        None,
        expected_call_record_id,
    }:
        raise ProspectingDialerConflictError("This dial record already has provider evidence.")
    graph = load_session_runtime_graph(db, session)
    if graph is None:
        raise ProspectingDialerConfigurationError("The dialer session setup is incomplete.")
    validate_runtime_policy(db, graph, settings, now=now, for_reservation=False)
    recipient = format_e164(leg.recipient)
    if recipient is None or is_phone_suppressed(db, session.organization_id, recipient):
        raise ProspectingDialerConflictError("This phone number is currently suppressed.")
    prospect = db.scalar(
        select(Prospect)
        .where(
            Prospect.id == leg.prospect_id,
            Prospect.organization_id == session.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    reservation_priority = str((leg.leg_metadata or {}).get("queue_priority", ""))
    correction_retry = reservation_priority == "correction"
    if (
        prospect is None
        or (prospect.converted_lead_id is not None and not correction_retry)
        or prospect.suppression_status != "clear"
        or prospect.call_eligibility != "eligible"
    ):
        raise ProspectingDialerConflictError("The prospect is no longer eligible for calling.")
    if leg.contact_point_id is not None:
        point = db.scalar(
            select(ProspectContactPoint)
            .where(
                ProspectContactPoint.id == leg.contact_point_id,
                ProspectContactPoint.organization_id == session.organization_id,
                ProspectContactPoint.prospect_id == leg.prospect_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if point is None or point.validation_status not in VALID_PHONE_STATUSES:
            raise ProspectingDialerConflictError("The reserved phone is no longer valid.")
        if (point.contact_metadata or {}).get("source_dnc") is True:
            raise ProspectingDialerConflictError("The reserved phone is marked do-not-call.")
    elif (
        prospect.phone_validation_status not in VALID_PHONE_STATUSES
        or format_e164(prospect.normalized_phone or prospect.phone) != recipient
    ):
        raise ProspectingDialerConflictError("The reserved phone is no longer valid.")


def _hard_runtime_stop_reason(
    graph: DialerRuntimeGraph | None,
    settings: Settings,
) -> str | None:
    if not settings.prospecting_native_dialer_enabled:
        return "Native prospecting dialer launch flag was disabled"
    if graph is None:
        return "Native prospecting dialer configuration became incomplete"
    if not graph.organization.is_active or not graph.organization.prospecting_dialer_enabled:
        return "Company prospecting dialer access was disabled"
    if not graph.caller.is_active or not graph.caller.calling_enabled:
        return "Caller prospecting access was disabled"
    if graph.profile.status != "active":
        return "Caller dialer profile was disabled"
    if graph.campaign.status != "active" or not graph.campaign.prospecting_dialer_enabled:
        return "Campaign prospecting dialer access was disabled"
    if graph.cohort.status != "active" or graph.batch.status not in ACTIVE_BATCH_STATUSES:
        return "The assigned calling queue was disabled"
    if (
        graph.line.status != "active"
        or graph.line.provider != "twilio"
        or graph.profile.voice_line_id != graph.line.id
    ):
        return "The assigned prospecting voice line was disabled"
    return None


def apply_runtime_kill_if_needed(
    db: Session,
    session: ProspectingDialSession,
    settings: Settings,
    *,
    now: datetime,
) -> None:
    try:
        graph = load_session_runtime_graph(db, session)
    except (PermissionError, ProspectingDialerConfigurationError):
        graph = None
    reason = _hard_runtime_stop_reason(graph, settings)
    if reason is None or session.state in TERMINAL_DIAL_SESSION_STATES:
        return
    leg = current_session_leg(db, session, lock=True)
    if leg is None:
        terminate_session(session, state="stopped", now=now, reason=reason)
    elif leg.status == "queued" and not leg.call_record_id and not leg.provider_call_id:
        release_unstarted_reservation(db, session, leg, now=now, reason="runtime_kill")
        terminate_session(session, state="stopped", now=now, reason=reason)
    else:
        metadata = dict(session.session_metadata)
        metadata["stop_after_current"] = True
        metadata["runtime_kill_requested_at"] = now.isoformat()
        session.session_metadata = metadata
        session.stop_reason = reason


def stop_idle_sessions_for_scope(
    db: Session,
    *,
    organization_id: UUID,
    campaign_id: UUID | None,
    now: datetime,
    reason: str,
) -> None:
    statement = select(ProspectingDialSession).where(
        ProspectingDialSession.organization_id == organization_id,
        ProspectingDialSession.ended_at.is_(None),
    )
    if campaign_id is not None:
        statement = statement.where(ProspectingDialSession.campaign_id == campaign_id)
    sessions = list(db.scalars(statement.with_for_update()))
    for session in sessions:
        leg = current_session_leg(db, session, lock=True)
        if leg is None:
            terminate_session(session, state="stopped", now=now, reason=reason)
        elif leg.status == "queued" and not leg.call_record_id and not leg.provider_call_id:
            release_unstarted_reservation(db, session, leg, now=now, reason="switch_disabled")
            terminate_session(session, state="stopped", now=now, reason=reason)
        else:
            metadata = dict(session.session_metadata)
            metadata["stop_after_current"] = True
            metadata["switch_disabled_at"] = now.isoformat()
            session.session_metadata = metadata
            session.stop_reason = reason[:255]


def process_next_prospecting_dialer_recovery(
    db: Session,
    settings: Settings,
) -> UUID | None:
    """Safely inspect one stale session without ever starting or ending a provider call."""

    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.prospecting_native_dialer_stale_after_seconds)
    session = db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.ended_at.is_(None),
            ProspectingDialSession.lease_expires_at.is_not(None),
            ProspectingDialSession.lease_expires_at <= now,
            ProspectingDialSession.heartbeat_at <= stale_before,
        )
        .order_by(
            ProspectingDialSession.lease_expires_at,
            ProspectingDialSession.created_at,
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if session is None:
        return None

    previous = session_snapshot(session)
    leg = current_session_leg(db, session, lock=True)
    if session.current_attempt_id is None:
        terminate_session(
            session,
            state="expired",
            now=now,
            reason="Stale dialer session had no active reservation",
        )
        add_system_session_audit(
            db,
            session,
            action="prospecting.dial_session_expired",
            previous=previous,
            reason="Coordinator expired an idle stale session",
        )
        db.commit()
        return session.id

    if leg is None:
        attempt = db.get(ProspectingAttempt, session.current_attempt_id)
        if attempt is not None and (attempt.call_record_id or attempt.provider_call_id):
            _preserve_stale_session(
                session,
                now=now,
                reason="Provider evidence exists but the current dial leg is missing",
            )
            action = "prospecting.dial_session_recovery_preserved"
            audit_reason = "Coordinator preserved possible live provider work"
        else:
            if attempt is not None and attempt.status == "in_progress":
                attempt.status = "cancelled"
                attempt.outcome = "technical_failure"
                attempt.contact_made = False
                attempt.completed_at = now
                attempt.notes = "Coordinator released a reservation with a missing dial leg."
                entry = db.get(ProspectCallingBatchEntry, attempt.batch_entry_id)
                if entry is not None and entry.status == "in_progress":
                    entry.status = "queued"
                    entry.completed_at = None
            terminate_session(
                session,
                state="failed",
                now=now,
                reason="Stale reservation was missing its dial leg",
            )
            action = "prospecting.dial_session_recovery_failed"
            audit_reason = "Coordinator failed closed and released missing local work"
        add_system_session_audit(
            db,
            session,
            action=action,
            previous=previous,
            reason=audit_reason,
        )
        db.commit()
        return session.id

    if leg.status in DIAL_LEG_TERMINAL_STATUSES:
        session.state = "wrap_up"
        # Keep the expired lease expired so the assigned caller can immediately
        # recover it in a new browser. Heartbeat throttles repeat worker audits.
        session.heartbeat_at = now
        recovery = dict(session.recovery_metadata)
        recovery["terminal_leg_observed_at"] = now.isoformat()
        recovery["terminal_leg_id"] = str(leg.id)
        session.recovery_metadata = recovery
        action = "prospecting.dial_session_recovery_waiting_for_wrap_up"
        audit_reason = "Coordinator retained the completed call for human disposition"
    elif leg.provider_call_id:
        _preserve_stale_session(
            session,
            now=now,
            reason="Active provider call evidence exists",
        )
        action = "prospecting.dial_session_recovery_preserved"
        audit_reason = "Coordinator preserved an active provider call for browser recovery"
    elif leg.call_record_id or leg.status != "queued":
        action, audit_reason = _reconcile_stale_preprovider_start(
            db,
            session,
            leg,
            now=now,
        )
    else:
        recovery = dict(session.recovery_metadata)
        first_seen = _snapshot_datetime(recovery.get("queued_orphan_first_seen_at"))
        if first_seen is None:
            recovery["queued_orphan_first_seen_at"] = now.isoformat()
            recovery["queued_orphan_leg_id"] = str(leg.id)
            session.recovery_metadata = recovery
            session.state = "reconnecting"
            _extend_stale_lease(session, settings, now=now)
            action = "prospecting.dial_session_recovery_grace_started"
            audit_reason = "Coordinator opened a grace period for a queued-only reservation"
        elif now < first_seen + timedelta(
            seconds=settings.prospecting_native_dialer_orphan_grace_seconds
        ):
            session.state = "reconnecting"
            session.lease_expires_at = first_seen + timedelta(
                seconds=settings.prospecting_native_dialer_orphan_grace_seconds
            )
            action = "prospecting.dial_session_recovery_grace_retained"
            audit_reason = "Queued-only reservation remains inside its recovery grace period"
        else:
            release_unstarted_reservation(
                db,
                session,
                leg,
                now=now,
                reason="stale_queued_orphan",
            )
            terminate_session(
                session,
                state="expired",
                now=now,
                reason="Queued reservation expired without provider evidence",
            )
            action = "prospecting.dial_session_orphan_released"
            audit_reason = "Coordinator safely released a stale queued-only reservation"

    add_system_session_audit(
        db,
        session,
        action=action,
        previous=previous,
        reason=audit_reason,
    )
    db.commit()
    return session.id


def _extend_stale_lease(
    session: ProspectingDialSession,
    settings: Settings,
    *,
    now: datetime,
) -> None:
    session.lease_expires_at = now + timedelta(
        seconds=settings.prospecting_native_dialer_orphan_grace_seconds
    )


def _preserve_stale_session(
    session: ProspectingDialSession,
    *,
    now: datetime,
    reason: str,
) -> None:
    session.state = "reconnecting"
    # Do not renew an expired browser lease merely because provider evidence exists.
    # The exact prior browser/token pair may immediately rotate ownership via recover.
    session.heartbeat_at = now
    recovery = dict(session.recovery_metadata)
    recovery["provider_work_preserved_at"] = now.isoformat()
    recovery["provider_work_preserved_reason"] = reason
    session.recovery_metadata = recovery


def _reconcile_stale_preprovider_start(
    db: Session,
    session: ProspectingDialSession,
    leg: ProspectingDialLeg,
    *,
    now: datetime,
) -> tuple[str, str]:
    call = db.get(CallRecord, leg.call_record_id) if leg.call_record_id is not None else None
    intent = (
        db.get(VoiceCallIntent, call.call_intent_id)
        if call is not None and call.call_intent_id is not None
        else None
    )
    if call is not None and call.provider_call_id:
        leg.provider_call_id = call.provider_call_id
        attempt = db.get(ProspectingAttempt, leg.attempt_id) if leg.attempt_id else None
        if attempt is not None:
            attempt.provider_call_id = call.provider_call_id
        _preserve_stale_session(
            session,
            now=now,
            reason="Provider call evidence was repaired from the local call record",
        )
        return (
            "prospecting.dial_session_recovery_preserved",
            "Coordinator repaired and preserved provider call evidence",
        )

    metadata = dict(intent.intent_metadata or {}) if intent is not None else {}
    start_state = metadata.get("provider_start_state")
    dispatch_unexpired = (
        start_state == "dispatching" and intent is not None and as_utc(intent.expires_at) > now
    )
    if dispatch_unexpired:
        _preserve_stale_session(
            session,
            now=now,
            reason="Provider dispatch is still inside its callback confirmation window",
        )
        return (
            "prospecting.dial_session_recovery_preserved",
            "Coordinator retained a recent provider dispatch without duplicating the call",
        )

    reason = (
        "Prepared provider start was abandoned before dispatch"
        if start_state in {None, "prepared"} and leg.status == "queued"
        else "Provider start confirmation expired without a provider call ID"
    )
    if intent is not None:
        intent.status = "failed"
        intent.consumed_at = now
        metadata["provider_start_state"] = (
            "failed" if start_state in {None, "prepared"} else "uncertain"
        )
        metadata["provider_start_recovered_at"] = now.isoformat()
        intent.intent_metadata = metadata
    if call is not None:
        call.status = "failed"
        call.ended_at = now
        call_metadata = dict(call.call_metadata or {})
        call_metadata["provider_start_recovery_reason"] = reason
        call.call_metadata = call_metadata
    leg.status = "failed"
    leg.failed_at = now
    leg.completed_at = now
    leg.terminal_result = "technical_failure"
    leg.provider_error_message = reason
    session.state = "wrap_up"
    session.heartbeat_at = now
    recovery = dict(session.recovery_metadata)
    recovery["provider_start_recovered_at"] = now.isoformat()
    recovery["provider_start_recovery_reason"] = reason
    session.recovery_metadata = recovery
    return (
        "prospecting.dial_session_provider_start_recovered",
        "Coordinator moved abandoned local provider-start evidence to human wrap-up",
    )


def can_manage_dialer(principal: Principal) -> bool:
    return PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys


def get_dialer_context(
    db: Session,
    principal: Principal,
    settings: Settings | None = None,
) -> DialerContextRead:
    active_settings = settings or get_settings()
    organization = db.scalar(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    user = db.scalar(
        select(User).where(
            User.id == principal.user_id,
            User.organization_id == principal.organization_id,
        )
    )
    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == principal.organization_id,
            ProspectingDialerProfile.user_id == principal.user_id,
        )
    )
    session = db.scalar(
        select(ProspectingDialSession).where(
            ProspectingDialSession.organization_id == principal.organization_id,
            ProspectingDialSession.caller_user_id == principal.user_id,
            ProspectingDialSession.ended_at.is_(None),
        )
    )
    legs = (
        list(
            db.scalars(
                select(ProspectingDialLeg)
                .where(
                    ProspectingDialLeg.organization_id == principal.organization_id,
                    ProspectingDialLeg.dial_session_id == session.id,
                    ProspectingDialLeg.completed_at.is_(None),
                )
                .order_by(ProspectingDialLeg.line_slot)
            )
        )
        if session is not None
        else []
    )

    blockers: list[str] = []
    if not active_settings.prospecting_native_dialer_enabled:
        blockers.append("Native prospecting dialer is disabled.")
    if organization is None or not organization.is_active:
        blockers.append("The Stonegate workspace is not active.")
    elif not organization.prospecting_dialer_enabled:
        blockers.append("The company prospecting dialer switch is off.")
    if user is None or not user.is_active:
        blockers.append("The current Stonegate user is not active.")
    elif not user.calling_enabled:
        blockers.append("Cold calling is not enabled for the current user.")
    if profile is None:
        blockers.append("A native dialer profile has not been configured.")
    elif profile.status != "active":
        blockers.append("The native dialer profile is not active.")
    elif profile.voice_line_id is None:
        blockers.append("A native dialer voice line has not been assigned.")
    else:
        line = dialer_voice_line(db, profile)
        if line is None or line.status != "active":
            blockers.append("The assigned native dialer voice line is not active.")
        elif (
            line.department_key != "acquisitions"
            or line.purpose_key != PROSPECTING_VOICE_LINE_PURPOSE
        ):
            blockers.append("Assign a dedicated acquisitions prospecting-outbound voice line.")
    if session is not None:
        campaign = db.scalar(
            select(Campaign).where(
                Campaign.id == session.campaign_id,
                Campaign.organization_id == principal.organization_id,
            )
        )
        if campaign is None or campaign.status != "active":
            blockers.append("The active dialer campaign is unavailable.")
        elif not campaign.prospecting_dialer_enabled:
            blockers.append("The active campaign prospecting dialer switch is off.")

    return DialerContextRead(
        feature_enabled=active_settings.prospecting_native_dialer_enabled,
        configured_line_cap=active_settings.prospecting_native_dialer_max_lines,
        implemented_line_cap=active_settings.prospecting_native_dialer_implemented_line_cap,
        effective_line_cap=active_settings.prospecting_native_dialer_effective_line_cap,
        can_manage=can_manage_dialer(principal),
        profile=(
            dialer_profile_read(db, profile, active_settings) if profile is not None else None
        ),
        active_session=dial_session_read(session) if session is not None else None,
        active_legs=[dial_leg_read(leg) for leg in legs],
        blockers=blockers,
    )


def list_dialer_profiles(
    db: Session,
    principal: Principal,
    settings: Settings | None = None,
) -> list[ProspectingDialerProfileRead]:
    active_settings = settings or get_settings()
    profiles = list(
        db.scalars(
            select(ProspectingDialerProfile)
            .join(User, User.id == ProspectingDialerProfile.user_id)
            .where(ProspectingDialerProfile.organization_id == principal.organization_id)
            .order_by(User.display_name, ProspectingDialerProfile.created_at)
        )
    )
    return [dialer_profile_read(db, profile, active_settings) for profile in profiles]


def upsert_dialer_profile(
    db: Session,
    principal: Principal,
    user_id: UUID,
    payload: ProspectingDialerProfileUpsert,
    settings: Settings | None = None,
) -> ProspectingDialerProfileRead | None:
    active_settings = settings or get_settings()
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == principal.organization_id,
            User.is_active.is_(True),
        )
    )
    if user is None:
        return None
    if not user.calling_enabled:
        raise ValueError("Enable cold calling for this user before configuring a dialer profile.")

    voice_line: VoiceLine | None = None
    if payload.voice_line_id is not None:
        voice_line = db.scalar(
            select(VoiceLine).where(
                VoiceLine.id == payload.voice_line_id,
                VoiceLine.organization_id == principal.organization_id,
            )
        )
        if voice_line is None:
            raise ValueError("The selected voice line is not available in this workspace.")
        if voice_line.status != "active":
            raise ValueError("The selected voice line must be active.")
        if (
            voice_line.department_key != "acquisitions"
            or voice_line.purpose_key != PROSPECTING_VOICE_LINE_PURPOSE
        ):
            raise ValueError(
                "The native dialer requires a dedicated acquisitions prospecting-outbound line."
            )

    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.organization_id == principal.organization_id,
            ProspectingDialerProfile.user_id == user_id,
        )
    )
    previous = dialer_profile_snapshot(profile) if profile is not None else None
    if profile is None:
        profile = ProspectingDialerProfile(
            organization_id=principal.organization_id,
            user_id=user.id,
            created_by_user_id=principal.user_id,
        )
        db.add(profile)
    profile.voice_line_id = voice_line.id if voice_line is not None else None
    profile.status = payload.status
    profile.default_line_count = payload.default_line_count
    profile.max_line_count = payload.max_line_count
    profile.recording_policy = payload.recording_policy.strip()
    profile.daily_dial_limit = payload.daily_dial_limit
    profile.daily_spend_limit_cents = payload.daily_spend_limit_cents
    profile.profile_metadata = dict(payload.metadata)
    profile.updated_by_user_id = principal.user_id
    db.flush()

    add_audit(
        db,
        principal,
        action="prospecting.dialer_profile_upserted",
        entity_type="prospecting_dialer_profile",
        entity_id=profile.id,
        previous=previous,
        new=dialer_profile_snapshot(profile),
        reason="Native prospecting dialer profile updated",
    )
    db.commit()
    return dialer_profile_read(db, profile, active_settings)


def dialer_profile_read(
    db: Session,
    profile: ProspectingDialerProfile,
    settings: Settings,
) -> ProspectingDialerProfileRead:
    user = db.scalar(
        select(User).where(
            User.id == profile.user_id,
            User.organization_id == profile.organization_id,
        )
    )
    if user is None:
        raise ValueError("Dialer profile references a user outside its workspace.")
    organization = db.scalar(select(Organization).where(Organization.id == profile.organization_id))
    if organization is None:
        raise ValueError("Dialer profile organization no longer exists.")
    voice_line = dialer_voice_line(db, profile)
    voice_line_limit = (
        voice_line.prospecting_dialer_max_concurrent_legs if voice_line is not None else 1
    )
    effective_line_count = min(
        profile.default_line_count,
        profile.max_line_count,
        organization.prospecting_dialer_max_concurrent_legs,
        voice_line_limit,
        settings.prospecting_native_dialer_effective_line_cap,
    )
    return ProspectingDialerProfileRead(
        id=profile.id,
        organization_id=profile.organization_id,
        user_id=profile.user_id,
        user_name=user.display_name,
        user_email=user.email,
        user_is_active=user.is_active,
        user_calling_enabled=user.calling_enabled,
        voice_line_id=profile.voice_line_id,
        voice_line_label=voice_line.label if voice_line is not None else None,
        voice_line_number=voice_line.phone_number if voice_line is not None else None,
        status=cast(DialerProfileStatus, profile.status),
        default_line_count=profile.default_line_count,
        max_line_count=profile.max_line_count,
        effective_line_count=effective_line_count,
        recording_policy=profile.recording_policy,
        daily_dial_limit=profile.daily_dial_limit,
        daily_spend_limit_cents=profile.daily_spend_limit_cents,
        metadata=dict(profile.profile_metadata),
        created_by_user_id=profile.created_by_user_id,
        updated_by_user_id=profile.updated_by_user_id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def dialer_voice_line(
    db: Session,
    profile: ProspectingDialerProfile,
) -> VoiceLine | None:
    if profile.voice_line_id is None:
        return None
    return db.scalar(
        select(VoiceLine).where(
            VoiceLine.id == profile.voice_line_id,
            VoiceLine.organization_id == profile.organization_id,
        )
    )


def dial_session_read(session: ProspectingDialSession) -> ProspectingDialSessionRead:
    metadata = dict(session.session_metadata or {})
    return ProspectingDialSessionRead(
        id=session.id,
        organization_id=session.organization_id,
        dialer_profile_id=session.dialer_profile_id,
        caller_user_id=session.caller_user_id,
        campaign_id=session.campaign_id,
        cohort_id=session.cohort_id,
        prospect_calling_batch_id=session.prospect_calling_batch_id,
        voice_line_id=session.voice_line_id,
        current_prospect_id=session.current_prospect_id,
        current_batch_entry_id=session.current_batch_entry_id,
        current_attempt_id=session.current_attempt_id,
        state=cast(DialerSessionState, session.state),
        requested_line_count=session.requested_line_count,
        effective_line_count=session.effective_line_count,
        organization_line_limit=session.organization_line_limit,
        va_line_limit=session.va_line_limit,
        campaign_line_limit=session.campaign_line_limit,
        voice_line_limit=session.voice_line_limit,
        feature_line_limit=session.feature_line_limit,
        lease_expires_at=session.lease_expires_at,
        started_at=session.started_at,
        paused_at=session.paused_at,
        resumed_at=session.resumed_at,
        heartbeat_at=session.heartbeat_at,
        ended_at=session.ended_at,
        stop_reason=session.stop_reason,
        pause_after_current=metadata.get("pause_after_current") is True,
        stop_after_current=metadata.get("stop_after_current") is True,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def dial_leg_read(leg: ProspectingDialLeg) -> ProspectingDialLegRead:
    return ProspectingDialLegRead(
        id=leg.id,
        organization_id=leg.organization_id,
        dial_session_id=leg.dial_session_id,
        prospect_id=leg.prospect_id,
        batch_entry_id=leg.batch_entry_id,
        attempt_id=leg.attempt_id,
        contact_point_id=leg.contact_point_id,
        voice_line_id=leg.voice_line_id,
        call_record_id=leg.call_record_id,
        line_slot=leg.line_slot,
        recipient=leg.recipient,
        provider=leg.provider,
        provider_call_id=leg.provider_call_id,
        status=cast(DialerLegStatus, leg.status),
        queued_at=leg.queued_at,
        dialing_at=leg.dialing_at,
        ringing_at=leg.ringing_at,
        answered_at=leg.answered_at,
        connected_at=leg.connected_at,
        cancelled_at=leg.cancelled_at,
        failed_at=leg.failed_at,
        completed_at=leg.completed_at,
        answer_classification=leg.answer_classification,
        party_classification=leg.party_classification,
        terminal_result=leg.terminal_result,
        provider_error_code=leg.provider_error_code,
        provider_error_message=leg.provider_error_message,
        cancellation_reason=leg.cancellation_reason,
        created_at=leg.created_at,
        updated_at=leg.updated_at,
    )


def record_dial_provider_event(
    db: Session,
    *,
    organization_id: UUID,
    provider: str,
    external_event_id: str,
    event_type: str,
    payload: dict[str, Any],
    dial_leg: ProspectingDialLeg | None = None,
    target_status: str | None = None,
    provider_sequence_number: int | None = None,
    occurred_at: datetime | None = None,
    signature_verified: bool = False,
    signature: str | None = None,
) -> tuple[ProspectingProviderEvent, bool]:
    normalized_provider = provider.strip().lower()
    normalized_event_id = external_event_id.strip()
    if not normalized_provider or not normalized_event_id:
        raise ValueError("Provider and external event ID are required.")
    if target_status is not None and target_status not in DIAL_LEG_STATUSES:
        raise ValueError(f"Unsupported dial-leg status: {target_status}")
    if target_status is not None and dial_leg is None:
        raise ValueError("A dial leg is required for provider state changes.")
    if target_status is not None and not signature_verified:
        raise ValueError("A verified provider signature is required for state changes.")

    locked_dial_leg: ProspectingDialLeg | None = None
    if dial_leg is not None:
        if dial_leg.organization_id != organization_id:
            raise ValueError("Provider event and dial leg must belong to the same workspace.")
        # All dialer mutations lock the parent session before its leg. Keeping provider
        # callbacks on that same order prevents a callback/session-control deadlock.
        locked_session = db.scalar(
            select(ProspectingDialSession)
            .where(
                ProspectingDialSession.id == dial_leg.dial_session_id,
                ProspectingDialSession.organization_id == organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_session is None:
            raise ValueError("The provider event dial session no longer exists.")
        locked_dial_leg = db.scalar(
            select(ProspectingDialLeg)
            .where(
                ProspectingDialLeg.id == dial_leg.id,
                ProspectingDialLeg.organization_id == organization_id,
                ProspectingDialLeg.dial_session_id == locked_session.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_dial_leg is None:
            raise ValueError("The provider event dial leg no longer exists in this workspace.")

    existing = db.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == organization_id,
            ProspectingProviderEvent.provider == normalized_provider,
            ProspectingProviderEvent.external_event_id == normalized_event_id,
        )
    )
    if existing is not None:
        return existing, False

    now = datetime.now(UTC)
    event = ProspectingProviderEvent(
        organization_id=organization_id,
        dial_session_id=(locked_dial_leg.dial_session_id if locked_dial_leg is not None else None),
        dial_leg_id=locked_dial_leg.id if locked_dial_leg is not None else None,
        batch_entry_id=locked_dial_leg.batch_entry_id if locked_dial_leg is not None else None,
        attempt_id=locked_dial_leg.attempt_id if locked_dial_leg is not None else None,
        provider=normalized_provider,
        external_event_id=normalized_event_id,
        event_type=event_type.strip(),
        processing_status="stored",
        provider_call_id=(
            locked_dial_leg.provider_call_id if locked_dial_leg is not None else None
        ),
        provider_sequence_number=provider_sequence_number,
        occurred_at=as_utc(occurred_at) if occurred_at is not None else None,
        signature_verified=signature_verified,
        signature_fingerprint=(
            hashlib.sha256(signature.encode("utf-8")).hexdigest() if signature else None
        ),
        payload_sha256=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
        payload=dict(payload),
        retry_count=0,
        received_at=now,
    )
    db.add(event)

    applied = False
    if locked_dial_leg is not None and target_status is not None:
        applied, processing_status = advance_dial_leg_provider_state(
            locked_dial_leg,
            target_status=target_status,
            provider_sequence_number=provider_sequence_number,
            occurred_at=occurred_at or now,
        )
        if applied:
            reconcile_dial_session_from_leg(
                db,
                locked_dial_leg,
                now=occurred_at or now,
            )
        event.processing_status = processing_status
        event.processed_at = now
    db.flush()
    return event, applied


def advance_dial_leg_provider_state(
    leg: ProspectingDialLeg,
    *,
    target_status: str,
    provider_sequence_number: int | None,
    occurred_at: datetime,
) -> tuple[bool, str]:
    if target_status not in DIAL_LEG_STATUSES:
        raise ValueError(f"Unsupported dial-leg status: {target_status}")
    normalized_occurred_at = as_utc(occurred_at)
    normalized_last_event_at = (
        as_utc(leg.last_provider_event_at) if leg.last_provider_event_at is not None else None
    )
    if (
        provider_sequence_number is not None
        and normalized_last_event_at is not None
        and provider_sequence_number <= leg.last_provider_event_sequence
    ):
        return False, "ignored_stale"
    if normalized_last_event_at is not None and normalized_occurred_at < normalized_last_event_at:
        return False, "ignored_stale"
    if leg.status in DIAL_LEG_TERMINAL_STATUSES:
        return False, "ignored_terminal"
    if leg.status in DIAL_LEG_TERMINAL_REGRESSIONS.get(target_status, set()):
        return False, "ignored_regression"
    if (
        target_status not in DIAL_LEG_TERMINAL_STATUSES
        and DIAL_LEG_PROGRESS_RANK[target_status] < DIAL_LEG_PROGRESS_RANK[leg.status]
    ):
        return False, "ignored_regression"

    leg.status = target_status
    leg.last_provider_event_at = normalized_occurred_at
    if provider_sequence_number is not None:
        leg.last_provider_event_sequence = provider_sequence_number
    if target_status == "dialing":
        leg.dialing_at = leg.dialing_at or normalized_occurred_at
    elif target_status == "ringing":
        leg.ringing_at = leg.ringing_at or normalized_occurred_at
    elif target_status == "answered":
        leg.answered_at = leg.answered_at or normalized_occurred_at
    elif target_status == "connected":
        leg.answered_at = leg.answered_at or normalized_occurred_at
        leg.connected_at = leg.connected_at or normalized_occurred_at
    elif target_status == "cancelled":
        leg.cancelled_at = leg.cancelled_at or normalized_occurred_at
    elif target_status == "failed":
        leg.failed_at = leg.failed_at or normalized_occurred_at
    if target_status in DIAL_LEG_TERMINAL_STATUSES:
        leg.completed_at = leg.completed_at or normalized_occurred_at
        leg.terminal_result = leg.terminal_result or target_status
    return True, "processed"


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def dialer_profile_snapshot(profile: ProspectingDialerProfile) -> dict[str, object]:
    return {
        "user_id": str(profile.user_id),
        "voice_line_id": str(profile.voice_line_id) if profile.voice_line_id else None,
        "status": profile.status,
        "default_line_count": profile.default_line_count,
        "max_line_count": profile.max_line_count,
        "recording_policy": profile.recording_policy,
        "daily_dial_limit": profile.daily_dial_limit,
        "daily_spend_limit_cents": profile.daily_spend_limit_cents,
        "metadata": dict(profile.profile_metadata),
    }


def add_audit(
    db: Session,
    principal: Principal,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    previous: dict[str, object] | None,
    new: dict[str, object],
    reason: str,
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            previous_value=previous,
            new_value=new,
            reason=reason,
        )
    )
