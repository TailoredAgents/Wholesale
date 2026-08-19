from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import Settings, get_settings
from app.domain.rbac import PermissionKeys
from app.integrations.twilio_voice import (
    InboundVoiceTarget,
    hangup_twiml,
    inbound_call_twiml,
    voicemail_twiml,
)
from app.models.foundation import (
    ActivityEvent,
    CallRecord,
    CommunicationProviderEvent,
    Permission,
    Prospect,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectingAttempt,
    ProspectingDialSession,
    ProspectingInboundCallback,
    Role,
    RoleAssignment,
    RolePermission,
    Task,
    TeamMembership,
    User,
    VoiceLine,
)
from app.schemas.prospecting import (
    ProspectingCallbackMatchStatus,
    ProspectingCallbackStatus,
    ProspectingEntryRead,
    ProspectingInboundCallbackListRead,
    ProspectingInboundCallbackRead,
)
from app.services.communication_compliance import format_e164
from app.services.prospecting import entry_read

MATCH_LOOKBACK_DAYS = 90
CALLBACK_LIST_LIMIT = 100
ACTIVE_CALLBACK_TASK_STATUSES = ("open", "in_progress")


@dataclass(frozen=True)
class CallbackMatch:
    status: str
    strategy: str
    confidence_basis_points: int
    candidate_count: int
    prospect: Prospect | None
    attempt: ProspectingAttempt | None


def process_prospecting_inbound_callback(
    db: Session,
    line: VoiceLine,
    *,
    caller: str,
    provider_call_id: str,
    settings: Settings | None = None,
) -> str:
    active_settings = settings or get_settings()
    normalized_caller = format_e164(caller)
    if normalized_caller is None:
        raise ValueError("Inbound prospect callback has an invalid caller number.")
    existing = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.organization_id == line.organization_id,
            ProspectingInboundCallback.provider == line.provider,
            ProspectingInboundCallback.provider_call_id == provider_call_id,
        )
    )
    if existing is not None:
        return _existing_callback_twiml(db, line, existing, active_settings)

    now = datetime.now(UTC)
    match = match_recent_prospecting_callback(
        db,
        organization_id=line.organization_id,
        voice_line_id=line.id,
        caller_number=normalized_caller,
        now=now,
    )
    user_ids = resolve_prospecting_callback_users(
        db,
        line,
        match=match,
        settings=active_settings,
        now=now,
    )
    targets = resolve_prospecting_callback_targets(db, user_ids)
    routed_user_ids = [UUID(target.user_id) for target in targets]
    assigned_user_id = (
        routed_user_ids[0] if routed_user_ids else (user_ids[0] if user_ids else None)
    )
    fallback_user_id = next(
        (
            user_id
            for user_id in [*routed_user_ids[1:], *user_ids]
            if user_id != assigned_user_id
        ),
        None,
    )
    callback = ProspectingInboundCallback(
        organization_id=line.organization_id,
        voice_line_id=line.id,
        provider=line.provider,
        provider_call_id=provider_call_id,
        normalized_caller=normalized_caller,
        caller_number=normalized_caller,
        matched_prospect_id=match.prospect.id if match.prospect is not None else None,
        matched_attempt_id=match.attempt.id if match.attempt is not None else None,
        match_status=match.status,
        match_strategy=match.strategy,
        match_confidence_basis_points=match.confidence_basis_points,
        candidate_count=match.candidate_count,
        assigned_user_id=assigned_user_id,
        fallback_user_id=fallback_user_id,
        status="ringing" if targets else "routing",
        received_at=now,
        answered_at=None,
        completed_at=None,
        routing_metadata={
            "routing_target_user_ids": [target.user_id for target in targets],
            "ring_strategy": line.ring_strategy,
            "ring_target_count": len(targets),
            "match_lookback_days": MATCH_LOOKBACK_DAYS,
        },
    )
    try:
        with db.begin_nested():
            db.add(callback)
            db.flush()
    except IntegrityError:
        db.expire_all()
        existing = db.scalar(
            select(ProspectingInboundCallback).where(
                ProspectingInboundCallback.organization_id == line.organization_id,
                ProspectingInboundCallback.provider == line.provider,
                ProspectingInboundCallback.provider_call_id == provider_call_id,
            )
        )
        if existing is None:
            raise
        return _existing_callback_twiml(db, line, existing, active_settings)
    call = CallRecord(
        organization_id=line.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=match.prospect.id if match.prospect is not None else None,
        prospecting_attempt_id=match.attempt.id if match.attempt is not None else None,
        prospecting_dial_leg_id=None,
        prospecting_inbound_callback_id=callback.id,
        actor_user_id=assigned_user_id,
        communication_record_id=None,
        voice_line_id=line.id,
        call_intent_id=None,
        provider=line.provider,
        provider_call_id=provider_call_id,
        child_provider_call_id=None,
        direction="inbound",
        status="ringing" if targets else "no-answer",
        from_number=normalized_caller,
        to_number=line.phone_number,
        started_at=now,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status=_recording_consent_status(active_settings),
        call_metadata={
            "source": "prospecting_inbound_callback",
            "routing_target_user_ids": [target.user_id for target in targets],
            "routing_mobile_user_ids": [target.user_id for target in targets],
            "routing_owner_user_id": str(assigned_user_id) if assigned_user_id else None,
            "ring_strategy": line.ring_strategy,
            "ring_user_count": len(targets),
            "ring_target_count": len(targets),
        },
    )
    db.add(call)
    _record_callback_event(
        db,
        callback,
        event_type="voice.prospecting_callback_received",
        summary=(
            "Known prospect callback received."
            if match.status == "matched"
            else "Unmatched prospecting-line callback received for review."
        ),
    )
    db.add(
        CommunicationProviderEvent(
            organization_id=line.organization_id,
            conversation_id=None,
            provider=line.provider,
            event_type="voice.prospecting_callback",
            external_event_id=f"voice:prospecting-callback:{provider_call_id}",
            processing_status="processed",
            payload={
                "callback_id": str(callback.id),
                "match_status": match.status,
                "candidate_count": match.candidate_count,
            },
            received_at=now,
            processed_at=now,
            next_attempt_at=None,
            processing_started_at=None,
            processing_token=None,
            error_message=None,
        )
    )
    db.commit()
    if targets:
        return inbound_call_twiml(
            active_settings,
            targets=targets,
            call_id=str(call.id),
            recording_enabled=active_settings.twilio_voice_recording_configured,
            ring_strategy=line.ring_strategy,
        )
    if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
        callback.status = "voicemail"
        db.commit()
        return voicemail_twiml(active_settings, call_id=str(call.id))
    callback.status = "missed"
    callback.completed_at = now
    call.ended_at = now
    ensure_prospecting_missed_callback_task(db, call)
    db.commit()
    return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")


def match_recent_prospecting_callback(
    db: Session,
    *,
    organization_id: UUID,
    voice_line_id: UUID,
    caller_number: str,
    now: datetime | None = None,
) -> CallbackMatch:
    canonical = format_e164(caller_number)
    if canonical is None:
        return CallbackMatch("unknown", "invalid_phone", 0, 0, None, None)
    digits = "".join(character for character in canonical if character.isdigit())
    exact_values = (canonical, digits)
    prospect_ids = set(
        db.scalars(
            select(ProspectContactPoint.prospect_id).where(
                ProspectContactPoint.organization_id == organization_id,
                ProspectContactPoint.contact_type == "phone",
                ProspectContactPoint.normalized_value.in_(exact_values),
            )
        )
    )
    prospect_ids.update(
        db.scalars(
            select(Prospect.id).where(
                Prospect.organization_id == organization_id,
                Prospect.normalized_phone.in_(exact_values),
            )
        )
    )
    if not prospect_ids:
        return CallbackMatch("unknown", "exact_phone_no_prospect", 0, 0, None, None)

    cutoff = _as_utc(now or datetime.now(UTC)) - timedelta(days=MATCH_LOOKBACK_DAYS)
    attempts = list(
        db.scalars(
            select(ProspectingAttempt)
            .outerjoin(CallRecord, CallRecord.id == ProspectingAttempt.call_record_id)
            .where(
                ProspectingAttempt.organization_id == organization_id,
                ProspectingAttempt.prospect_id.in_(prospect_ids),
                ProspectingAttempt.started_at >= cutoff,
                CallRecord.voice_line_id == voice_line_id,
                CallRecord.prospecting_dial_leg_id.is_not(None),
                CallRecord.to_number.in_(exact_values),
                # The root provider call only proves Twilio reached Stonegate's
                # browser/cellphone bridge. A child call ID is the durable proof
                # that Twilio actually placed the seller-facing Number leg.
                CallRecord.child_provider_call_id.is_not(None),
            )
            .order_by(ProspectingAttempt.started_at.desc(), ProspectingAttempt.id.desc())
        ).unique()
    )
    latest_by_prospect: dict[UUID, ProspectingAttempt] = {}
    for attempt in attempts:
        latest_by_prospect.setdefault(attempt.prospect_id, attempt)
    if not latest_by_prospect:
        return CallbackMatch("unknown", "exact_phone_no_recent_line_attempt", 0, 0, None, None)
    candidate_count = len(latest_by_prospect)
    if candidate_count == 1:
        prospect_id, attempt = next(iter(latest_by_prospect.items()))
        prospect = db.get(Prospect, prospect_id)
        if prospect is None or prospect.organization_id != organization_id:
            return CallbackMatch("unknown", "prospect_unavailable", 0, 0, None, None)
        strong = _has_right_party_evidence(attempt)
        return CallbackMatch(
            "matched",
            (
                "exact_phone_recent_same_line_right_party"
                if strong
                else "exact_phone_recent_same_line"
            ),
            9500 if strong else 8000,
            1,
            prospect,
            attempt,
        )

    right_party_candidates = [
        attempt for attempt in latest_by_prospect.values() if _has_right_party_evidence(attempt)
    ]
    if len(right_party_candidates) == 1:
        attempt = right_party_candidates[0]
        prospect = db.get(Prospect, attempt.prospect_id)
        if prospect is not None and prospect.organization_id == organization_id:
            return CallbackMatch(
                "matched",
                "exact_phone_unique_right_party_same_line",
                9000,
                candidate_count,
                prospect,
                attempt,
            )
    return CallbackMatch(
        "ambiguous",
        "exact_phone_multiple_recent_same_line",
        0,
        candidate_count,
        None,
        None,
    )


def resolve_prospecting_callback_users(
    db: Session,
    line: VoiceLine,
    *,
    match: CallbackMatch,
    settings: Settings,
    now: datetime | None = None,
) -> list[UUID]:
    observed_at = _as_utc(now or datetime.now(UTC))
    batch_entry = _callback_batch_entry(db, line.organization_id, match)
    candidate_ids: list[UUID | None] = []
    if match.attempt is not None:
        candidate_ids.append(match.attempt.caller_user_id)
    if match.prospect is not None:
        candidate_ids.append(match.prospect.assigned_user_id)
        latest_entry_user = db.scalar(
            select(ProspectCallingBatchEntry.assigned_user_id)
            .where(
                ProspectCallingBatchEntry.organization_id == line.organization_id,
                ProspectCallingBatchEntry.prospect_id == match.prospect.id,
            )
            .order_by(
                ProspectCallingBatchEntry.last_attempt_at.desc().nullslast(),
                ProspectCallingBatchEntry.created_at.desc(),
            )
        )
        candidate_ids.append(latest_entry_user)

    result: list[UUID] = []
    for candidate_id in candidate_ids:
        if candidate_id is None or candidate_id in result:
            continue
        if not _user_can_open_batch_entry(
            db,
            line.organization_id,
            candidate_id,
            batch_entry,
        ):
            continue
        if _dialer_user_available(
            db,
            line.organization_id,
            line.id,
            candidate_id,
            settings,
            observed_at,
        ):
            result.append(candidate_id)

    configured_fallback_ids: list[UUID | None] = [
        line.fallback_user_id,
        line.assigned_user_id,
    ]
    if line.assigned_team_id is not None:
        configured_fallback_ids.extend(
            db.scalars(
                select(TeamMembership.user_id)
                .join(User, User.id == TeamMembership.user_id)
                .where(
                    TeamMembership.organization_id == line.organization_id,
                    TeamMembership.team_id == line.assigned_team_id,
                    User.is_active.is_(True),
                )
                .order_by(
                    (TeamMembership.membership_role == "manager").desc(),
                    TeamMembership.created_at,
                )
            )
        )
    approved_configured_count = 0
    for candidate_id in configured_fallback_ids:
        if candidate_id is None or candidate_id in result:
            continue
        user = db.scalar(
            select(User).where(
                User.id == candidate_id,
                User.organization_id == line.organization_id,
                User.is_active.is_(True),
            )
        )
        explicitly_approved_line_fallback = bool(
            user is not None
            and user.id == line.fallback_user_id
            and _user_has_permission(
                db,
                line.organization_id,
                user.id,
                PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
            )
        )
        if user is None or not (
            explicitly_approved_line_fallback
            or _user_can_open_batch_entry(
                db,
                line.organization_id,
                user.id,
                batch_entry,
            )
        ):
            continue
        result.append(user.id)
        approved_configured_count += 1

    if approved_configured_count == 0:
        owner_ids = db.scalars(
            select(User.id)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(
                User.organization_id == line.organization_id,
                RoleAssignment.organization_id == line.organization_id,
                Role.organization_id == line.organization_id,
                User.is_active.is_(True),
                Role.key.in_(("owner", "founder_operator", "ceo")),
            )
            .order_by(User.created_at)
        )
        for owner_id in owner_ids:
            if owner_id not in result and _user_can_open_batch_entry(
                db,
                line.organization_id,
                owner_id,
                batch_entry,
            ):
                result.append(owner_id)
    return result[:10]


def resolve_prospecting_callback_targets(
    db: Session,
    user_ids: list[UUID],
) -> list[InboundVoiceTarget]:
    targets: list[InboundVoiceTarget] = []
    for user_id in user_ids:
        if len(targets) >= 10:
            break
        user = db.get(User, user_id)
        forwarding_number = (
            format_e164(user.voice_forwarding_number or "")
            if user is not None and user.is_active and user.voice_forwarding_enabled
            else None
        )
        if user is None or forwarding_number is None:
            continue
        targets.append(
            InboundVoiceTarget(
                identity=f"stonegate_user_{user.id}",
                user_id=str(user.id),
                forwarding_number=forwarding_number,
            )
        )
    return targets


def _callback_batch_entry(
    db: Session,
    organization_id: UUID,
    match: CallbackMatch,
) -> ProspectCallingBatchEntry | None:
    if match.attempt is not None:
        entry = db.scalar(
            select(ProspectCallingBatchEntry).where(
                ProspectCallingBatchEntry.organization_id == organization_id,
                ProspectCallingBatchEntry.id == match.attempt.batch_entry_id,
            )
        )
        if entry is not None:
            return entry
    if match.prospect is None:
        return None
    return db.scalar(
        select(ProspectCallingBatchEntry)
        .where(
            ProspectCallingBatchEntry.organization_id == organization_id,
            ProspectCallingBatchEntry.prospect_id == match.prospect.id,
        )
        .order_by(
            ProspectCallingBatchEntry.last_attempt_at.desc().nullslast(),
            ProspectCallingBatchEntry.created_at.desc(),
        )
    )


def _user_can_open_batch_entry(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    entry: ProspectCallingBatchEntry | None,
) -> bool:
    if entry is not None and entry.assigned_user_id == user_id:
        return True
    return _user_has_permission(
        db,
        organization_id,
        user_id,
        PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
    )


def _user_has_permission(
    db: Session,
    organization_id: UUID,
    user_id: UUID,
    permission_key: str,
) -> bool:
    return (
        db.scalar(
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
            .where(
                RoleAssignment.organization_id == organization_id,
                RolePermission.organization_id == organization_id,
                RoleAssignment.user_id == user_id,
                Permission.key == permission_key,
            )
            .limit(1)
        )
        is not None
    )


def update_prospecting_callback_status(
    db: Session,
    call: CallRecord,
    status: str,
    *,
    aggregate_terminal: bool = False,
) -> None:
    if call.prospecting_inbound_callback_id is None:
        return
    callback = db.scalar(
        select(ProspectingInboundCallback)
        .where(
            ProspectingInboundCallback.id == call.prospecting_inbound_callback_id,
            ProspectingInboundCallback.organization_id == call.organization_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if callback is None:
        return
    if callback.status in {"voicemail", "missed", "completed", "failed", "canceled"}:
        return
    now = datetime.now(UTC)
    normalized_status = status.strip().lower()
    if normalized_status in {"initiated", "queued", "ringing"}:
        if callback.status in {"received", "routing", "ringing"}:
            callback.status = "ringing"
    elif normalized_status in {"in-progress", "answered"}:
        callback.status = "answered"
        callback.answered_at = callback.answered_at or now
        if call.actor_user_id is not None:
            callback.assigned_user_id = call.actor_user_id
    elif normalized_status == "completed":
        if aggregate_terminal:
            callback.status = "completed" if callback.answered_at is not None else "missed"
            callback.completed_at = callback.completed_at or now
    elif aggregate_terminal and normalized_status in {
        "busy",
        "failed",
        "no-answer",
        "canceled",
        "cancelled",
    }:
        callback.status = "missed"
        callback.completed_at = callback.completed_at or now


def complete_prospecting_callback_voicemail(db: Session, call: CallRecord) -> None:
    if call.prospecting_inbound_callback_id is None:
        return
    callback = db.get(ProspectingInboundCallback, call.prospecting_inbound_callback_id)
    if callback is None or callback.organization_id != call.organization_id:
        return
    callback.status = "voicemail"
    callback.completed_at = callback.completed_at or datetime.now(UTC)
    ensure_prospecting_missed_callback_task(db, call)


def ensure_prospecting_missed_callback_task(db: Session, call: CallRecord) -> None:
    callback_id = call.prospecting_inbound_callback_id
    if callback_id is None:
        return
    callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.id == callback_id,
            ProspectingInboundCallback.organization_id == call.organization_id,
        )
    )
    if callback is None:
        return
    existing = db.scalar(
        select(Task.id).where(
            Task.organization_id == call.organization_id,
            Task.prospecting_inbound_callback_id == callback.id,
            Task.task_type == "missed_prospecting_callback",
        )
    )
    if existing is not None:
        return
    task = Task(
        organization_id=call.organization_id,
        lead_id=None,
        deal_id=None,
        prospecting_inbound_callback_id=callback.id,
        prospect_id=callback.matched_prospect_id,
        call_record_id=call.id,
        responsible_user_id=callback.assigned_user_id or callback.fallback_user_id,
        task_type="missed_prospecting_callback",
        work_kind="supporting",
        title=f"Return prospect callback from {callback.caller_number}",
        status="open",
        priority="urgent",
        due_at=datetime.now(UTC) + timedelta(minutes=5),
        completed_at=None,
        completed_by_user_id=None,
        outcome=None,
        completion_notes=None,
        successor_task_id=None,
    )
    created = False
    try:
        with db.begin_nested():
            db.add(task)
            db.flush()
            created = True
    except IntegrityError:
        pass
    if created:
        _record_callback_event(
            db,
            callback,
            event_type="prospecting_callback.missed",
            summary="Missed prospect callback created an urgent return-call task.",
        )


def list_prospecting_inbound_callbacks(
    db: Session,
    principal: Principal,
    *,
    limit: int = 50,
) -> ProspectingInboundCallbackListRead:
    bounded_limit = max(1, min(limit, CALLBACK_LIST_LIMIT))
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    statement = select(ProspectingInboundCallback).where(
        ProspectingInboundCallback.organization_id == principal.organization_id
    )
    if not can_manage:
        statement = statement.where(
            or_(
                ProspectingInboundCallback.assigned_user_id == principal.user_id,
                ProspectingInboundCallback.fallback_user_id == principal.user_id,
            )
        )
    total = int(
        db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    )
    callbacks = list(
        db.scalars(
            statement.order_by(
                ProspectingInboundCallback.received_at.desc(),
                ProspectingInboundCallback.id.desc(),
            ).limit(bounded_limit)
        )
    )
    return ProspectingInboundCallbackListRead(
        items=[_callback_read(db, callback, principal) for callback in callbacks],
        total=total,
    )


def get_prospecting_callback_prospect(
    db: Session,
    principal: Principal,
    callback_id: UUID,
) -> ProspectingEntryRead | None:
    """Return immutable dialer context through the callback's narrow access grant."""

    statement = select(ProspectingInboundCallback).where(
        ProspectingInboundCallback.organization_id == principal.organization_id,
        ProspectingInboundCallback.id == callback_id,
    )
    if PermissionKeys.MANAGE_ACQUISITION_OPERATIONS not in principal.permission_keys:
        statement = statement.where(
            or_(
                ProspectingInboundCallback.assigned_user_id == principal.user_id,
                ProspectingInboundCallback.fallback_user_id == principal.user_id,
            )
        )
    callback = db.scalar(statement)
    if callback is None or callback.matched_attempt_id is None:
        return None
    attempt = db.scalar(
        select(ProspectingAttempt).where(
            ProspectingAttempt.organization_id == principal.organization_id,
            ProspectingAttempt.id == callback.matched_attempt_id,
        )
    )
    if attempt is None:
        return None
    entry = db.scalar(
        select(ProspectCallingBatchEntry).where(
            ProspectCallingBatchEntry.organization_id == principal.organization_id,
            ProspectCallingBatchEntry.id == attempt.batch_entry_id,
            ProspectCallingBatchEntry.prospect_id == callback.matched_prospect_id,
        )
    )
    return entry_read(db, entry) if entry is not None else None


def _callback_read(
    db: Session,
    callback: ProspectingInboundCallback,
    principal: Principal,
) -> ProspectingInboundCallbackRead:
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.organization_id == callback.organization_id,
            VoiceLine.id == callback.voice_line_id,
        )
    )
    prospect = (
        db.scalar(
            select(Prospect).where(
                Prospect.organization_id == callback.organization_id,
                Prospect.id == callback.matched_prospect_id,
            )
        )
        if callback.matched_prospect_id is not None
        else None
    )
    attempt = (
        db.scalar(
            select(ProspectingAttempt).where(
                ProspectingAttempt.organization_id == callback.organization_id,
                ProspectingAttempt.id == callback.matched_attempt_id,
            )
        )
        if callback.matched_attempt_id is not None
        else None
    )
    batch_entry = None
    if attempt is not None:
        batch_entry = db.scalar(
            select(ProspectCallingBatchEntry).where(
                ProspectCallingBatchEntry.organization_id == callback.organization_id,
                ProspectCallingBatchEntry.id == attempt.batch_entry_id,
            )
        )
    if batch_entry is None and prospect is not None:
        batch_entry = db.scalar(
            select(ProspectCallingBatchEntry)
            .where(
                ProspectCallingBatchEntry.organization_id == callback.organization_id,
                ProspectCallingBatchEntry.prospect_id == prospect.id,
            )
            .order_by(
                ProspectCallingBatchEntry.last_attempt_at.desc().nullslast(),
                ProspectCallingBatchEntry.created_at.desc(),
            )
        )
    batch_entry_id = batch_entry.id if batch_entry is not None else None
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == callback.organization_id,
            CallRecord.prospecting_inbound_callback_id == callback.id,
        )
    )
    missed_task_id = db.scalar(
        select(Task.id).where(
            Task.organization_id == callback.organization_id,
            Task.prospecting_inbound_callback_id == callback.id,
            Task.task_type == "missed_prospecting_callback",
        )
    )
    assigned_user = (
        db.scalar(
            select(User).where(
                User.organization_id == callback.organization_id,
                User.id == callback.assigned_user_id,
            )
        )
        if callback.assigned_user_id is not None
        else None
    )
    can_manage = PermissionKeys.MANAGE_ACQUISITION_OPERATIONS in principal.permission_keys
    has_callback_scope = principal.user_id in {
        callback.assigned_user_id,
        callback.fallback_user_id,
    }
    can_open_callback = bool(
        has_callback_scope
        and PermissionKeys.WORK_ASSIGNED_CALLING_LISTS in principal.permission_keys
    )
    address_parts = (
        [prospect.street_address, prospect.city, prospect.state_code, prospect.postal_code]
        if prospect is not None
        else []
    )
    return ProspectingInboundCallbackRead(
        id=callback.id,
        voice_line_id=callback.voice_line_id,
        voice_line_label=line.label if line is not None else "Prospecting line",
        caller_number=callback.caller_number,
        match_status=cast(ProspectingCallbackMatchStatus, callback.match_status),
        match_strategy=callback.match_strategy or "unclassified",
        match_confidence_basis_points=callback.match_confidence_basis_points or 0,
        candidate_count=callback.candidate_count,
        matched_prospect_id=callback.matched_prospect_id,
        matched_attempt_id=callback.matched_attempt_id,
        batch_entry_id=batch_entry_id,
        can_open=bool(
            prospect is not None
            and batch_entry_id is not None
            and (can_manage or can_open_callback)
        ),
        prospect_name=prospect.legal_name if prospect is not None else None,
        property_address=", ".join(part for part in address_parts if part) or None,
        assigned_user_id=callback.assigned_user_id,
        assigned_user_name=assigned_user.display_name if assigned_user is not None else None,
        fallback_user_id=callback.fallback_user_id,
        status=cast(ProspectingCallbackStatus, callback.status),
        call_record_id=call.id if call is not None else None,
        missed_task_id=missed_task_id,
        received_at=callback.received_at,
        answered_at=callback.answered_at,
        completed_at=callback.completed_at,
        created_at=callback.created_at,
        updated_at=callback.updated_at,
    )


def _existing_callback_twiml(
    db: Session,
    line: VoiceLine,
    callback: ProspectingInboundCallback,
    settings: Settings,
) -> str:
    call = db.scalar(
        select(CallRecord).where(
            CallRecord.organization_id == callback.organization_id,
            CallRecord.prospecting_inbound_callback_id == callback.id,
        )
    )
    if call is None:
        return hangup_twiml("Stonegate is unavailable. Please try again shortly.")
    if callback.status not in {"received", "routing", "ringing"}:
        return hangup_twiml()
    raw_ids = (callback.routing_metadata or {}).get("routing_target_user_ids") or []
    user_ids: list[UUID] = []
    for raw_id in raw_ids:
        try:
            user_ids.append(UUID(str(raw_id)))
        except ValueError:
            continue
    targets = resolve_prospecting_callback_targets(db, user_ids)
    if targets:
        return inbound_call_twiml(
            settings,
            targets=targets,
            call_id=str(call.id),
            recording_enabled=settings.twilio_voice_recording_configured,
            ring_strategy=line.ring_strategy,
        )
    if line.missed_call_action in {"voicemail", "fallback_then_voicemail"}:
        callback.status = "voicemail"
        db.commit()
        return voicemail_twiml(settings, call_id=str(call.id))
    callback.status = "missed"
    callback.completed_at = callback.completed_at or datetime.now(UTC)
    ensure_prospecting_missed_callback_task(db, call)
    db.commit()
    return hangup_twiml("Stonegate is unavailable. We will return your call shortly.")


def _dialer_user_available(
    db: Session,
    organization_id: UUID,
    voice_line_id: UUID,
    user_id: UUID,
    settings: Settings,
    now: datetime,
) -> bool:
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
            User.calling_enabled.is_(True),
        )
    )
    if user is None:
        return False
    stale_before = now - timedelta(
        seconds=settings.prospecting_native_dialer_stale_after_seconds
    )
    return (
        db.scalar(
            select(ProspectingDialSession.id).where(
                ProspectingDialSession.organization_id == organization_id,
                ProspectingDialSession.caller_user_id == user_id,
                ProspectingDialSession.voice_line_id == voice_line_id,
                ProspectingDialSession.ended_at.is_(None),
                ProspectingDialSession.state == "ready",
                ProspectingDialSession.heartbeat_at >= stale_before,
                ProspectingDialSession.lease_expires_at.is_not(None),
                ProspectingDialSession.lease_expires_at > now,
            )
        )
        is not None
    )


def _has_right_party_evidence(attempt: ProspectingAttempt) -> bool:
    return bool(
        attempt.right_party_confirmed_at is not None
        or (attempt.contact_made is True and attempt.party_classification == "right_party")
    )


def _record_callback_event(
    db: Session,
    callback: ProspectingInboundCallback,
    *,
    event_type: str,
    summary: str,
) -> None:
    entity_type = "prospect" if callback.matched_prospect_id is not None else "prospecting_callback"
    entity_id = callback.matched_prospect_id or callback.id
    db.add(
        ActivityEvent(
            organization_id=callback.organization_id,
            actor_user_id=None,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            summary=summary,
        )
    )


def _recording_consent_status(settings: Settings) -> str:
    if not settings.twilio_voice_recording_configured:
        return "not_requested"
    return (
        "disclosure_configured"
        if settings.twilio_voice_recording_disclosure
        else "one_party_consent"
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
