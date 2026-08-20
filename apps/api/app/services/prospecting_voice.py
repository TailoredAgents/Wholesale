from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, principal_for_user
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_voice import (
    callback_url,
    create_voice_access_token,
    forwarded_outbound_screen_twiml,
    outbound_call_twiml,
)
from app.integrations.twilio_voice_calls import get_twilio_voice_call_provider
from app.integrations.voice_call_provider import (
    VoiceCallProvider,
    VoiceCallProviderError,
    VoiceCallResult,
)
from app.models.foundation import (
    AuditEvent,
    CallRecord,
    Prospect,
    ProspectCallingBatch,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectingAttempt,
    ProspectingDialerPilot,
    ProspectingDialerProfile,
    ProspectingDialLeg,
    ProspectingDialSession,
    ProspectingProviderEvent,
    User,
    VoiceCallIntent,
    VoiceLine,
)
from app.schemas.prospecting import (
    ProspectingBrowserVoiceLineRead,
    ProspectingBrowserVoiceSessionRead,
    ProspectingDialSessionLeaseCommand,
    ProspectingVoiceCallControl,
    ProspectingVoiceCallCreate,
    ProspectingVoiceCallRead,
)
from app.services.communication_compliance import format_e164
from app.services.prospecting_dialer import (
    DIAL_LEG_TERMINAL_STATUSES,
    ProspectingDialerConfigurationError,
    ProspectingDialerConflictError,
    advance_dial_leg_provider_state,
    as_utc,
    dial_leg_read,
    lock_expected_session_pilot,
    reconcile_dial_session_from_leg,
    reconcile_session_current_leg,
    record_dial_provider_event,
    release_unstarted_reservation,
    validate_in_flight_dial_leg_policy,
    validate_reserved_dial_leg_policy,
    validate_session_lease,
)

PROSPECTING_VOICE_LINE_PURPOSE = "prospecting_outbound"
PROSPECTING_BROWSER_CONNECTION_MODE = "browser_softphone"
PROSPECTING_CELLPHONE_CONNECTION_MODE = "staff_cellphone"
PROSPECTING_ACTIVE_SESSION_STATES = {
    "ready",
    "dialing",
}
PROVIDER_START_PREPARED = "prepared"
PROVIDER_START_DISPATCHING = "dispatching"
PROVIDER_START_STARTED = "started"
PROVIDER_START_FAILED = "failed"
PROVIDER_START_UNCERTAIN = "uncertain"
TWILIO_TO_DIAL_LEG_STATUS = {
    "queued": "dialing",
    "initiated": "dialing",
    "ringing": "ringing",
    "answered": "connected",
    "in-progress": "connected",
    "completed": "completed",
    "busy": "busy",
    "failed": "failed",
    "no-answer": "no_answer",
    "canceled": "cancelled",
    "cancelled": "cancelled",
}


class ProspectingVoiceConflictError(RuntimeError):
    pass


class ProspectingVoiceConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProspectingVoiceGraph:
    leg: ProspectingDialLeg
    session: ProspectingDialSession
    profile: ProspectingDialerProfile
    prospect: Prospect
    entry: ProspectCallingBatchEntry
    batch: ProspectCallingBatch
    attempt: ProspectingAttempt
    caller: User
    line: VoiceLine


def create_prospecting_browser_voice_session(
    db: Session,
    principal: Principal,
    dial_session_id: UUID,
    payload: ProspectingDialSessionLeaseCommand,
    *,
    settings: Settings | None = None,
) -> ProspectingBrowserVoiceSessionRead | None:
    """Issue one short-lived Voice SDK token for the exact active browser lease."""

    active_settings = settings or get_settings()
    require_native_dialer_enabled(active_settings)
    require_call_permission(principal)
    session = db.scalar(
        select(ProspectingDialSession)
        .where(
            ProspectingDialSession.id == dial_session_id,
            ProspectingDialSession.organization_id == principal.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None:
        return None
    if session.caller_user_id != principal.user_id:
        raise PermissionError("This dialer session belongs to another caller.")
    try:
        validate_session_lease(session, payload, now=datetime.now(UTC))
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc
    if session.state not in {"ready", "dialing", "ringing", "connected", "reconnecting"}:
        raise ProspectingVoiceConflictError(
            "The dialer session cannot initialize browser audio in its current state."
        )
    profile = db.scalar(
        select(ProspectingDialerProfile).where(
            ProspectingDialerProfile.id == session.dialer_profile_id,
            ProspectingDialerProfile.organization_id == principal.organization_id,
            ProspectingDialerProfile.user_id == principal.user_id,
        )
    )
    caller = db.scalar(
        select(User).where(
            User.id == principal.user_id,
            User.organization_id == principal.organization_id,
        )
    )
    line = (
        db.scalar(
            select(VoiceLine).where(
                VoiceLine.id == session.voice_line_id,
                VoiceLine.organization_id == principal.organization_id,
            )
        )
        if session.voice_line_id is not None
        else None
    )
    if profile is None or caller is None or line is None:
        raise ProspectingVoiceConfigurationError(
            "The dialer session has incomplete browser Voice configuration."
        )
    if not caller.is_active or not caller.calling_enabled or profile.status != "active":
        raise ProspectingVoiceConfigurationError(
            "The caller's native dialer profile is not active."
        )
    if profile.voice_line_id != line.id:
        raise ProspectingVoiceConfigurationError(
            "The dialer session does not use the caller's assigned prospecting line."
        )
    validate_prospecting_line(line)
    if session.effective_line_count != 1:
        raise ProspectingVoiceConfigurationError(
            "Browser calling currently supports exactly one active line."
        )

    identity = browser_voice_identity(session)
    line_read = ProspectingBrowserVoiceLineRead(
        id=line.id,
        phone_number=line.phone_number,
        label=line.label,
        provider=line.provider,
        status=line.status,
        department_key=line.department_key,
        purpose_key=line.purpose_key,
    )
    if not active_settings.twilio_browser_voice_configured:
        return ProspectingBrowserVoiceSessionRead(
            can_initialize=False,
            dial_session_id=session.id,
            identity=identity,
            token=None,
            expires_at=None,
            line=line_read,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            effective_line_count=1,
            blockers=list(active_settings.twilio_browser_voice_configuration_blockers),
        )
    token, expires_at = create_voice_access_token(
        active_settings,
        identity=identity,
        incoming_allow=False,
    )
    return ProspectingBrowserVoiceSessionRead(
        can_initialize=True,
        dial_session_id=session.id,
        identity=identity,
        token=token,
        expires_at=expires_at,
        line=line_read,
        recording_enabled=active_settings.twilio_voice_recording_configured,
        effective_line_count=1,
        blockers=[],
    )


def prepare_browser_prospecting_voice_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallCreate,
    *,
    settings: Settings | None = None,
) -> ProspectingVoiceCallRead | None:
    """Prepare a cold-call intent for Twilio Device.connect without calling a cellphone."""

    active_settings = settings or get_settings()
    require_native_dialer_enabled(active_settings)
    if not active_settings.twilio_browser_voice_configured:
        raise ProspectingVoiceConfigurationError(
            "Twilio browser Voice is not configured: "
            + ", ".join(active_settings.twilio_browser_voice_configuration_blockers)
            + "."
        )
    graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if graph is None:
        return None
    require_call_permission(principal)
    now = datetime.now(UTC)
    validate_voice_session_lease(graph.session, payload, now=now)

    existing_intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_intent is not None:
        if existing_intent.prospecting_dial_leg_id != graph.leg.id:
            raise ProspectingVoiceConflictError(
                "The idempotency key was already used for another prospecting call."
            )
        existing_call = db.scalar(
            select(CallRecord).where(
                CallRecord.organization_id == principal.organization_id,
                CallRecord.call_intent_id == existing_intent.id,
            )
        )
        if existing_call is None:
            raise ProspectingVoiceConflictError(
                "The existing browser call intent has no call evidence."
            )
        validate_existing_call_context(graph, existing_intent, existing_call)
        require_connection_mode(existing_intent, PROSPECTING_BROWSER_CONNECTION_MODE)
        try:
            validate_browser_intent_lease_binding(graph, existing_intent)
        except ProspectingVoiceConflictError:
            if not browser_intent_can_rebind(graph, existing_intent, existing_call):
                raise
            rebind_browser_intent(graph, existing_intent, now=now)
            add_call_audit(
                db,
                principal,
                graph,
                existing_call,
                action="prospecting.voice_browser_call_rebound",
                reason="Prepared browser call rebound after exact dialer lease recovery",
                extra={"call_intent_id": str(existing_intent.id)},
            )
            db.commit()
        return prospecting_voice_call_read(
            graph,
            existing_intent,
            existing_call,
            provider_status=existing_call.status,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            control_action="replayed",
        )

    validate_graph_for_start(db, graph, principal)
    if graph.leg.provider_call_id or graph.leg.call_record_id:
        raise ProspectingVoiceConflictError("This dial leg already has provider call evidence.")
    try:
        validate_reserved_dial_leg_policy(
            db,
            principal,
            graph.leg,
            active_settings,
            now=now,
        )
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc
    except ProspectingDialerConfigurationError as exc:
        raise ProspectingVoiceConfigurationError(str(exc)) from exc

    identity = browser_voice_identity(graph.session)
    intent = VoiceCallIntent(
        organization_id=principal.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=principal.user_id,
        voice_line_id=graph.line.id,
        idempotency_key=payload.idempotency_key,
        recipient=graph.leg.recipient,
        status="pending",
        recording_consent_status=prospecting_recording_status(active_settings),
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
        provider_call_id=None,
        intent_metadata={
            "source": "native_prospecting_dialer",
            "dialer_mode": "one_line_power",
            "campaign_id": str(graph.session.campaign_id),
            "batch_id": str(graph.batch.id),
            "connection_mode": PROSPECTING_BROWSER_CONNECTION_MODE,
            "browser_session_id": graph.session.browser_session_id,
            "lease_fingerprint": dialer_lease_fingerprint(graph.session.lease_token),
            "voice_identity": identity,
            "provider_start_state": PROVIDER_START_PREPARED,
            "provider_start_prepared_at": now.isoformat(),
        },
    )
    db.add(intent)
    db.flush()
    call = CallRecord(
        organization_id=principal.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=principal.user_id,
        communication_record_id=None,
        voice_line_id=graph.line.id,
        call_intent_id=intent.id,
        provider=graph.line.provider,
        provider_call_id=None,
        child_provider_call_id=None,
        direction="outbound",
        status="queued",
        from_number=graph.line.phone_number,
        to_number=graph.leg.recipient,
        started_at=now,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status=intent.recording_consent_status,
        call_metadata={
            "source": "native_prospecting_dialer",
            "bridge": PROSPECTING_BROWSER_CONNECTION_MODE,
            "provider_start_state": PROVIDER_START_PREPARED,
        },
    )
    db.add(call)
    db.flush()
    attach_call_evidence(graph, call)
    graph.leg.voice_line_id = graph.line.id
    graph.attempt.dial_started_at = graph.attempt.dial_started_at or now
    add_call_audit(
        db,
        principal,
        graph,
        call,
        action="prospecting.voice_browser_call_prepared",
        reason="Browser softphone call authorized for the active dialer lease",
        extra={"call_intent_id": str(intent.id)},
    )
    db.commit()
    return prospecting_voice_call_read(
        graph,
        intent,
        call,
        provider_status=call.status,
        recording_enabled=active_settings.twilio_voice_recording_configured,
        control_action="prepared",
    )


def start_prospecting_voice_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallCreate,
    *,
    provider: VoiceCallProvider | None = None,
    settings: Settings | None = None,
) -> ProspectingVoiceCallRead | None:
    active_settings = settings or get_settings()
    require_native_dialer_enabled(active_settings)
    graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if graph is None:
        return None
    require_call_permission(principal)
    now = datetime.now(UTC)
    validate_voice_session_lease(graph.session, payload, now=now)

    existing_intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.organization_id == principal.organization_id,
            VoiceCallIntent.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_intent is not None:
        if existing_intent.prospecting_dial_leg_id != graph.leg.id:
            raise ProspectingVoiceConflictError(
                "The idempotency key was already used for another prospecting call."
            )
        existing_call = db.scalar(
            select(CallRecord).where(
                CallRecord.organization_id == principal.organization_id,
                CallRecord.call_intent_id == existing_intent.id,
            )
        )
        if existing_call is None:
            raise ProspectingVoiceConflictError(
                "The existing prospecting call intent has no call evidence."
            )
        validate_existing_call_context(graph, existing_intent, existing_call)
        require_connection_mode(
            existing_intent,
            PROSPECTING_CELLPHONE_CONNECTION_MODE,
            allow_legacy=True,
        )
        if (
            existing_call.provider_call_id is not None
            or existing_intent.provider_call_id is not None
        ):
            return prospecting_voice_call_read(
                graph,
                existing_intent,
                existing_call,
                provider_status=existing_call.status,
                recording_enabled=active_settings.twilio_voice_recording_configured,
                control_action="replayed",
            )
        start_state = provider_start_state(existing_intent)
        if start_state == PROVIDER_START_DISPATCHING:
            if as_utc(existing_intent.expires_at) > now:
                raise ProspectingVoiceConflictError(
                    "The provider start is still being confirmed. "
                    "Wait for its callback before retrying."
                )
            mark_start_failure(
                db,
                graph,
                existing_intent,
                existing_call,
                "Provider start confirmation expired without a provider call ID; "
                "verify Twilio before continuing.",
                start_state=PROVIDER_START_UNCERTAIN,
            )
            db.commit()
            raise ProspectingVoiceConflictError(
                "The prior provider start became uncertain and was moved to wrap-up. "
                "Verify Twilio before continuing."
            )
        if start_state != PROVIDER_START_PREPARED or existing_intent.status != "pending":
            return prospecting_voice_call_read(
                graph,
                existing_intent,
                existing_call,
                provider_status=existing_call.status,
                recording_enabled=active_settings.twilio_voice_recording_configured,
                control_action="replayed",
            )
        db.commit()
        return dispatch_prepared_voice_call(
            db,
            principal,
            dial_leg_id,
            payload,
            existing_intent.id,
            existing_call.id,
            provider=provider,
            settings=active_settings,
        )

    validate_graph_for_start(db, graph, principal)
    if graph.leg.provider_call_id or graph.leg.call_record_id:
        raise ProspectingVoiceConflictError("This dial leg already has a provider call.")

    try:
        validate_reserved_dial_leg_policy(
            db,
            principal,
            graph.leg,
            active_settings,
            now=now,
        )
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc
    except ProspectingDialerConfigurationError as exc:
        raise ProspectingVoiceConfigurationError(str(exc)) from exc
    intent = VoiceCallIntent(
        organization_id=principal.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=principal.user_id,
        voice_line_id=graph.line.id,
        idempotency_key=payload.idempotency_key,
        recipient=graph.leg.recipient,
        status="pending",
        recording_consent_status=prospecting_recording_status(active_settings),
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
        provider_call_id=None,
        intent_metadata={
            "source": "native_prospecting_dialer",
            "dialer_mode": "one_line_power",
            "campaign_id": str(graph.session.campaign_id),
            "batch_id": str(graph.batch.id),
            "connection_mode": PROSPECTING_CELLPHONE_CONNECTION_MODE,
            "provider_start_state": PROVIDER_START_PREPARED,
            "provider_start_prepared_at": now.isoformat(),
        },
    )
    db.add(intent)
    db.flush()
    call = CallRecord(
        organization_id=principal.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=graph.prospect.id,
        prospecting_attempt_id=graph.attempt.id,
        prospecting_dial_leg_id=graph.leg.id,
        actor_user_id=principal.user_id,
        communication_record_id=None,
        voice_line_id=graph.line.id,
        call_intent_id=intent.id,
        provider=graph.line.provider,
        provider_call_id=None,
        child_provider_call_id=None,
        direction="outbound",
        status="queued",
        from_number=graph.line.phone_number,
        to_number=graph.leg.recipient,
        started_at=now,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status=intent.recording_consent_status,
        call_metadata={
            "source": "native_prospecting_dialer",
            "bridge": "staff_cellphone",
        },
    )
    db.add(call)
    db.flush()
    attach_call_evidence(graph, call)
    graph.leg.voice_line_id = graph.line.id
    graph.attempt.dial_started_at = graph.attempt.dial_started_at or now

    forwarding_number = format_e164(graph.caller.voice_forwarding_number or "")
    if not graph.caller.voice_forwarding_enabled or forwarding_number is None:
        mark_start_failure(
            db,
            graph,
            intent,
            call,
            "The caller's Stonegate cellphone forwarding is not configured.",
        )
        db.commit()
        raise ProspectingVoiceConfigurationError(
            "Add and enable the caller's cellphone under Settings > Communications."
        )
    if not active_settings.twilio_voice_configured:
        mark_start_failure(
            db,
            graph,
            intent,
            call,
            "Twilio cellphone calling is not configured.",
        )
        db.commit()
        raise ProspectingVoiceConfigurationError("Twilio cellphone calling is not configured.")

    # Persist a resumable `prepared` boundary before provider dispatch. A retry after a
    # crash here can safely resume because no provider request has been marked as begun.
    db.commit()
    return dispatch_prepared_voice_call(
        db,
        principal,
        dial_leg_id,
        payload,
        intent.id,
        call.id,
        provider=provider,
        settings=active_settings,
    )


def dispatch_prepared_voice_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    payload: ProspectingVoiceCallCreate,
    intent_id: UUID,
    call_id: UUID,
    *,
    provider: VoiceCallProvider | None,
    settings: Settings,
) -> ProspectingVoiceCallRead:
    """Revalidate, publish a callback-safe dispatch marker, then cross the provider boundary."""

    graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if graph is None:
        raise ProspectingVoiceConflictError("The reserved dial record no longer exists.")
    require_call_permission(principal)
    now = datetime.now(UTC)
    validate_voice_session_lease(graph.session, payload, now=now)
    validate_graph_for_start(db, graph, principal)
    intent, call = load_graph_call(db, graph, lock=True)
    if intent.id != intent_id or call.id != call_id:
        raise ProspectingVoiceConflictError(
            "The prepared provider call no longer matches this dial record."
        )
    validate_existing_call_context(graph, intent, call)
    if call.provider_call_id is not None or intent.provider_call_id is not None:
        return prospecting_voice_call_read(
            graph,
            intent,
            call,
            provider_status=call.status,
            recording_enabled=settings.twilio_voice_recording_configured,
            control_action="replayed",
        )
    if provider_start_state(intent) != PROVIDER_START_PREPARED or intent.status != "pending":
        raise ProspectingVoiceConflictError(
            "The prepared provider call can no longer be dispatched."
        )
    try:
        validate_reserved_dial_leg_policy(
            db,
            principal,
            graph.leg,
            settings,
            now=now,
            expected_call_record_id=call.id,
        )
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc
    except ProspectingDialerConfigurationError as exc:
        raise ProspectingVoiceConfigurationError(str(exc)) from exc

    forwarding_number = format_e164(graph.caller.voice_forwarding_number or "")
    if not graph.caller.voice_forwarding_enabled or forwarding_number is None:
        mark_start_failure(
            db,
            graph,
            intent,
            call,
            "The caller's Stonegate cellphone forwarding is not configured.",
        )
        db.commit()
        raise ProspectingVoiceConfigurationError(
            "Add and enable the caller's cellphone under Settings > Communications."
        )
    if not settings.twilio_voice_configured:
        mark_start_failure(db, graph, intent, call, "Twilio cellphone calling is not configured.")
        db.commit()
        raise ProspectingVoiceConfigurationError("Twilio cellphone calling is not configured.")

    set_provider_start_state(intent, PROVIDER_START_DISPATCHING, now=now)
    call_metadata = dict(call.call_metadata or {})
    call_metadata["provider_start_state"] = PROVIDER_START_DISPATCHING
    call_metadata["provider_dispatch_started_at"] = now.isoformat()
    call.call_metadata = call_metadata
    # This commit releases Session -> Leg locks before Twilio can synchronously call
    # back. The dispatch marker makes the now-unavoidable external-boundary ambiguity
    # explicit and prevents a retry from placing a duplicate call.
    db.commit()

    # A manager can flip a company/campaign kill switch while the callback-safe
    # marker commit releases its locks. Re-read every live D10/runtime control
    # immediately before the provider request; never rely on the pre-commit view.
    dispatch_graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if dispatch_graph is None:
        raise ProspectingVoiceConflictError(
            "The dial record disappeared before provider dispatch."
        )
    dispatch_intent, dispatch_call = load_graph_call(db, dispatch_graph, lock=True)
    if dispatch_intent.id != intent_id or dispatch_call.id != call_id:
        raise ProspectingVoiceConflictError(
            "The provider dispatch marker no longer matches this dial record."
        )
    try:
        validate_reserved_dial_leg_policy(
            db,
            principal,
            dispatch_graph.leg,
            settings,
            now=datetime.now(UTC),
            expected_call_record_id=dispatch_call.id,
        )
    except (ProspectingDialerConflictError, ProspectingDialerConfigurationError) as exc:
        mark_start_failure(
            db,
            dispatch_graph,
            dispatch_intent,
            dispatch_call,
            f"Provider dispatch was stopped by a current runtime control: {exc}",
        )
        db.commit()
        if isinstance(exc, ProspectingDialerConfigurationError):
            raise ProspectingVoiceConfigurationError(str(exc)) from exc
        raise ProspectingVoiceConflictError(str(exc)) from exc

    # Keep the Pilot -> Session -> Leg locks acquired by load_authorized_graph
    # through the provider start. Otherwise revocation can commit after this
    # final policy check but before Twilio accepts the call, allowing one call
    # to escape a kill switch. Twilio's synchronous callback may briefly wait
    # for the transaction, and is reconciled after the provider result below.

    try:
        result = (provider or get_twilio_voice_call_provider()).start(
            to=forwarding_number,
            from_number=graph.line.phone_number,
            twiml=forwarded_outbound_screen_twiml(settings, intent_id=str(intent.id)),
            status_callback=callback_url(
                settings,
                "/api/v1/webhooks/twilio/voice/status",
                intent_id=str(intent.id),
            ),
            status_callback_events=("initiated", "ringing", "answered", "completed"),
        )
    except VoiceCallProviderError as exc:
        refreshed = load_authorized_graph(db, principal, dial_leg_id, lock=True)
        if refreshed is None:
            raise ProspectingVoiceConflictError(
                "The dial record disappeared during provider start."
            ) from exc
        refreshed_intent, refreshed_call = load_graph_call(db, refreshed, lock=True)
        if refreshed_call.provider_call_id is not None:
            db.commit()
            return prospecting_voice_call_read(
                refreshed,
                refreshed_intent,
                refreshed_call,
                provider_status=refreshed_call.status,
                recording_enabled=settings.twilio_voice_recording_configured,
                control_action="replayed",
            )
        mark_start_failure(db, refreshed, refreshed_intent, refreshed_call, str(exc))
        db.commit()
        raise

    refreshed = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if refreshed is None:
        raise ProspectingVoiceConflictError("The dial record disappeared during provider start.")
    intent, call = load_graph_call(db, refreshed, lock=True)
    attach_provider_result(db, refreshed, intent, call, result)
    set_provider_start_state(intent, PROVIDER_START_STARTED, now=datetime.now(UTC))
    reconcile_provider_result(
        db,
        refreshed,
        call,
        result,
        event_id=f"voice:start:{result.sid}:{result.status}",
        event_type="call.start_accepted",
    )
    add_call_audit(
        db,
        principal,
        refreshed,
        call,
        action="prospecting.voice_call_started",
        reason="Controlled native prospecting call started",
        extra={"provider_call_id": result.sid},
    )
    db.commit()
    return prospecting_voice_call_read(
        refreshed,
        intent,
        call,
        provider_status=result.status,
        recording_enabled=settings.twilio_voice_recording_configured,
        control_action="started",
    )


def fetch_prospecting_voice_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    *,
    provider: VoiceCallProvider | None = None,
    settings: Settings | None = None,
) -> ProspectingVoiceCallRead | None:
    active_settings = settings or get_settings()
    graph = load_authorized_graph(db, principal, dial_leg_id, lock=False)
    if graph is None:
        return None
    require_call_permission(principal)
    intent, call = load_graph_call(db, graph)
    if call.provider_call_id is None:
        if (
            connection_mode(intent) == PROSPECTING_BROWSER_CONNECTION_MODE
            and as_utc(intent.expires_at) <= datetime.now(UTC)
        ):
            locked_graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
            if locked_graph is None:
                raise ProspectingVoiceConflictError(
                    "The dial record disappeared during browser call recovery."
                )
            locked_intent, locked_call = load_graph_call(db, locked_graph, lock=True)
            now = datetime.now(UTC)
            if (
                as_utc(locked_intent.expires_at) <= now
                and untouched_browser_call(locked_graph, locked_intent, locked_call)
            ):
                abandon_untouched_browser_call(
                    db,
                    principal,
                    locked_graph,
                    locked_intent,
                    locked_call,
                    now=now,
                    reason="Browser call preparation expired before Twilio started.",
                    intent_status="expired",
                )
                db.commit()
                return prospecting_voice_call_read(
                    locked_graph,
                    locked_intent,
                    locked_call,
                    provider_status=locked_call.status,
                    recording_enabled=active_settings.twilio_voice_recording_configured,
                    control_action="fetched",
                )
        return prospecting_voice_call_read(
            graph,
            intent,
            call,
            provider_status=call.status,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            control_action="replayed",
        )
    browser_connection = connection_mode(intent) == PROSPECTING_BROWSER_CONNECTION_MODE
    if browser_connection and call.child_provider_call_id is None:
        # The browser/root leg only proves that Twilio reached Stonegate's TwiML app.
        # It is not evidence that the seller's Number leg rang or answered.
        return prospecting_voice_call_read(
            graph,
            intent,
            call,
            provider_status=call.status,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            control_action="replayed",
        )
    provider_call_id = (
        call.child_provider_call_id if browser_connection else call.provider_call_id
    )
    assert provider_call_id is not None
    # Never hold coordinator row locks while waiting on Twilio. Provider truth is
    # reconciled in a fresh Session -> Leg transaction immediately afterward.
    db.commit()
    result = (provider or get_twilio_voice_call_provider()).fetch(provider_call_id)
    refreshed = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if refreshed is None:
        raise ProspectingVoiceConflictError("The dial record disappeared during provider refresh.")
    intent, call = load_graph_call(db, refreshed, lock=True)
    expected_provider_call_id = (
        call.child_provider_call_id
        if connection_mode(intent) == PROSPECTING_BROWSER_CONNECTION_MODE
        else call.provider_call_id
    )
    if expected_provider_call_id != provider_call_id or result.sid != provider_call_id:
        raise ProspectingVoiceConflictError(
            "The provider response does not match this prospecting call."
        )
    reconcile_provider_result(
        db,
        refreshed,
        call,
        result,
        event_id=f"voice:fetch:{result.sid}:{result.status}",
        event_type="call.fetch_reconciled",
    )
    db.commit()
    return prospecting_voice_call_read(
        refreshed,
        intent,
        call,
        provider_status=result.status,
        recording_enabled=active_settings.twilio_voice_recording_configured,
        control_action="fetched",
    )


def control_prospecting_voice_call(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    *,
    action: Literal["cancel", "hangup"],
    payload: ProspectingVoiceCallControl,
    provider: VoiceCallProvider | None = None,
    settings: Settings | None = None,
) -> ProspectingVoiceCallRead | None:
    active_settings = settings or get_settings()
    graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if graph is None:
        return None
    require_call_permission(principal)
    now = datetime.now(UTC)
    validate_voice_session_lease(graph.session, payload, now=now)
    reason = payload.reason
    intent, call = load_graph_call(db, graph)
    if graph.leg.status in DIAL_LEG_TERMINAL_STATUSES:
        return prospecting_voice_call_read(
            graph,
            intent,
            call,
            provider_status=call.status,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            control_action="replayed",
        )
    if action == "cancel" and graph.leg.status in {"answered", "connected"}:
        raise ProspectingVoiceConflictError("Connected calls must be hung up, not cancelled.")
    if action == "hangup" and graph.leg.status not in {"answered", "connected"}:
        raise ProspectingVoiceConflictError("Only an answered call can be hung up.")
    browser_connection = connection_mode(intent) == PROSPECTING_BROWSER_CONNECTION_MODE
    if (
        action == "cancel"
        and call.provider_call_id is None
        and untouched_browser_call(graph, intent, call)
    ):
        abandon_untouched_browser_call(
            db,
            principal,
            graph,
            intent,
            call,
            now=now,
            reason=reason,
            intent_status="cancelled",
        )
        db.commit()
        return prospecting_voice_call_read(
            graph,
            intent,
            call,
            provider_status=call.status,
            recording_enabled=active_settings.twilio_voice_recording_configured,
            control_action="cancelled",
        )
    if call.provider_call_id is None:
        raise ProspectingVoiceConflictError("The provider call has not started.")

    previous_leg_status = graph.leg.status
    if action == "cancel":
        record_dial_provider_event(
            db,
            organization_id=graph.leg.organization_id,
            provider=graph.leg.provider,
            external_event_id=f"voice:cancel-requested:{graph.leg.id}",
            event_type="call.cancel_requested",
            payload={"reason": reason, "source": "api"},
            dial_leg=graph.leg,
            occurred_at=now,
            signature_verified=False,
        )
        graph.leg.status = "cancelling"
        reconcile_dial_session_from_leg(db, graph.leg, now=now)
    provider_call_id = (
        call.child_provider_call_id
        if browser_connection and call.child_provider_call_id is not None
        else call.provider_call_id
    )
    terminate_root_for_cancel = bool(
        browser_connection and action == "cancel" and call.child_provider_call_id is None
    )
    db.commit()
    voice_provider = provider or get_twilio_voice_call_provider()
    try:
        result = (
            voice_provider.cancel(provider_call_id)
            if action == "cancel" and not terminate_root_for_cancel
            else voice_provider.hangup(provider_call_id)
        )
    except VoiceCallProviderError as exc:
        refreshed = load_authorized_graph(db, principal, dial_leg_id, lock=True)
        if refreshed is None:
            raise ProspectingVoiceConflictError(
                "The dial record disappeared during call control."
            ) from exc
        refreshed_intent, refreshed_call = load_graph_call(db, refreshed, lock=True)
        if action == "cancel" and refreshed.leg.status == "cancelling":
            refreshed.leg.status = previous_leg_status
            reconcile_dial_session_from_leg(db, refreshed.leg, now=datetime.now(UTC))
        mark_control_failure(db, refreshed, action=action, message=str(exc))
        add_call_audit(
            db,
            principal,
            refreshed,
            refreshed_call,
            action=f"prospecting.voice_call_{action}_failed",
            reason=reason,
            extra={"error": str(exc)},
        )
        db.commit()
        raise

    graph = load_authorized_graph(db, principal, dial_leg_id, lock=True)
    if graph is None:
        raise ProspectingVoiceConflictError("The dial record disappeared during call control.")
    intent, call = load_graph_call(db, graph, lock=True)
    associated_provider_call_ids = {
        call_id
        for call_id in (call.provider_call_id, call.child_provider_call_id)
        if call_id is not None
    }
    if (
        provider_call_id not in associated_provider_call_ids
        or result.sid != provider_call_id
    ):
        raise ProspectingVoiceConflictError(
            "The provider response does not match this prospecting call."
        )
    reconcile_provider_result(
        db,
        graph,
        call,
        result,
        event_id=f"voice:{action}:{result.sid}:{result.status}",
        event_type=f"call.{action}",
        cancellation_requested=action == "cancel",
    )
    graph.leg.cancellation_reason = reason if action == "cancel" else graph.leg.cancellation_reason
    add_call_audit(
        db,
        principal,
        graph,
        call,
        action=f"prospecting.voice_call_{action}",
        reason=reason,
        extra={"provider_status": result.status},
    )
    db.commit()
    return prospecting_voice_call_read(
        graph,
        intent,
        call,
        provider_status=result.status,
        recording_enabled=active_settings.twilio_voice_recording_configured,
        control_action="cancelled" if action == "cancel" else "hung_up",
    )


def reconcile_signed_prospecting_status(
    db: Session,
    call: CallRecord,
    payload: dict[str, str],
    *,
    status: str,
    signature_verified: bool,
    signature: str | None,
    callback_kind: Literal["status", "dial_result"] = "status",
) -> str:
    require_verified_callback(signature_verified)
    graph = load_callback_graph(db, call, lock=True)
    if graph is None:
        raise ProspectingVoiceConfigurationError(
            "Prospecting call context could not be correlated to one dial leg."
        )
    event_sid, is_contact_leg = correlate_status_callback(
        db,
        graph,
        call,
        payload,
        callback_kind=callback_kind,
    )
    normalized_status = status.strip().lower()
    external_event_id = (
        f"voice:{callback_kind}:{call.provider_call_id}:{event_sid}:{normalized_status}"
    )
    existing = db.scalar(
        select(ProspectingProviderEvent).where(
            ProspectingProviderEvent.organization_id == call.organization_id,
            ProspectingProviderEvent.provider == call.provider,
            ProspectingProviderEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return existing.processing_status

    target_status = callback_target_status(
        graph.leg,
        normalized_status,
        is_contact_leg=is_contact_leg,
    )
    event, applied = record_dial_provider_event(
        db,
        organization_id=call.organization_id,
        provider=call.provider,
        external_event_id=external_event_id,
        event_type=f"call.{normalized_status.replace('-', '_')}",
        payload=payload,
        dial_leg=graph.leg,
        target_status=target_status,
        # Twilio sequence numbers restart for the parent and child call streams.
        # Rank/timestamp reduction is safer than combining both counters on one dial leg.
        provider_sequence_number=None,
        occurred_at=provider_occurred_at(payload),
        signature_verified=signature_verified,
        signature=signature,
    )
    event.provider_call_id = event_sid
    if applied and target_status is not None:
        apply_reconciled_state(graph, call, target_status, payload)
    db.commit()
    return event.processing_status


def reconcile_signed_prospecting_recording(
    db: Session,
    call: CallRecord,
    payload: dict[str, str],
    *,
    signature_verified: bool,
    signature: str | None,
) -> str:
    require_verified_callback(signature_verified)
    graph = load_callback_graph(db, call, lock=True)
    if graph is None:
        raise ProspectingVoiceConfigurationError(
            "Prospecting recording could not be correlated to one dial leg."
        )
    recording_sid = payload.get("RecordingSid")
    recording_status = (payload.get("RecordingStatus") or "").lower()
    if not recording_sid or not recording_status:
        raise ValueError("Provider recording callback is missing required fields.")
    correlate_media_callback(db, graph, call, payload)
    external_event_id = f"voice:recording:{recording_sid}:{recording_status}"
    event, _ = record_dial_provider_event(
        db,
        organization_id=call.organization_id,
        provider=call.provider,
        external_event_id=external_event_id,
        event_type=f"recording.{recording_status}",
        payload=payload,
        dial_leg=graph.leg,
        occurred_at=provider_occurred_at(payload),
        signature_verified=signature_verified,
        signature=signature,
    )
    event.provider_recording_id = recording_sid
    graph.leg.provider_recording_id = recording_sid
    graph.attempt.provider_recording_id = recording_sid
    db.flush()
    return event.processing_status


def reconcile_signed_prospecting_disclosure(
    db: Session,
    call: CallRecord,
    payload: dict[str, str],
    *,
    signature_verified: bool,
    signature: str | None,
) -> str:
    require_verified_callback(signature_verified)
    graph = load_callback_graph(db, call, lock=True)
    if graph is None:
        raise ProspectingVoiceConfigurationError(
            "Prospecting disclosure could not be correlated to one dial leg."
        )
    correlate_media_callback(db, graph, call, payload)
    event, _ = record_dial_provider_event(
        db,
        organization_id=call.organization_id,
        provider=call.provider,
        external_event_id=f"voice:recording-disclosure:{call.id}",
        event_type="recording.disclosure",
        payload=payload,
        dial_leg=graph.leg,
        occurred_at=provider_occurred_at(payload),
        signature_verified=signature_verified,
        signature=signature,
    )
    db.flush()
    return event.processing_status


def validate_prospecting_connect_intent(
    db: Session,
    intent: VoiceCallIntent,
    payload: dict[str, str],
    *,
    expected_pilot_id: UUID | None = None,
) -> None:
    if intent.prospect_id is None:
        return
    require_connection_mode(intent, PROSPECTING_CELLPHONE_CONNECTION_MODE)
    if provider_start_state(intent) != PROVIDER_START_STARTED:
        raise ProspectingVoiceConflictError(
            "The staff bridge has not reached its provider-start boundary."
        )
    if (intent.intent_metadata or {}).get("seller_bridge_authorized_at"):
        raise ProspectingVoiceConflictError("The seller bridge was already authorized.")
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == intent.organization_id,
            CallRecord.call_intent_id == intent.id,
        )
    )
    graph = load_callback_graph(db, call, lock=True) if call is not None else None
    if call is None or graph is None:
        raise ProspectingVoiceConfigurationError(
            "Prospecting call intent is not attached to an active dial leg."
        )
    if graph.session.pilot_id != expected_pilot_id:
        raise ProspectingVoiceConflictError(
            "The dialer's D10 authorization changed before seller connection."
        )
    if graph.leg.status in DIAL_LEG_TERMINAL_STATUSES | {"cancelling"}:
        raise ProspectingVoiceConflictError("The prospecting call is no longer connectable.")
    root_sid = payload.get("CallSid")
    if not root_sid:
        raise ValueError("Provider connect request is missing its root call ID.")
    if (
        graph.attempt.status != "in_progress"
        or call.status != "dialing"
        or call.ended_at is not None
        or call.child_provider_call_id is not None
        or intent.provider_call_id != root_sid
        or call.provider_call_id != root_sid
        or graph.leg.provider_call_id != root_sid
        or graph.attempt.provider_call_id != root_sid
    ):
        raise ProspectingVoiceConflictError(
            "The staff bridge does not match the active provider call."
        )
    principal = principal_for_user(db, graph.caller)
    try:
        validate_in_flight_dial_leg_policy(
            db,
            principal,
            graph.leg,
            get_settings(),
            now=datetime.now(UTC),
            expected_call_record_id=call.id,
            expected_provider_call_id=root_sid,
        )
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc
    except ProspectingDialerConfigurationError as exc:
        raise ProspectingVoiceConfigurationError(str(exc)) from exc
    ensure_root_provider_call_id(db, graph, call, root_sid)
    metadata = dict(intent.intent_metadata or {})
    metadata["seller_bridge_authorized_at"] = datetime.now(UTC).isoformat()
    intent.intent_metadata = metadata


def lock_prospecting_connect_pilot(
    db: Session,
    intent_id: UUID,
) -> UUID | None:
    """Lock D10 authorization before any intent/session/leg bridge locks.

    Revocation uses the same pilot-first order.  The bridge later revalidates
    this identifier after locking its exact runtime graph, so a stale pre-read
    can never authorize a seller connection.
    """

    identity = db.execute(
        select(
            VoiceCallIntent.prospect_id,
            ProspectingDialSession.pilot_id,
        )
        .join(CallRecord, CallRecord.call_intent_id == VoiceCallIntent.id)
        .join(
            ProspectingDialLeg,
            ProspectingDialLeg.id == CallRecord.prospecting_dial_leg_id,
        )
        .join(
            ProspectingDialSession,
            ProspectingDialSession.id == ProspectingDialLeg.dial_session_id,
        )
        .where(VoiceCallIntent.id == intent_id)
    ).one_or_none()
    if identity is None or identity.prospect_id is None or identity.pilot_id is None:
        return None
    pilot = db.scalar(
        select(ProspectingDialerPilot)
        .where(
            ProspectingDialerPilot.id == identity.pilot_id,
            ProspectingDialerPilot.organization_id == db.scalar(
                select(VoiceCallIntent.organization_id).where(
                    VoiceCallIntent.id == intent_id
                )
            ),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if pilot is None:
        raise ProspectingVoiceConfigurationError(
            "The dialer's D10 authorization is unavailable."
        )
    return pilot.id


def process_browser_prospecting_outbound_request(
    db: Session,
    intent: VoiceCallIntent,
    payload: dict[str, str],
    *,
    settings: Settings | None = None,
) -> str:
    """Consume a one-time cold-call intent from Twilio's browser Voice webhook."""

    active_settings = settings or get_settings()
    require_native_dialer_enabled(active_settings)
    if not active_settings.twilio_browser_voice_configured:
        raise ProspectingVoiceConfigurationError("Twilio browser Voice is not configured.")
    require_connection_mode(intent, PROSPECTING_BROWSER_CONNECTION_MODE)
    if intent.prospect_id is None:
        raise ProspectingVoiceConfigurationError("Browser prospecting context is unavailable.")
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == intent.organization_id,
            CallRecord.call_intent_id == intent.id,
        )
    )
    graph = load_callback_graph(db, call, lock=True) if call is not None else None
    if call is None or graph is None:
        raise ProspectingVoiceConfigurationError(
            "Browser prospecting call is not attached to an active dial leg."
        )
    validate_existing_call_context(graph, intent, call)
    validate_browser_intent_lease_binding(graph, intent)
    expected_identity = str((intent.intent_metadata or {}).get("voice_identity") or "")
    caller_identity = payload.get("From", "").removeprefix("client:")
    if not expected_identity or not secrets.compare_digest(caller_identity, expected_identity):
        raise PermissionError("Voice SDK identity does not match the active dialer lease.")
    root_sid = (payload.get("CallSid") or "").strip()
    if not root_sid:
        raise ValueError("Provider connect request is missing its root call ID.")

    now = datetime.now(UTC)
    if intent.status == "started" and intent.provider_call_id == root_sid:
        ensure_root_provider_call_id(db, graph, call, root_sid)
    elif intent.status == "pending":
        if as_utc(intent.expires_at) <= now:
            mark_start_failure(
                db,
                graph,
                intent,
                call,
                "Browser Voice call intent expired before provider connection.",
            )
            intent.status = "expired"
            db.commit()
            raise ProspectingVoiceConflictError("Browser Voice call intent expired.")
        principal = principal_for_user(db, graph.caller)
        require_call_permission(principal)
        validate_graph_for_start(db, graph, principal)
        try:
            validate_reserved_dial_leg_policy(
                db,
                principal,
                graph.leg,
                active_settings,
                now=now,
                expected_call_record_id=call.id,
            )
        except ProspectingDialerConflictError as exc:
            raise ProspectingVoiceConflictError(str(exc)) from exc
        except ProspectingDialerConfigurationError as exc:
            raise ProspectingVoiceConfigurationError(str(exc)) from exc
        ensure_root_provider_call_id(db, graph, call, root_sid)
        reconcile_provider_result(
            db,
            graph,
            call,
            # This is the browser -> TwiML root. Even when Twilio labels it
            # in-progress, only the child Number leg can prove seller connection.
            VoiceCallResult(sid=root_sid, status="initiated"),
            event_id=f"voice:browser-start:{root_sid}",
            event_type="call.browser_connected",
        )
        call_metadata = dict(call.call_metadata or {})
        call_metadata["provider_start_state"] = PROVIDER_START_STARTED
        call_metadata["browser_connected_at"] = now.isoformat()
        call.call_metadata = call_metadata
        add_call_audit(
            db,
            principal,
            graph,
            call,
            action="prospecting.voice_browser_call_started",
            reason="Twilio browser softphone connected the authorized dialer call",
            extra={"provider_call_id": root_sid},
        )
    else:
        raise ProspectingVoiceConflictError("Browser Voice call intent has already been used.")

    validate_prospecting_line(graph.line)
    db.commit()
    return outbound_call_twiml(
        active_settings,
        recipient=intent.recipient,
        from_number=graph.line.phone_number,
        intent_id=str(intent.id),
        recording_enabled=active_settings.twilio_voice_recording_configured,
    )


def load_authorized_graph(
    db: Session,
    principal: Principal,
    dial_leg_id: UUID,
    *,
    lock: bool,
) -> ProspectingVoiceGraph | None:
    session_id = db.scalar(
        select(ProspectingDialLeg.dial_session_id).where(
            ProspectingDialLeg.id == dial_leg_id,
            ProspectingDialLeg.organization_id == principal.organization_id,
        )
    )
    if session_id is None:
        return None
    expected_pilot_id = (
        lock_expected_session_pilot(
            db,
            organization_id=principal.organization_id,
            session_id=session_id,
        )
        if lock
        else None
    )
    if lock:
        session = db.scalar(
            select(ProspectingDialSession)
            .where(
                ProspectingDialSession.id == session_id,
                ProspectingDialSession.organization_id == principal.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if session is None:
            return None
        if session.pilot_id != expected_pilot_id:
            raise ProspectingVoiceConflictError(
                "The dialer's D10 authorization changed while locking its call graph."
            )
    statement = select(ProspectingDialLeg).where(
        ProspectingDialLeg.id == dial_leg_id,
        ProspectingDialLeg.organization_id == principal.organization_id,
        ProspectingDialLeg.dial_session_id == session_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    leg = db.scalar(statement)
    if leg is None:
        return None
    graph = assemble_graph(db, leg)
    if graph is None:
        raise ProspectingVoiceConfigurationError("The dial leg has incomplete call context.")
    if graph.session.caller_user_id != principal.user_id:
        raise PermissionError("This dial leg is assigned to another caller.")
    return graph


def load_callback_graph(
    db: Session,
    call: CallRecord,
    *,
    lock: bool,
) -> ProspectingVoiceGraph | None:
    if call.prospect_id is None or call.prospecting_dial_leg_id is None:
        return None
    session_id = db.scalar(
        select(ProspectingDialLeg.dial_session_id).where(
            ProspectingDialLeg.id == call.prospecting_dial_leg_id,
            ProspectingDialLeg.organization_id == call.organization_id,
        )
    )
    if session_id is None:
        return None
    expected_pilot_id = (
        lock_expected_session_pilot(
            db,
            organization_id=call.organization_id,
            session_id=session_id,
        )
        if lock
        else None
    )
    if lock:
        session = db.scalar(
            select(ProspectingDialSession)
            .where(
                ProspectingDialSession.id == session_id,
                ProspectingDialSession.organization_id == call.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if session is None:
            return None
        if session.pilot_id != expected_pilot_id:
            raise ProspectingVoiceConflictError(
                "The dialer's D10 authorization changed while locking its call graph."
            )
    statement = select(ProspectingDialLeg).where(
        ProspectingDialLeg.id == call.prospecting_dial_leg_id,
        ProspectingDialLeg.organization_id == call.organization_id,
        ProspectingDialLeg.dial_session_id == session_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    leg = db.scalar(statement)
    if leg is None or leg.call_record_id != call.id:
        return None
    graph = assemble_graph(db, leg)
    if graph is None:
        return None
    if (
        call.prospect_id != graph.prospect.id
        or call.prospecting_attempt_id != graph.attempt.id
        or call.actor_user_id != graph.caller.id
        or call.voice_line_id != graph.line.id
    ):
        return None
    if call.call_intent_id is None:
        return None
    intent = db.scalar(
        select(VoiceCallIntent).where(
            VoiceCallIntent.id == call.call_intent_id,
            VoiceCallIntent.organization_id == call.organization_id,
        )
    )
    if intent is None:
        return None
    try:
        validate_existing_call_context(graph, intent, call)
    except ProspectingVoiceConfigurationError:
        return None
    return graph


def validate_existing_call_context(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
) -> None:
    expected = (
        graph.prospect.id,
        graph.attempt.id,
        graph.leg.id,
        graph.caller.id,
        graph.line.id,
    )
    if (
        (
            intent.prospect_id,
            intent.prospecting_attempt_id,
            intent.prospecting_dial_leg_id,
            intent.actor_user_id,
            intent.voice_line_id,
        )
        != expected
        or (
            call.prospect_id,
            call.prospecting_attempt_id,
            call.prospecting_dial_leg_id,
            call.actor_user_id,
            call.voice_line_id,
        )
        != expected
        or call.call_intent_id != intent.id
        or graph.leg.call_record_id != call.id
        or graph.leg.attempt_id != graph.attempt.id
        or graph.leg.prospect_id != graph.prospect.id
        or graph.leg.dial_session_id != graph.session.id
        or graph.attempt.call_record_id != call.id
    ):
        raise ProspectingVoiceConfigurationError(
            "Prospecting intent, call, attempt, and dial leg are not reciprocal."
        )
    if (
        call.provider != graph.line.provider
        or graph.leg.provider != graph.line.provider
        or graph.attempt.provider not in {None, graph.line.provider}
    ):
        raise ProspectingVoiceConfigurationError(
            "Prospecting call provider context does not match its voice line."
        )
    root_ids = {
        value
        for value in (
            intent.provider_call_id,
            call.provider_call_id,
            graph.leg.provider_call_id,
            graph.attempt.provider_call_id,
        )
        if value is not None
    }
    if len(root_ids) > 1:
        raise ProspectingVoiceConfigurationError(
            "Prospecting call records reference different provider calls."
        )


def require_verified_callback(signature_verified: bool) -> None:
    if not signature_verified:
        raise PermissionError(
            "A verified provider signature is required for prospecting callbacks."
        )


def correlate_status_callback(
    db: Session,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    payload: dict[str, str],
    *,
    callback_kind: Literal["status", "dial_result"],
) -> tuple[str, bool]:
    call_sid = (payload.get("CallSid") or "").strip()
    parent_sid = (payload.get("ParentCallSid") or "").strip()
    dial_sid = (payload.get("DialCallSid") or "").strip()
    if callback_kind == "dial_result":
        root_sid = call_sid or parent_sid
        child_sid = dial_sid
        is_contact_leg = True
    elif parent_sid:
        root_sid = parent_sid
        child_sid = call_sid
        is_contact_leg = True
    else:
        root_sid = call_sid
        child_sid = ""
        is_contact_leg = False
    if not root_sid:
        raise ValueError("Provider callback is missing its root call ID.")
    ensure_root_provider_call_id(db, graph, call, root_sid)
    if child_sid:
        ensure_child_provider_call_id(db, graph, call, child_sid)
    event_sid = child_sid or root_sid
    return event_sid, is_contact_leg


def correlate_media_callback(
    db: Session,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    payload: dict[str, str],
) -> None:
    call_sid = (payload.get("CallSid") or "").strip()
    parent_sid = (payload.get("ParentCallSid") or "").strip()
    if not call_sid:
        raise ValueError("Provider media callback is missing its call ID.")
    if parent_sid:
        ensure_root_provider_call_id(db, graph, call, parent_sid)
        ensure_child_provider_call_id(db, graph, call, call_sid)
        return
    if call_sid not in {call.provider_call_id, call.child_provider_call_id}:
        raise ProspectingVoiceConflictError(
            "Provider media callback does not belong to this prospecting call."
        )


def ensure_root_provider_call_id(
    db: Session,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    provider_call_id: str,
) -> None:
    normalized_id = provider_call_id.strip()
    if not normalized_id:
        raise ValueError("A provider root call ID is required.")
    collision = db.scalar(
        select(CallRecord.id).where(
            CallRecord.organization_id == call.organization_id,
            CallRecord.id != call.id,
            (
                (CallRecord.provider_call_id == normalized_id)
                | (CallRecord.child_provider_call_id == normalized_id)
            ),
        )
    )
    if collision is not None:
        raise ProspectingVoiceConflictError(
            "Provider root call ID is already attached to another call."
        )
    intent = db.get(VoiceCallIntent, call.call_intent_id) if call.call_intent_id else None
    if intent is None or intent.organization_id != call.organization_id:
        raise ProspectingVoiceConfigurationError("Prospecting call intent is unavailable.")
    for current_id in (
        intent.provider_call_id,
        call.provider_call_id,
        graph.leg.provider_call_id,
        graph.attempt.provider_call_id,
    ):
        if current_id not in {None, normalized_id}:
            raise ProspectingVoiceConflictError(
                "Provider root call ID does not match the reserved dial leg."
            )
    intent.provider_call_id = normalized_id
    if intent.status == "pending":
        intent.status = "started"
        intent.consumed_at = datetime.now(UTC)
    set_provider_start_state(intent, PROVIDER_START_STARTED, now=datetime.now(UTC))
    call.provider_call_id = normalized_id
    graph.leg.provider = graph.line.provider
    graph.leg.provider_call_id = normalized_id
    graph.attempt.provider = graph.line.provider
    graph.attempt.provider_call_id = normalized_id
    # Tests and production workers intentionally run with autoflush disabled.
    # Persist the root binding before any provider-event reconciliation reloads
    # the same leg with ``populate_existing`` and could otherwise erase it.
    db.flush([intent, call, graph.leg, graph.attempt])


def ensure_child_provider_call_id(
    db: Session,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    provider_call_id: str,
) -> None:
    normalized_id = provider_call_id.strip()
    if not normalized_id or normalized_id == call.provider_call_id:
        raise ProspectingVoiceConflictError("Provider child call ID is invalid.")
    collision = db.scalar(
        select(CallRecord.id).where(
            CallRecord.organization_id == call.organization_id,
            CallRecord.id != call.id,
            (
                (CallRecord.provider_call_id == normalized_id)
                | (CallRecord.child_provider_call_id == normalized_id)
            ),
        )
    )
    if collision is not None or call.child_provider_call_id not in {None, normalized_id}:
        raise ProspectingVoiceConflictError(
            "Provider child call ID belongs to a different call leg."
        )
    call.child_provider_call_id = normalized_id
    graph.leg.leg_metadata = {
        **dict(graph.leg.leg_metadata),
        "child_provider_call_id": normalized_id,
    }


def assemble_graph(db: Session, leg: ProspectingDialLeg) -> ProspectingVoiceGraph | None:
    session = db.get(ProspectingDialSession, leg.dial_session_id)
    prospect = db.get(Prospect, leg.prospect_id)
    entry = db.get(ProspectCallingBatchEntry, leg.batch_entry_id)
    attempt = db.get(ProspectingAttempt, leg.attempt_id) if leg.attempt_id else None
    if session is None or prospect is None or entry is None or attempt is None:
        return None
    profile = db.get(ProspectingDialerProfile, session.dialer_profile_id)
    batch = db.get(ProspectCallingBatch, entry.prospect_calling_batch_id)
    caller = db.get(User, session.caller_user_id)
    line_id = (
        leg.voice_line_id or session.voice_line_id or (profile.voice_line_id if profile else None)
    )
    line = db.get(VoiceLine, line_id) if line_id else None
    if profile is None or batch is None or caller is None or line is None:
        return None
    organization_ids = {
        leg.organization_id,
        session.organization_id,
        profile.organization_id,
        prospect.organization_id,
        entry.organization_id,
        batch.organization_id,
        attempt.organization_id,
        caller.organization_id,
        line.organization_id,
    }
    if len(organization_ids) != 1:
        return None
    return ProspectingVoiceGraph(
        leg=leg,
        session=session,
        profile=profile,
        prospect=prospect,
        entry=entry,
        batch=batch,
        attempt=attempt,
        caller=caller,
        line=line,
    )


def validate_graph_for_start(
    db: Session,
    graph: ProspectingVoiceGraph,
    principal: Principal,
) -> None:
    if not graph.caller.is_active or not graph.caller.calling_enabled:
        raise ProspectingVoiceConfigurationError("Cold calling is not enabled for this caller.")
    if graph.profile.user_id != principal.user_id or graph.profile.status != "active":
        raise ProspectingVoiceConfigurationError(
            "The caller's native dialer profile is not active."
        )
    if graph.profile.voice_line_id != graph.line.id:
        raise ProspectingVoiceConfigurationError("The dial session uses a different voice line.")
    if graph.session.voice_line_id != graph.line.id or graph.leg.voice_line_id != graph.line.id:
        raise ProspectingVoiceConfigurationError(
            "The reserved dial session and leg must use the dedicated prospecting line."
        )
    if graph.line.status != "active" or graph.line.provider != "twilio":
        raise ProspectingVoiceConfigurationError("The prospecting voice line is unavailable.")
    if (
        graph.line.department_key != "acquisitions"
        or graph.line.purpose_key != PROSPECTING_VOICE_LINE_PURPOSE
    ):
        raise ProspectingVoiceConfigurationError(
            "Assign a dedicated acquisitions line with the prospecting-outbound purpose."
        )
    if graph.session.state not in PROSPECTING_ACTIVE_SESSION_STATES:
        raise ProspectingVoiceConflictError("The dial session is no longer active.")
    if graph.session.effective_line_count != 1 or graph.leg.line_slot != 1:
        raise ProspectingVoiceConfigurationError("D2 supports exactly one controlled call leg.")
    if graph.session.campaign_id != graph.prospect.campaign_id:
        raise ProspectingVoiceConfigurationError(
            "The prospect is outside the dial session campaign."
        )
    if graph.batch.campaign_id != graph.session.campaign_id:
        raise ProspectingVoiceConfigurationError("The calling batch is outside the campaign.")
    if graph.session.prospect_calling_batch_id not in {None, graph.batch.id}:
        raise ProspectingVoiceConfigurationError(
            "The dial session references another calling batch."
        )
    if (
        graph.entry.prospect_id != graph.prospect.id
        or graph.entry.assigned_user_id != principal.user_id
        or graph.batch.assigned_user_id != principal.user_id
    ):
        raise PermissionError("This prospect is not assigned to the current caller.")
    if (
        graph.attempt.batch_entry_id != graph.entry.id
        or graph.attempt.prospect_id != graph.prospect.id
        or graph.attempt.caller_user_id != principal.user_id
        or graph.attempt.status != "in_progress"
    ):
        raise ProspectingVoiceConflictError("The dial leg is not attached to the active attempt.")
    for current_value, expected, label in (
        (graph.session.current_prospect_id, graph.prospect.id, "prospect"),
        (graph.session.current_batch_entry_id, graph.entry.id, "calling-list entry"),
        (graph.session.current_attempt_id, graph.attempt.id, "attempt"),
    ):
        if current_value != expected:
            raise ProspectingVoiceConflictError(
                f"The dial session is not reserved for this {label}."
            )
    if graph.leg.completed_at is not None or graph.leg.status in DIAL_LEG_TERMINAL_STATUSES:
        raise ProspectingVoiceConflictError("The dial leg is already complete.")
    if graph.prospect.converted_lead_id is not None:
        raise ProspectingVoiceConflictError("The prospect has already been converted to a lead.")
    if (
        graph.prospect.suppression_status != "clear"
        or graph.prospect.call_eligibility != "eligible"
    ):
        raise ProspectingVoiceConflictError("The prospect is not currently eligible for calling.")
    validate_recipient(db, graph)


def validate_recipient(db: Session, graph: ProspectingVoiceGraph) -> None:
    recipient = format_e164(graph.leg.recipient)
    if recipient is None:
        raise ProspectingVoiceConfigurationError("The dial leg has an invalid phone number.")
    allowed_numbers = {
        value
        for value in (format_e164(graph.prospect.normalized_phone or graph.prospect.phone or ""),)
        if value is not None
    }
    contact_points = list(
        db.scalars(
            select(ProspectContactPoint).where(
                ProspectContactPoint.organization_id == graph.leg.organization_id,
                ProspectContactPoint.prospect_id == graph.prospect.id,
                ProspectContactPoint.contact_type == "phone",
            )
        )
    )
    allowed_numbers.update(
        formatted
        for point in contact_points
        if (formatted := format_e164(point.normalized_value or point.value)) is not None
    )
    if recipient not in allowed_numbers:
        raise ProspectingVoiceConflictError("The dial leg phone does not belong to this prospect.")
    if graph.leg.contact_point_id is not None and not any(
        point.id == graph.leg.contact_point_id and format_e164(point.normalized_value) == recipient
        for point in contact_points
    ):
        raise ProspectingVoiceConflictError("The dial leg contact point does not match its phone.")
    graph.leg.recipient = recipient


def require_native_dialer_enabled(settings: Settings) -> None:
    if not settings.prospecting_native_dialer_enabled:
        raise ProspectingVoiceConfigurationError("Native prospecting dialer is disabled.")


def validate_prospecting_line(line: VoiceLine) -> None:
    if line.status != "active" or line.provider != "twilio":
        raise ProspectingVoiceConfigurationError("The prospecting voice line is unavailable.")
    if (
        line.department_key != "acquisitions"
        or line.purpose_key != PROSPECTING_VOICE_LINE_PURPOSE
    ):
        raise ProspectingVoiceConfigurationError(
            "Assign a dedicated acquisitions line with the prospecting-outbound purpose."
        )


def dialer_lease_fingerprint(lease_token: str | None) -> str:
    if not lease_token:
        raise ProspectingVoiceConflictError("The dialer session has no active lease.")
    return hashlib.sha256(lease_token.encode("utf-8")).hexdigest()


def browser_voice_identity(session: ProspectingDialSession) -> str:
    if not session.browser_session_id:
        raise ProspectingVoiceConflictError("The dialer session has no browser owner.")
    binding = (
        f"{session.id}:{session.browser_session_id}:"
        f"{dialer_lease_fingerprint(session.lease_token)}"
    )
    digest = hashlib.sha256(binding.encode("utf-8")).hexdigest()[:24]
    return f"stonegate_p_{session.caller_user_id.hex}_{digest}"


def require_connection_mode(
    intent: VoiceCallIntent,
    expected: str,
    *,
    allow_legacy: bool = False,
) -> None:
    mode = connection_mode(intent)
    if allow_legacy and mode is None:
        return
    if mode != expected:
        raise ProspectingVoiceConflictError(
            "The prospecting call intent belongs to a different connection mode."
        )


def connection_mode(intent: VoiceCallIntent) -> str | None:
    mode = (intent.intent_metadata or {}).get("connection_mode")
    return mode if isinstance(mode, str) else None


def validate_browser_intent_lease_binding(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
) -> None:
    metadata = dict(intent.intent_metadata or {})
    browser_session_id = metadata.get("browser_session_id")
    lease_fingerprint = metadata.get("lease_fingerprint")
    if not isinstance(browser_session_id, str) or not isinstance(lease_fingerprint, str):
        raise ProspectingVoiceConfigurationError(
            "The browser call intent has no dialer lease binding."
        )
    if graph.session.browser_session_id != browser_session_id:
        raise ProspectingVoiceConflictError(
            "The browser call intent belongs to a stale browser session."
        )
    current_fingerprint = dialer_lease_fingerprint(graph.session.lease_token)
    if not secrets.compare_digest(current_fingerprint, lease_fingerprint):
        raise ProspectingVoiceConflictError(
            "The browser call intent belongs to a replaced dialer lease."
        )
    if (
        graph.session.lease_expires_at is None
        or as_utc(graph.session.lease_expires_at) <= datetime.now(UTC)
    ):
        raise ProspectingVoiceConflictError("The dialer lease expired and must be recovered.")
    if browser_voice_identity(graph.session) != metadata.get("voice_identity"):
        raise ProspectingVoiceConflictError(
            "The browser Voice identity no longer matches the dialer lease."
        )


def browser_intent_can_rebind(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
) -> bool:
    return bool(
        graph.session.state == "ready"
        and untouched_browser_call(graph, intent, call)
    )


def untouched_browser_call(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
) -> bool:
    """Return true only before the browser or Twilio has produced provider evidence."""

    return bool(
        connection_mode(intent) == PROSPECTING_BROWSER_CONNECTION_MODE
        and graph.leg.status == "queued"
        and graph.leg.provider_call_id is None
        and graph.attempt.provider_call_id is None
        and intent.status == "pending"
        and intent.consumed_at is None
        and intent.provider_call_id is None
        and provider_start_state(intent) == PROVIDER_START_PREPARED
        and call.status == "queued"
        and call.provider_call_id is None
        and call.child_provider_call_id is None
    )


def abandon_untouched_browser_call(
    db: Session,
    principal: Principal,
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
    *,
    now: datetime,
    reason: str,
    intent_status: Literal["cancelled", "expired"],
) -> None:
    """Release a browser-prepared call only when Twilio has never seen it."""

    if not untouched_browser_call(graph, intent, call):
        raise ProspectingVoiceConflictError(
            "The browser call has provider evidence and cannot be abandoned locally."
        )
    intent.status = intent_status
    intent.consumed_at = now
    set_provider_start_state(intent, PROVIDER_START_FAILED, now=now)
    intent_metadata = dict(intent.intent_metadata or {})
    intent_metadata["browser_pre_provider_terminal_reason"] = reason
    intent_metadata["browser_pre_provider_terminal_at"] = now.isoformat()
    intent.intent_metadata = intent_metadata
    call.status = "cancelled" if intent_status == "cancelled" else "failed"
    call.ended_at = now
    call_metadata = dict(call.call_metadata or {})
    call_metadata["browser_pre_provider_terminal_reason"] = reason
    call_metadata["browser_pre_provider_terminal_at"] = now.isoformat()
    call.call_metadata = call_metadata
    release_unstarted_reservation(
        db,
        graph.session,
        graph.leg,
        now=now,
        reason=reason,
        prepared_call_record_id=call.id,
    )
    reconcile_session_current_leg(db, graph.session, now=now)
    add_call_audit(
        db,
        principal,
        graph,
        call,
        action=(
            "prospecting.voice_browser_call_cancelled_before_provider"
            if intent_status == "cancelled"
            else "prospecting.voice_browser_call_expired_before_provider"
        ),
        reason=reason,
        extra={"provider_started": False, "intent_status": intent_status},
    )


def rebind_browser_intent(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    *,
    now: datetime,
) -> None:
    metadata = dict(intent.intent_metadata or {})
    metadata.update(
        {
            "browser_session_id": graph.session.browser_session_id,
            "lease_fingerprint": dialer_lease_fingerprint(graph.session.lease_token),
            "voice_identity": browser_voice_identity(graph.session),
            "browser_rebound_at": now.isoformat(),
        }
    )
    intent.intent_metadata = metadata
    intent.expires_at = now + timedelta(minutes=5)


def require_call_permission(principal: Principal) -> None:
    if PermissionKeys.WORK_ASSIGNED_CALLING_LISTS not in principal.permission_keys:
        raise PermissionError("Cold calling is not enabled for the current user.")
    if not (
        PermissionKeys.PLACE_CALLS in principal.permission_keys
        or PermissionKeys.PLACE_ASSIGNED_CALLS in principal.permission_keys
    ):
        raise PermissionError("The current user cannot place prospecting calls.")


def validate_voice_session_lease(
    session: ProspectingDialSession,
    payload: ProspectingVoiceCallCreate | ProspectingVoiceCallControl,
    *,
    now: datetime,
) -> None:
    try:
        validate_session_lease(session, payload, now=now)
    except ProspectingDialerConflictError as exc:
        raise ProspectingVoiceConflictError(str(exc)) from exc


def load_graph_call(
    db: Session,
    graph: ProspectingVoiceGraph,
    *,
    lock: bool = False,
) -> tuple[VoiceCallIntent, CallRecord]:
    call_statement = select(CallRecord).where(
        CallRecord.organization_id == graph.leg.organization_id,
        CallRecord.prospecting_dial_leg_id == graph.leg.id,
        CallRecord.prospect_id == graph.prospect.id,
    )
    if lock:
        call_statement = call_statement.with_for_update().execution_options(populate_existing=True)
    call = db.scalar(call_statement)
    if call is None or call.call_intent_id is None:
        raise ProspectingVoiceConflictError("This dial leg has no provider call.")
    intent_statement = select(VoiceCallIntent).where(
        VoiceCallIntent.id == call.call_intent_id,
        VoiceCallIntent.organization_id == graph.leg.organization_id,
        VoiceCallIntent.prospecting_dial_leg_id == graph.leg.id,
        VoiceCallIntent.prospect_id == graph.prospect.id,
    )
    if lock:
        intent_statement = intent_statement.with_for_update().execution_options(
            populate_existing=True
        )
    intent = db.scalar(intent_statement)
    if intent is None:
        raise ProspectingVoiceConfigurationError("The prospecting call intent is unavailable.")
    return intent, call


def attach_call_evidence(graph: ProspectingVoiceGraph, call: CallRecord) -> None:
    graph.leg.call_record_id = call.id
    graph.attempt.call_record_id = call.id
    graph.attempt.provider = graph.line.provider


def provider_start_state(intent: VoiceCallIntent) -> str:
    metadata = dict(intent.intent_metadata or {})
    state = metadata.get("provider_start_state")
    if isinstance(state, str) and state:
        return state
    if intent.provider_call_id is not None or intent.status == "started":
        return PROVIDER_START_STARTED
    if intent.status in {"failed", "expired"}:
        return PROVIDER_START_FAILED
    return PROVIDER_START_PREPARED


def set_provider_start_state(
    intent: VoiceCallIntent,
    state: str,
    *,
    now: datetime,
) -> None:
    metadata = dict(intent.intent_metadata or {})
    metadata["provider_start_state"] = state
    metadata[f"provider_start_{state}_at"] = now.isoformat()
    intent.intent_metadata = metadata


def attach_provider_result(
    db: Session,
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
    result: VoiceCallResult,
) -> None:
    ensure_root_provider_call_id(db, graph, call, result.sid)
    intent.status = "started"
    intent.consumed_at = datetime.now(UTC)
    intent.provider_call_id = result.sid
    if call.status in {"queued", "initiated"}:
        call.status = result.status


def mark_start_failure(
    db: Session,
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
    message: str,
    *,
    start_state: str = PROVIDER_START_FAILED,
) -> None:
    now = datetime.now(UTC)
    intent.status = "failed"
    intent.consumed_at = now
    set_provider_start_state(intent, start_state, now=now)
    call.status = "failed"
    call.ended_at = now
    graph.leg.provider_error_message = message[:2000]
    record_dial_provider_event(
        db,
        organization_id=graph.leg.organization_id,
        provider=graph.leg.provider,
        external_event_id=f"voice:start-failed:{intent.id}",
        event_type="call.failed",
        payload={"error": message, "source": "api"},
        dial_leg=graph.leg,
        occurred_at=now,
        signature_verified=False,
    )
    applied, _ = advance_dial_leg_provider_state(
        graph.leg,
        target_status="failed",
        provider_sequence_number=None,
        occurred_at=now,
    )
    if applied:
        reconcile_dial_session_from_leg(db, graph.leg, now=now)


def mark_control_failure(
    db: Session,
    graph: ProspectingVoiceGraph,
    *,
    action: str,
    message: str,
) -> None:
    now = datetime.now(UTC)
    graph.leg.provider_error_message = message[:2000]
    record_dial_provider_event(
        db,
        organization_id=graph.leg.organization_id,
        provider=graph.leg.provider,
        external_event_id=f"voice:{action}-failed:{graph.leg.id}",
        event_type=f"call.{action}_failed",
        payload={"error": message, "source": "api"},
        dial_leg=graph.leg,
        occurred_at=now,
        signature_verified=False,
    )


def reconcile_provider_result(
    db: Session,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    result: VoiceCallResult,
    *,
    event_id: str,
    event_type: str,
    cancellation_requested: bool = False,
) -> None:
    normalized_status = result.status.strip().lower()
    target_status = TWILIO_TO_DIAL_LEG_STATUS.get(normalized_status)
    if cancellation_requested and normalized_status in {"completed", "canceled", "cancelled"}:
        target_status = "cancelled"
    now = datetime.now(UTC)
    event, applied = record_dial_provider_event(
        db,
        organization_id=graph.leg.organization_id,
        provider=graph.leg.provider,
        external_event_id=event_id,
        event_type=event_type,
        payload={"CallSid": result.sid, "CallStatus": result.status, "source": "provider_api"},
        dial_leg=graph.leg,
        occurred_at=now,
        signature_verified=False,
    )
    event.provider_call_id = result.sid
    if target_status is not None:
        applied, _ = advance_dial_leg_provider_state(
            graph.leg,
            target_status=target_status,
            provider_sequence_number=None,
            occurred_at=now,
        )
        if applied:
            reconcile_dial_session_from_leg(db, graph.leg, now=now)
    if applied and target_status is not None:
        apply_reconciled_state(graph, call, target_status, {})


def callback_target_status(
    leg: ProspectingDialLeg,
    provider_status: str,
    *,
    is_contact_leg: bool,
) -> str | None:
    mapped = TWILIO_TO_DIAL_LEG_STATUS.get(provider_status)
    if is_contact_leg:
        if leg.status == "cancelling" and provider_status == "completed":
            return "cancelled"
        return mapped
    if provider_status in {"queued", "initiated"}:
        return "dialing"
    if provider_status in {"busy", "failed", "no-answer", "canceled", "cancelled"}:
        return mapped
    if provider_status == "completed":
        if leg.status == "cancelling":
            return "cancelled"
        # Root completion only means the staff bridge ended. The child callback or
        # Dial action carries the actual prospect outcome and may arrive later.
        return None
    # Ringing and answering the staff bridge do not mean the prospect is ringing or answered.
    return None


def apply_reconciled_state(
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    target_status: str,
    payload: dict[str, str],
) -> None:
    now = datetime.now(UTC)
    call.status = target_status
    duration = parse_int(
        payload.get("CallDuration") or payload.get("DialCallDuration") or payload.get("Duration")
    )
    if duration is not None:
        call.duration_seconds = duration
    if target_status in {"answered", "connected"}:
        call.answered_at = call.answered_at or now
        graph.attempt.answered_at = graph.attempt.answered_at or now
    if target_status in DIAL_LEG_TERMINAL_STATUSES:
        call.ended_at = call.ended_at or now


def prospecting_voice_call_read(
    graph: ProspectingVoiceGraph,
    intent: VoiceCallIntent,
    call: CallRecord,
    *,
    provider_status: str,
    recording_enabled: bool,
    control_action: Literal[
        "prepared",
        "started",
        "fetched",
        "cancelled",
        "hung_up",
        "replayed",
    ],
) -> ProspectingVoiceCallRead:
    if (
        intent.prospect_id is None
        or intent.prospecting_attempt_id is None
        or intent.prospecting_dial_leg_id is None
    ):
        raise ProspectingVoiceConfigurationError("Prospecting call context is incomplete.")
    return ProspectingVoiceCallRead(
        call_intent_id=intent.id,
        call_record_id=call.id,
        prospect_id=intent.prospect_id,
        attempt_id=intent.prospecting_attempt_id,
        dial_session_id=graph.session.id,
        dial_leg_id=intent.prospecting_dial_leg_id,
        provider=call.provider,
        provider_call_id=call.provider_call_id,
        provider_status=provider_status,
        recipient=intent.recipient,
        from_number=call.from_number or "",
        recording_enabled=recording_enabled,
        control_action=control_action,
        leg=dial_leg_read(graph.leg),
    )


def add_call_audit(
    db: Session,
    principal: Principal,
    graph: ProspectingVoiceGraph,
    call: CallRecord,
    *,
    action: str,
    reason: str,
    extra: dict[str, Any],
) -> None:
    db.add(
        AuditEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            actor_type="user",
            action=action,
            entity_type="prospecting_dial_leg",
            entity_id=graph.leg.id,
            previous_value=None,
            new_value={
                "prospect_id": str(graph.prospect.id),
                "attempt_id": str(graph.attempt.id),
                "dial_session_id": str(graph.session.id),
                "call_record_id": str(call.id),
                **extra,
            },
            reason=reason,
        )
    )


def prospecting_recording_status(settings: Settings) -> str:
    if not settings.twilio_voice_recording_configured:
        return "not_requested"
    return (
        "disclosure_configured"
        if settings.twilio_voice_recording_disclosure
        else "one_party_consent"
    )


def provider_occurred_at(payload: dict[str, str]) -> datetime:
    raw_value = payload.get("Timestamp") or payload.get("EventTimestamp")
    if raw_value:
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def parse_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
