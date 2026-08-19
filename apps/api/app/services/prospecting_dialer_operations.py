import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.integrations.twilio_voice_calls import get_twilio_voice_call_provider
from app.integrations.voice_call_provider import VoiceCallProvider, VoiceCallProviderError
from app.models.foundation import (
    AuditEvent,
    CallRecord,
    Campaign,
    Organization,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingInboundCallback,
    Task,
    User,
    VoiceLine,
)
from app.schemas.prospecting import (
    ProspectingCampaignDialerControlRead,
    ProspectingDialerCallerRead,
    ProspectingDialerHealthSummaryRead,
    ProspectingDialerOperationalErrorRead,
    ProspectingDialerOperationsRead,
    ProspectingDialSessionOperationRead,
    ProspectingEligibleVoiceLineRead,
    ProspectingManagerSessionRecoveryCommand,
    ProspectingManagerSessionStopCommand,
)
from app.services.operations import get_worker_readiness
from app.services.prospecting_dialer import (
    DIAL_LEG_TERMINAL_STATUSES,
    TERMINAL_DIAL_SESSION_STATES,
    advance_dial_leg_provider_state,
    current_session_leg,
    dial_session_read,
    list_dialer_profiles,
    reconcile_dial_session_from_leg,
    release_unstarted_reservation,
    terminate_session,
)

PROSPECTING_LINE_PURPOSE = "prospecting_outbound"
ACTIVE_CALLBACK_STATUSES = ("received", "routing", "ringing", "answered", "voicemail")
ACTIVE_TASK_STATUSES = ("open", "in_progress")
MANAGER_COMMAND_HISTORY_LIMIT = 20
PROVIDER_TO_LEG_STATUS = {
    "queued": "dialing",
    "initiated": "dialing",
    "ringing": "ringing",
    "in-progress": "connected",
    "answered": "connected",
    "completed": "completed",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "busy": "busy",
    "no-answer": "no_answer",
    "failed": "failed",
}


class ProspectingDialerOperationsConflictError(RuntimeError):
    pass


def get_prospecting_dialer_operations(
    db: Session,
    principal: Principal,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> ProspectingDialerOperationsRead:
    active_settings = settings or get_settings()
    observed_at = _as_utc(now or datetime.now(UTC))
    organization = db.scalar(
        select(Organization).where(Organization.id == principal.organization_id)
    )
    if organization is None:
        raise ValueError("Stonegate workspace was not found.")

    callers = list(
        db.scalars(
            select(User)
            .where(User.organization_id == principal.organization_id)
            .order_by(User.is_active.desc(), User.display_name, User.email)
        )
    )
    lines = list(
        db.scalars(
            select(VoiceLine)
            .where(
                VoiceLine.organization_id == principal.organization_id,
                VoiceLine.department_key == "acquisitions",
                VoiceLine.purpose_key == PROSPECTING_LINE_PURPOSE,
                VoiceLine.status == "active",
            )
            .order_by(VoiceLine.status.desc(), VoiceLine.label, VoiceLine.id)
        )
    )
    campaigns = list(
        db.scalars(
            select(Campaign)
            .where(Campaign.organization_id == principal.organization_id)
            .order_by(Campaign.status.desc(), Campaign.name, Campaign.id)
        )
    )
    sessions = list(
        db.scalars(
            select(ProspectingDialSession)
            .where(
                ProspectingDialSession.organization_id == principal.organization_id,
                ProspectingDialSession.ended_at.is_(None),
            )
            .order_by(ProspectingDialSession.heartbeat_at.asc(), ProspectingDialSession.id)
        )
    )
    stale_before = observed_at - timedelta(
        seconds=active_settings.prospecting_native_dialer_stale_after_seconds
    )
    session_reads = [
        _session_operation_read(db, session, stale_before=stale_before) for session in sessions
    ]
    active_leg_count = int(
        db.scalar(
            select(func.count(ProspectingDialLeg.id)).where(
                ProspectingDialLeg.organization_id == principal.organization_id,
                ProspectingDialLeg.completed_at.is_(None),
            )
        )
        or 0
    )
    callback_waiting_count = int(
        db.scalar(
            select(func.count(ProspectingInboundCallback.id)).where(
                ProspectingInboundCallback.organization_id == principal.organization_id,
                ProspectingInboundCallback.status.in_(ACTIVE_CALLBACK_STATUSES),
            )
        )
        or 0
    )
    missed_callback_task_count = int(
        db.scalar(
            select(func.count(Task.id)).where(
                Task.organization_id == principal.organization_id,
                Task.task_type == "missed_prospecting_callback",
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
        or 0
    )
    # OperationalFailure is intentionally service-global and has no organization key.
    # Do not leak another workspace's worker failures into this manager view.  The
    # actionable recovery count is therefore derived only from this organization's
    # sessions and legs.
    open_recovery_failure_count = sum(
        item.health_status in {"attention", "reconnecting"} for item in session_reads
    )
    readiness = get_worker_readiness(db, active_settings)
    oldest_heartbeat = min((_as_utc(session.heartbeat_at) for session in sessions), default=None)

    return ProspectingDialerOperationsRead(
        feature_enabled=active_settings.prospecting_native_dialer_enabled,
        company_enabled=organization.prospecting_dialer_enabled,
        configured_line_cap=active_settings.prospecting_native_dialer_max_lines,
        implemented_line_cap=active_settings.prospecting_native_dialer_implemented_line_cap,
        effective_line_cap=active_settings.prospecting_native_dialer_effective_line_cap,
        callers=[
            ProspectingDialerCallerRead(
                id=user.id,
                display_name=user.display_name,
                email=user.email,
                is_active=user.is_active,
                calling_enabled=user.calling_enabled,
            )
            for user in callers
        ],
        profiles=list_dialer_profiles(db, principal, active_settings),
        eligible_lines=[
            ProspectingEligibleVoiceLineRead(
                id=line.id,
                label=line.label,
                phone_number=line.phone_number,
                status=line.status,
                assigned_user_id=line.assigned_user_id,
                fallback_user_id=line.fallback_user_id,
                assigned_team_id=line.assigned_team_id,
                ring_strategy=line.ring_strategy,
                missed_call_action=line.missed_call_action,
                max_concurrent_legs=line.prospecting_dialer_max_concurrent_legs,
            )
            for line in lines
        ],
        campaigns=[
            ProspectingCampaignDialerControlRead(
                id=campaign.id,
                name=campaign.name,
                code=campaign.code,
                status=campaign.status,
                enabled=campaign.prospecting_dialer_enabled,
                max_concurrent_legs=campaign.prospecting_dialer_max_concurrent_legs,
            )
            for campaign in campaigns
        ],
        sessions=session_reads,
        health=ProspectingDialerHealthSummaryRead(
            active_session_count=len(sessions),
            stale_session_count=sum(item.health_status == "stale" for item in session_reads),
            reconnecting_session_count=sum(
                item.health_status == "reconnecting" for item in session_reads
            ),
            active_leg_count=active_leg_count,
            callback_waiting_count=callback_waiting_count,
            missed_callback_task_count=missed_callback_task_count,
            open_recovery_failure_count=open_recovery_failure_count,
            oldest_heartbeat_at=oldest_heartbeat,
            worker_status=readiness.status,
            worker_heartbeat_at=readiness.heartbeat_at,
        ),
        recent_errors=_recent_operational_errors(db, principal.organization_id),
    )


def manager_stop_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingManagerSessionStopCommand,
    *,
    provider: VoiceCallProvider | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionOperationRead | None:
    observed_at = _as_utc(now or datetime.now(UTC))
    session = _locked_manager_session(db, principal, session_id)
    if session is None:
        return None
    replayed = _validate_or_begin_manager_command(
        session,
        key=payload.idempotency_key,
        kind="stop",
        value=payload.mode,
        reason=payload.reason,
        now=observed_at,
    )
    if replayed:
        return _session_operation_read(
            db,
            session,
            stale_before=_manager_stale_before(observed_at),
        )

    previous = _safe_session_snapshot(session)
    leg = current_session_leg(db, session, lock=True)
    provider_call_id: str | None = None
    call_record_id: UUID | None = None
    previous_leg_status: str | None = None

    if session.state in TERMINAL_DIAL_SESSION_STATES:
        pass
    elif leg is None:
        terminate_session(session, state="stopped", now=observed_at, reason=payload.reason)
    elif leg.status == "queued" and not leg.provider_call_id and not leg.call_record_id:
        release_unstarted_reservation(
            db,
            session,
            leg,
            now=observed_at,
            reason="manager_stop",
        )
        terminate_session(session, state="stopped", now=observed_at, reason=payload.reason)
    elif payload.mode == "cancel_unanswered" and leg.status in {
        "dialing",
        "ringing",
        "cancelling",
    }:
        call = (
            db.get(CallRecord, leg.call_record_id) if leg.call_record_id is not None else None
        )
        provider_call_id = (
            (call.child_provider_call_id or call.provider_call_id) if call is not None else None
        ) or leg.provider_call_id
        if not provider_call_id:
            _request_safe_drain(session, payload.reason, observed_at)
        else:
            previous_leg_status = leg.status
            leg.status = "cancelling"
            leg.cancellation_reason = payload.reason
            call_record_id = call.id if call is not None else None
            _request_safe_drain(session, payload.reason, observed_at)
            db.flush()
    else:
        _request_safe_drain(session, payload.reason, observed_at)

    _add_manager_audit(
        db,
        principal,
        session,
        action="prospecting.manager_session_stop_requested",
        previous=previous,
        reason=payload.reason,
        extra={"mode": payload.mode},
    )
    if provider_call_id is None:
        _complete_manager_command(session, payload.idempotency_key, observed_at)
        db.commit()
        return _session_operation_read(
            db,
            session,
            stale_before=_manager_stale_before(observed_at),
        )

    db.commit()
    try:
        result = (provider or get_twilio_voice_call_provider()).cancel(provider_call_id)
    except VoiceCallProviderError as exc:
        session = _locked_manager_session(db, principal, session_id)
        if session is not None:
            leg = current_session_leg(db, session, lock=True)
            if leg is not None and leg.status == "cancelling" and previous_leg_status:
                leg.status = previous_leg_status
                leg.provider_error_message = _safe_error_message(str(exc))
            _fail_manager_command(session, payload.idempotency_key, observed_at)
            db.commit()
        raise

    session = _locked_manager_session(db, principal, session_id)
    if session is None:
        return None
    leg = current_session_leg(db, session, lock=True)
    if leg is None:
        raise ProspectingDialerOperationsConflictError(
            "The active dial record changed during provider cancellation."
        )
    if result.sid != provider_call_id:
        raise ProspectingDialerOperationsConflictError(
            "The provider response did not match the active call."
        )
    applied, _ = advance_dial_leg_provider_state(
        leg,
        target_status="cancelled",
        provider_sequence_number=None,
        occurred_at=observed_at,
    )
    if applied:
        reconcile_dial_session_from_leg(db, leg, now=observed_at)
    if call_record_id is not None:
        call = db.get(CallRecord, call_record_id)
        if call is not None and call.organization_id == principal.organization_id:
            call.status = "cancelled"
            call.ended_at = call.ended_at or observed_at
    _complete_manager_command(session, payload.idempotency_key, observed_at)
    db.commit()
    return _session_operation_read(
        db,
        session,
        stale_before=_manager_stale_before(observed_at),
    )


def manager_recover_dial_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
    payload: ProspectingManagerSessionRecoveryCommand,
    *,
    provider: VoiceCallProvider | None = None,
    now: datetime | None = None,
) -> ProspectingDialSessionOperationRead | None:
    observed_at = _as_utc(now or datetime.now(UTC))
    session = _locked_manager_session(db, principal, session_id)
    if session is None:
        return None
    replayed = _validate_or_begin_manager_command(
        session,
        key=payload.idempotency_key,
        kind="recover",
        value=payload.action,
        reason=payload.reason,
        now=observed_at,
    )
    if replayed:
        return _session_operation_read(
            db,
            session,
            stale_before=_manager_stale_before(observed_at),
        )
    previous = _safe_session_snapshot(session)
    leg = current_session_leg(db, session, lock=True)

    if payload.action == "release_orphan":
        if (
            leg is None
            or leg.status != "queued"
            or leg.provider_call_id is not None
            or leg.call_record_id is not None
        ):
            raise ProspectingDialerOperationsConflictError(
                "Only an untouched queued reservation can be released."
            )
        release_unstarted_reservation(
            db,
            session,
            leg,
            now=observed_at,
            reason="manager_recovery",
        )
        terminate_session(session, state="failed", now=observed_at, reason=payload.reason)
    elif payload.action == "mark_failed":
        if leg is not None and leg.status not in DIAL_LEG_TERMINAL_STATUSES:
            raise ProspectingDialerOperationsConflictError(
                "An active provider call cannot be marked failed. Reconcile or safely stop it."
            )
        terminate_session(session, state="failed", now=observed_at, reason=payload.reason)
    else:
        if leg is None:
            raise ProspectingDialerOperationsConflictError(
                "This session has no active dial record to reconcile."
            )
        call = db.get(CallRecord, leg.call_record_id) if leg.call_record_id else None
        provider_call_id = (
            (call.child_provider_call_id or call.provider_call_id) if call is not None else None
        ) or leg.provider_call_id
        if not provider_call_id:
            raise ProspectingDialerOperationsConflictError(
                "No provider call exists. Use release_orphan for an untouched reservation."
            )
        leg_id = leg.id
        call_id = call.id if call is not None else None
        db.commit()
        try:
            result = (provider or get_twilio_voice_call_provider()).fetch(provider_call_id)
        except VoiceCallProviderError:
            session = _locked_manager_session(db, principal, session_id)
            if session is not None:
                _fail_manager_command(session, payload.idempotency_key, observed_at)
                db.commit()
            raise
        session = _locked_manager_session(db, principal, session_id)
        if session is None:
            return None
        leg = current_session_leg(db, session, lock=True)
        if leg is None or leg.id != leg_id or result.sid != provider_call_id:
            _fail_manager_command(session, payload.idempotency_key, observed_at)
            db.commit()
            raise ProspectingDialerOperationsConflictError(
                "The active dial record changed during provider reconciliation."
            )
        target_status = PROVIDER_TO_LEG_STATUS.get(result.status.strip().lower())
        if target_status is None:
            _fail_manager_command(session, payload.idempotency_key, observed_at)
            db.commit()
            raise ProspectingDialerOperationsConflictError(
                "The provider returned an unsupported call state."
            )
        applied, _ = advance_dial_leg_provider_state(
            leg,
            target_status=target_status,
            provider_sequence_number=None,
            occurred_at=observed_at,
        )
        if applied:
            reconcile_dial_session_from_leg(db, leg, now=observed_at)
        if call_id is not None:
            call = db.get(CallRecord, call_id)
            if call is not None and call.organization_id == principal.organization_id:
                call.status = target_status
                if target_status in {"answered", "connected"}:
                    call.answered_at = call.answered_at or observed_at
                if target_status in DIAL_LEG_TERMINAL_STATUSES:
                    call.ended_at = call.ended_at or observed_at

    _complete_manager_command(session, payload.idempotency_key, observed_at)
    _add_manager_audit(
        db,
        principal,
        session,
        action="prospecting.manager_session_recovered",
        previous=previous,
        reason=payload.reason,
        extra={"action": payload.action},
    )
    db.commit()
    return _session_operation_read(
        db,
        session,
        stale_before=_manager_stale_before(observed_at),
    )


def _session_operation_read(
    db: Session,
    session: ProspectingDialSession,
    *,
    stale_before: datetime,
) -> ProspectingDialSessionOperationRead:
    caller = db.scalar(
        select(User).where(
            User.organization_id == session.organization_id,
            User.id == session.caller_user_id,
        )
    )
    campaign = db.scalar(
        select(Campaign).where(
            Campaign.organization_id == session.organization_id,
            Campaign.id == session.campaign_id,
        )
    )
    line = (
        db.scalar(
            select(VoiceLine).where(
                VoiceLine.organization_id == session.organization_id,
                VoiceLine.id == session.voice_line_id,
            )
        )
        if session.voice_line_id
        else None
    )
    leg = current_session_leg(db, session)
    heartbeat = _as_utc(session.heartbeat_at)
    health_status: Literal["healthy", "stale", "reconnecting", "attention"]
    if heartbeat < _as_utc(stale_before):
        health_status = "stale"
    elif session.state == "reconnecting":
        health_status = "reconnecting"
    elif session.state in {"failed", "expired"} or (
        leg is not None and leg.provider_error_message
    ):
        health_status = "attention"
    else:
        health_status = "healthy"
    return ProspectingDialSessionOperationRead(
        session=dial_session_read(session),
        caller_name=caller.display_name if caller is not None else "Unavailable caller",
        caller_email=caller.email if caller is not None else "",
        campaign_name=campaign.name if campaign is not None else "Unavailable campaign",
        voice_line_label=line.label if line is not None else None,
        current_leg_status=leg.status if leg is not None else None,
        health_status=health_status,
    )


def _recent_operational_errors(
    db: Session,
    organization_id: UUID,
) -> list[ProspectingDialerOperationalErrorRead]:
    errors: list[ProspectingDialerOperationalErrorRead] = []
    legs = list(
        db.scalars(
            select(ProspectingDialLeg)
            .where(
                ProspectingDialLeg.organization_id == organization_id,
                ProspectingDialLeg.provider_error_message.is_not(None),
            )
            .order_by(ProspectingDialLeg.updated_at.desc(), ProspectingDialLeg.id.desc())
            .limit(20)
        )
    )
    for leg in legs:
        session = db.scalar(
            select(ProspectingDialSession).where(
                ProspectingDialSession.organization_id == organization_id,
                ProspectingDialSession.id == leg.dial_session_id,
            )
        )
        errors.append(
            ProspectingDialerOperationalErrorRead(
                occurred_at=leg.updated_at,
                code=leg.provider_error_code or "provider_call_error",
                message=_safe_error_message(leg.provider_error_message or "Provider call failed."),
                session_id=leg.dial_session_id,
                caller_user_id=session.caller_user_id if session is not None else None,
                campaign_id=session.campaign_id if session is not None else None,
                recoverable=leg.status not in DIAL_LEG_TERMINAL_STATUSES,
            )
        )
    sessions = list(
        db.scalars(
            select(ProspectingDialSession)
            .where(
                ProspectingDialSession.organization_id == organization_id,
                ProspectingDialSession.state.in_(("failed", "expired", "reconnecting")),
            )
            .order_by(
                ProspectingDialSession.updated_at.desc(),
                ProspectingDialSession.id.desc(),
            )
            .limit(20)
        )
    )
    for session in sessions:
        errors.append(
            ProspectingDialerOperationalErrorRead(
                occurred_at=session.updated_at,
                code=f"session_{session.state}",
                message=_safe_error_message(
                    session.stop_reason or "Dialer session requires manager attention."
                ),
                session_id=session.id,
                caller_user_id=session.caller_user_id,
                campaign_id=session.campaign_id,
                recoverable=session.state in {"reconnecting", "expired"},
            )
        )
    errors.sort(key=lambda item: _as_utc(item.occurred_at), reverse=True)
    return errors[:20]


def _locked_manager_session(
    db: Session,
    principal: Principal,
    session_id: UUID,
) -> ProspectingDialSession | None:
    return db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.id == session_id,
            ProspectingDialSession.organization_id == principal.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _request_safe_drain(
    session: ProspectingDialSession,
    reason: str,
    now: datetime,
) -> None:
    metadata = dict(session.session_metadata or {})
    metadata["stop_after_current"] = True
    metadata["manager_stop_requested_at"] = now.isoformat()
    session.session_metadata = metadata
    session.stop_reason = reason[:255]


def _manager_command_history(session: ProspectingDialSession) -> list[dict[str, str]]:
    raw = (session.session_metadata or {}).get("manager_commands")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)][-MANAGER_COMMAND_HISTORY_LIMIT:]


def _validate_or_begin_manager_command(
    session: ProspectingDialSession,
    *,
    key: str,
    kind: str,
    value: str,
    reason: str,
    now: datetime,
) -> bool:
    history = _manager_command_history(session)
    existing = next((item for item in history if item.get("key") == key), None)
    if existing is not None:
        if (
            existing.get("kind") != kind
            or existing.get("value") != value
            or existing.get("reason") != reason
        ):
            raise ProspectingDialerOperationsConflictError(
                "The idempotency key was already used for a different manager action."
            )
        status = existing.get("status")
        if status == "completed":
            return True
        if status == "pending":
            raise ProspectingDialerOperationsConflictError(
                "This manager action may still be in progress. Reconcile the session "
                "before issuing it again."
            )
        if status != "failed":
            raise ProspectingDialerOperationsConflictError(
                "The prior manager action has an unknown state and cannot be replayed safely."
            )
        # A provider-declared failure is known not to have completed the requested
        # operation.  Retrying the exact same command is deliberate and safe.
        retry_count = int(existing.get("retry_count") or "0") + 1
        existing["status"] = "pending"
        existing["retry_count"] = str(retry_count)
        existing["requested_at"] = now.isoformat()
        existing.pop("completed_at", None)
        metadata = dict(session.session_metadata or {})
        metadata["manager_commands"] = history[-MANAGER_COMMAND_HISTORY_LIMIT:]
        session.session_metadata = metadata
        return False
    history.append(
        {
            "key": key,
            "kind": kind,
            "value": value,
            "reason": reason,
            "status": "pending",
            "requested_at": now.isoformat(),
        }
    )
    metadata = dict(session.session_metadata or {})
    metadata["manager_commands"] = history[-MANAGER_COMMAND_HISTORY_LIMIT:]
    session.session_metadata = metadata
    return False


def _complete_manager_command(
    session: ProspectingDialSession,
    key: str,
    now: datetime,
) -> None:
    _set_manager_command_status(session, key, "completed", now)


def _fail_manager_command(
    session: ProspectingDialSession,
    key: str,
    now: datetime,
) -> None:
    _set_manager_command_status(session, key, "failed", now)


def _set_manager_command_status(
    session: ProspectingDialSession,
    key: str,
    status: str,
    now: datetime,
) -> None:
    history = _manager_command_history(session)
    for item in history:
        if item.get("key") == key:
            item["status"] = status
            item["completed_at"] = now.isoformat()
    metadata = dict(session.session_metadata or {})
    metadata["manager_commands"] = history[-MANAGER_COMMAND_HISTORY_LIMIT:]
    session.session_metadata = metadata


def _safe_session_snapshot(session: ProspectingDialSession) -> dict[str, object]:
    return {
        "state": session.state,
        "caller_user_id": str(session.caller_user_id),
        "campaign_id": str(session.campaign_id),
        "current_prospect_id": (
            str(session.current_prospect_id) if session.current_prospect_id else None
        ),
        "current_attempt_id": (
            str(session.current_attempt_id) if session.current_attempt_id else None
        ),
        "stop_after_current": bool(
            (session.session_metadata or {}).get("stop_after_current")
        ),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }


def _add_manager_audit(
    db: Session,
    principal: Principal,
    session: ProspectingDialSession,
    *,
    action: str,
    previous: dict[str, object],
    reason: str,
    extra: dict[str, object],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="prospecting_dial_session",
            entity_id=session.id,
            previous_value=previous,
            new_value={**_safe_session_snapshot(session), **extra},
            reason=reason,
        )
    )


def _safe_error_message(value: str) -> str:
    normalized = " ".join(value.strip().split())[:240] or "Dialer operation failed."
    normalized = re.sub(
        r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}",
        "[redacted]",
        normalized,
    )
    normalized = re.sub(
        r"(?i)\b(?:authorization|api[_ -]?key|auth[_ -]?token|access[_ -]?token|"
        r"token|secret|password|signature)\s*[:=]\s*[^\s,;]+",
        "[redacted]",
        normalized,
    )
    normalized = re.sub(
        r"(?i)\b(?:AC|CA|SK|RK|MG|SM)[A-Fa-f0-9]{20,}\b",
        "[provider-id]",
        normalized,
    )
    normalized = re.sub(
        r"(?i)([?&][A-Za-z0-9_.~-]+=)[^&\s]+",
        r"\1[redacted]",
        normalized,
    )
    normalized = re.sub(
        r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[email]",
        normalized,
    )
    normalized = re.sub(
        r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\w)",
        "[phone]",
        normalized,
    )
    normalized = re.sub(r"\b\d{7,}\b", "[redacted]", normalized)
    return normalized


def _manager_stale_before(now: datetime) -> datetime:
    return now - timedelta(
        seconds=get_settings().prospecting_native_dialer_stale_after_seconds
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
