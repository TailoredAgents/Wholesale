from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.models.foundation import (
    ActivityEvent,
    CallRecord,
    Contact,
    Property,
    Prospect,
    ProspectingInboundCallback,
    User,
    VoiceLine,
)
from app.schemas.voice import (
    MarinCallDashboardRead,
    MarinCallDetailRead,
    MarinCallDiagnosticsRead,
    MarinCallListItemRead,
    MarinCallReviewRead,
    MarinCallReviewUpdate,
    MarinCallStatsRead,
    MarinReviewFlag,
    MarinToolEventRead,
    MarinTranscriptTurnRead,
)
from app.services.realtime_seller_agent import _is_suspected_transcription_hallucination

PROVIDER = "openai_realtime"
DEFAULT_TIMEZONE = "America/New_York"
TERMINAL_CALLBACK_STATUSES = frozenset({"completed", "failed", "canceled"})
KNOWN_REVIEW_FLAGS = frozenset(
    {
        "awkward_wording",
        "interruption",
        "wrong_information",
        "missed_intent",
        "poor_qualification",
        "failed_transfer",
        "technical_failure",
        "privacy_or_compliance",
    }
)


def list_marin_calls(
    db: Session,
    principal: Principal,
    *,
    days: int = 30,
    limit: int = 100,
) -> MarinCallDashboardRead:
    now = datetime.now(UTC)
    bounded_days = max(1, min(days, 365))
    bounded_limit = max(1, min(limit, 200))
    window_start = now - timedelta(days=bounded_days)
    query_start = now - timedelta(days=max(bounded_days, 30))
    rows = list(
        db.execute(
            select(ProspectingInboundCallback, CallRecord)
            .outerjoin(
                CallRecord,
                CallRecord.prospecting_inbound_callback_id == ProspectingInboundCallback.id,
            )
            .where(
                ProspectingInboundCallback.organization_id == principal.organization_id,
                ProspectingInboundCallback.provider == PROVIDER,
                ProspectingInboundCallback.received_at >= query_start,
            )
            .order_by(
                ProspectingInboundCallback.received_at.desc(),
                ProspectingInboundCallback.id.desc(),
            )
        ).all()
    )
    window_rows = [row for row in rows if _as_utc(row[0].received_at) >= window_start]
    identity_context = _identity_context(
        db,
        principal.organization_id,
        [row[0] for row in window_rows],
    )
    items = [
        _call_item(callback, record, identity_context.get(callback.id, {}))
        for callback, record in window_rows[:bounded_limit]
    ]
    total_calls = int(
        db.scalar(
            select(func.count())
            .select_from(ProspectingInboundCallback)
            .where(
                ProspectingInboundCallback.organization_id == principal.organization_id,
                ProspectingInboundCallback.provider == PROVIDER,
            )
        )
        or 0
    )
    total_unique_callers = int(
        db.scalar(
            select(func.count(func.distinct(ProspectingInboundCallback.normalized_caller))).where(
                ProspectingInboundCallback.organization_id == principal.organization_id,
                ProspectingInboundCallback.provider == PROVIDER,
            )
        )
        or 0
    )
    timezone_name, today_start = _today_start(db, principal.organization_id, now)
    stats_rows = [row for row in rows if _as_utc(row[0].received_at) >= now - timedelta(days=30)]
    caller_counts = Counter(
        row[0].normalized_caller for row in stats_rows if row[0].normalized_caller
    )
    durations = [
        row[1].duration_seconds
        for row in stats_rows
        if row[1] is not None and row[1].duration_seconds is not None
    ]
    capture_statuses = [_capture_status(row[0]) for row in stats_rows]
    call_path_statuses = [_call_path_status(*row) for row in stats_rows]
    stats = MarinCallStatsRead(
        timezone=timezone_name,
        total_calls=total_calls,
        total_unique_callers=total_unique_callers,
        calls_today=sum(_as_utc(row[0].received_at) >= today_start for row in stats_rows),
        calls_7_days=sum(
            _as_utc(row[0].received_at) >= now - timedelta(days=7) for row in stats_rows
        ),
        calls_30_days=len(stats_rows),
        unique_callers_30_days=len(caller_counts),
        repeat_callers_30_days=sum(count > 1 for count in caller_counts.values()),
        completed_calls_30_days=sum(row[0].status == "completed" for row in stats_rows),
        failed_calls_30_days=sum(row[0].status == "failed" for row in stats_rows),
        transferred_calls_30_days=sum(_outcome(*row) == "transferred" for row in stats_rows),
        scheduled_callbacks_30_days=sum(
            _outcome(*row) == "callback_scheduled" for row in stats_rows
        ),
        interested_calls_30_days=sum(_outcome(*row) == "interested" for row in stats_rows),
        conversations_started_30_days=sum(
            status == "conversation_started" for status in call_path_statuses
        ),
        ended_during_greeting_30_days=sum(
            status == "ended_during_greeting" for status in call_path_statuses
        ),
        no_caller_response_30_days=sum(
            status == "no_caller_response" for status in call_path_statuses
        ),
        caller_audio_issues_30_days=sum(
            status == "caller_audio_not_transcribed" for status in call_path_statuses
        ),
        seller_callbacks_captured_30_days=sum(
            status in {"provisional", "qualified"} for status in capture_statuses
        ),
        fully_qualified_sellers_30_days=sum(status == "qualified" for status in capture_statuses),
        leads_created_30_days=sum(
            bool((row[0].routing_metadata or {}).get("lead_created_by_agent")) for row in stats_rows
        ),
        needs_review=sum(bool(_review_reasons(*row)) for row in stats_rows),
        average_duration_seconds_30_days=(
            round(sum(durations) / len(durations)) if durations else None
        ),
    )
    return MarinCallDashboardRead(
        items=items,
        total=len(window_rows),
        stats=stats,
        generated_at=now,
    )


def get_marin_call(
    db: Session,
    principal: Principal,
    callback_id: UUID,
) -> MarinCallDetailRead | None:
    row = db.execute(
        select(ProspectingInboundCallback, CallRecord)
        .outerjoin(
            CallRecord,
            CallRecord.prospecting_inbound_callback_id == ProspectingInboundCallback.id,
        )
        .where(
            ProspectingInboundCallback.organization_id == principal.organization_id,
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.id == callback_id,
        )
    ).one_or_none()
    if row is None:
        return None
    callback, record = row
    identity = _identity_context(db, principal.organization_id, [callback]).get(callback.id, {})
    metadata = dict(callback.routing_metadata or {})
    transcript = _transcript(callback, record)
    captured_details = metadata.get("seller_details")
    if not isinstance(captured_details, dict):
        captured_details = {}
    tool_events = _tool_events(metadata)
    return MarinCallDetailRead(
        **_call_item(callback, record, identity).model_dump(),
        transcript=transcript,
        diagnostics=_diagnostics(callback, record, transcript),
        captured_details=captured_details,
        tool_events=tool_events,
        callback_at=_parse_datetime(metadata.get("callback_at")),
        callback_reason=_text(metadata.get("callback_reason")),
        transfer_number=_text(metadata.get("transfer_number")),
    )


def review_marin_call(
    db: Session,
    principal: Principal,
    callback_id: UUID,
    payload: MarinCallReviewUpdate,
) -> MarinCallDetailRead | None:
    callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.organization_id == principal.organization_id,
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.id == callback_id,
        )
    )
    if callback is None:
        return None
    flags = list(dict.fromkeys(payload.flags))
    if payload.status == "flagged" and not flags:
        raise ValueError("Choose at least one issue before flagging this call.")
    if payload.status == "reviewed" and flags:
        raise ValueError("Clear the issue flags or save this call as flagged.")
    reviewer = db.get(User, principal.user_id)
    reviewed_at = datetime.now(UTC)
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "marin_review": {
            "status": payload.status,
            "flags": flags,
            "notes": (payload.notes or "").strip() or None,
            "reviewed_by_user_id": str(principal.user_id),
            "reviewer_name": reviewer.display_name if reviewer is not None else principal.email,
            "reviewed_at": reviewed_at.isoformat(),
        },
    }
    db.add(
        ActivityEvent(
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            entity_type="prospecting_inbound_callback",
            entity_id=callback.id,
            event_type=f"voice.marin_call_{payload.status}",
            summary=(
                f"Marin call marked {payload.status}."
                if not flags
                else f"Marin call marked {payload.status}: {', '.join(flags)}."
            ),
        )
    )
    db.commit()
    return get_marin_call(db, principal, callback_id)


def _call_item(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
    identity: dict[str, Any],
) -> MarinCallListItemRead:
    metadata = dict(callback.routing_metadata or {})
    transcript = _transcript(callback, record)
    reasons = _review_reasons(callback, record)
    return MarinCallListItemRead(
        id=callback.id,
        call_record_id=record.id if record is not None else None,
        caller_number=callback.caller_number,
        seller_name=identity.get("seller_name"),
        property_address=identity.get("property_address"),
        lead_id=identity.get("lead_id"),
        status=callback.status,
        outcome=_outcome(callback, record),
        call_path_status=_call_path_status(callback, record, transcript),
        capture_status=_capture_status(callback),
        summary=_text(metadata.get("summary")),
        received_at=callback.received_at,
        answered_at=callback.answered_at,
        completed_at=callback.completed_at,
        duration_seconds=record.duration_seconds if record is not None else None,
        transcript_available=bool(transcript),
        transcript_turn_count=len(transcript),
        model=_text(metadata.get("model")),
        voice=_text(metadata.get("voice")),
        prompt_version=_text(metadata.get("prompt_version")),
        error=_text(metadata.get("error")),
        needs_review=bool(reasons),
        review_reasons=reasons,
        review=_review(metadata),
    )


def _identity_context(
    db: Session,
    organization_id: UUID,
    callbacks: list[ProspectingInboundCallback],
) -> dict[UUID, dict[str, Any]]:
    contact_ids: set[UUID] = set()
    property_ids: set[UUID] = set()
    prospect_ids: set[UUID] = set()
    for callback in callbacks:
        metadata = callback.routing_metadata or {}
        if contact_id := _uuid(metadata.get("verified_contact_id")):
            contact_ids.add(contact_id)
        if property_id := _uuid(metadata.get("verified_property_id")):
            property_ids.add(property_id)
        if prospect_id := _uuid(metadata.get("verified_prospect_id")):
            prospect_ids.add(prospect_id)
    contacts = {
        item.id: item
        for item in db.scalars(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.id.in_(contact_ids),
            )
        )
    }
    properties = {
        item.id: item
        for item in db.scalars(
            select(Property).where(
                Property.organization_id == organization_id,
                Property.id.in_(property_ids),
            )
        )
    }
    prospects = {
        item.id: item
        for item in db.scalars(
            select(Prospect).where(
                Prospect.organization_id == organization_id,
                Prospect.id.in_(prospect_ids),
            )
        )
    }
    result: dict[UUID, dict[str, Any]] = {}
    for callback in callbacks:
        metadata = callback.routing_metadata or {}
        details = metadata.get("seller_details")
        details = details if isinstance(details, dict) else {}
        contact_id = _uuid(metadata.get("verified_contact_id"))
        property_id = _uuid(metadata.get("verified_property_id"))
        prospect_id = _uuid(metadata.get("verified_prospect_id"))
        contact = contacts.get(contact_id) if contact_id is not None else None
        property_record = properties.get(property_id) if property_id is not None else None
        prospect = prospects.get(prospect_id) if prospect_id is not None else None
        seller_name = (
            contact.legal_name
            if contact is not None
            else prospect.legal_name
            if prospect is not None
            else _text(details.get("seller_name"))
        )
        property_address = (
            _property_label(property_record)
            if property_record is not None
            else _prospect_property_label(prospect)
            if prospect is not None
            else _details_property_label(details)
        )
        result[callback.id] = {
            "seller_name": seller_name,
            "property_address": property_address,
            "lead_id": _uuid(metadata.get("verified_lead_id")),
        }
    return result


def _transcript(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
) -> list[MarinTranscriptTurnRead]:
    callback_metadata = callback.routing_metadata or {}
    record_metadata = record.call_metadata or {} if record is not None else {}
    raw = record_metadata.get("transcript") or callback_metadata.get("transcript") or []
    if not isinstance(raw, list):
        return []
    turns: list[MarinTranscriptTurnRead] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").lower()
        text = _text(item.get("text"))
        if speaker not in {"caller", "marin"} or not text:
            continue
        if speaker == "caller" and _is_suspected_transcription_hallucination(text):
            continue
        turns.append(
            MarinTranscriptTurnRead(
                speaker=cast(Literal["caller", "marin"], speaker),
                text=text,
            )
        )
    return turns


def _tool_events(metadata: dict[str, Any]) -> list[MarinToolEventRead]:
    raw = metadata.get("tool_events")
    if not isinstance(raw, list):
        return []
    result: list[MarinToolEventRead] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name:
            continue
        result.append(
            MarinToolEventRead(
                name=name,
                succeeded=bool(item.get("succeeded")),
                occurred_at=_parse_datetime(item.get("occurred_at")),
            )
        )
    return result


def _review(metadata: dict[str, Any]) -> MarinCallReviewRead:
    raw = metadata.get("marin_review")
    if not isinstance(raw, dict):
        raw = {}
    raw_status = str(raw.get("status") or "unreviewed")
    status = cast(
        Literal["unreviewed", "reviewed", "flagged", "resolved"],
        raw_status
        if raw_status in {"unreviewed", "reviewed", "flagged", "resolved"}
        else "unreviewed",
    )
    raw_flags = raw.get("flags")
    flags = (
        [
            cast(MarinReviewFlag, item)
            for item in raw_flags
            if isinstance(item, str) and item in KNOWN_REVIEW_FLAGS
        ]
        if isinstance(raw_flags, list)
        else []
    )
    return MarinCallReviewRead(
        status=status,
        flags=flags,
        notes=_text(raw.get("notes")),
        reviewed_by_user_id=_uuid(raw.get("reviewed_by_user_id")),
        reviewer_name=_text(raw.get("reviewer_name")),
        reviewed_at=_parse_datetime(raw.get("reviewed_at")),
    )


def _review_reasons(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
) -> list[str]:
    metadata = dict(callback.routing_metadata or {})
    review = _review(metadata)
    if review.status in {"reviewed", "resolved"}:
        return []
    if review.status == "flagged":
        return ["Flagged by a reviewer"]
    reasons: list[str] = []
    outcome = _outcome(callback, record)
    if callback.status == "failed" or outcome == "agent_failed" or metadata.get("error"):
        reasons.append("Technical failure")
    if outcome == "timed_out":
        reasons.append("Call reached the time limit")
    if outcome == "incomplete" and callback.status in TERMINAL_CALLBACK_STATUSES:
        reasons.append("No final outcome was recorded")
    if metadata.get("transfer_requested_at") and not metadata.get("transferred_at"):
        reasons.append("Transfer may not have completed")
    if _call_path_status(callback, record) == "caller_audio_not_transcribed":
        reasons.append("Caller audio was detected but not transcribed")
    if (
        callback.status in TERMINAL_CALLBACK_STATUSES
        and record is not None
        and (record.duration_seconds or 0) >= 10
        and not _transcript(callback, record)
    ):
        reasons.append("Transcript is missing")
    return list(dict.fromkeys(reasons))


def _diagnostics(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
    transcript: list[MarinTranscriptTurnRead] | None = None,
) -> MarinCallDiagnosticsRead:
    raw = _diagnostic_metadata(callback, record)
    return MarinCallDiagnosticsRead(
        call_path_status=_call_path_status(callback, record, transcript),
        caller_speech_detected=_diagnostic_count(raw, "caller_speech_started_count") > 0,
        caller_speech_turns=_diagnostic_count(raw, "caller_speech_started_count"),
        caller_transcript_turns=_diagnostic_count(raw, "caller_transcript_count"),
        transcription_failures=_diagnostic_count(raw, "transcription_failed_count"),
        discarded_transcripts=_diagnostic_count(raw, "discarded_transcription_count"),
        opening_audio_started=_diagnostic_count(raw, "output_audio_started_count") > 0,
        opening_audio_completed=_diagnostic_count(raw, "output_audio_stopped_count") > 0,
        connection_close_type=_text(raw.get("monitor_close_type")),
        connection_close_code=(
            raw.get("monitor_close_code")
            if isinstance(raw.get("monitor_close_code"), int)
            else None
        ),
    )


def _call_path_status(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
    transcript: list[MarinTranscriptTurnRead] | None = None,
) -> Literal[
    "in_progress",
    "conversation_started",
    "ended_during_greeting",
    "no_caller_response",
    "caller_audio_not_transcribed",
    "technical_failure",
    "diagnostics_unavailable",
]:
    metadata = callback.routing_metadata or {}
    if callback.status not in TERMINAL_CALLBACK_STATUSES:
        return "in_progress"
    if (
        callback.status == "failed"
        or _outcome(callback, record) == "agent_failed"
        or metadata.get("error")
    ):
        return "technical_failure"
    turns = transcript if transcript is not None else _transcript(callback, record)
    if any(turn.speaker == "caller" for turn in turns):
        return "conversation_started"
    diagnostics = _diagnostic_metadata(callback, record)
    if not diagnostics:
        return "diagnostics_unavailable"
    caller_speech = _diagnostic_count(diagnostics, "caller_speech_started_count")
    transcription_failures = _diagnostic_count(diagnostics, "transcription_failed_count")
    discarded = _diagnostic_count(diagnostics, "discarded_transcription_count")
    if caller_speech or transcription_failures or discarded:
        return "caller_audio_not_transcribed"
    opening_started = _diagnostic_count(diagnostics, "output_audio_started_count") > 0
    opening_completed = _diagnostic_count(diagnostics, "output_audio_stopped_count") > 0
    if opening_started and not opening_completed:
        return "ended_during_greeting"
    if opening_completed:
        return "no_caller_response"
    return "diagnostics_unavailable"


def _diagnostic_metadata(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
) -> dict[str, Any]:
    record_metadata = record.call_metadata or {} if record is not None else {}
    callback_metadata = callback.routing_metadata or {}
    raw = record_metadata.get("call_diagnostics") or callback_metadata.get("call_diagnostics")
    return raw if isinstance(raw, dict) else {}


def _diagnostic_count(metadata: dict[str, Any], key: str) -> int:
    value = metadata.get(key)
    return max(0, value) if isinstance(value, int) else 0


def _outcome(
    callback: ProspectingInboundCallback,
    record: CallRecord | None,
) -> str:
    metadata = callback.routing_metadata or {}
    value = metadata.get("outcome") or (record.disposition if record is not None else None)
    if value:
        return str(value)
    return "in_progress" if callback.status not in TERMINAL_CALLBACK_STATUSES else "incomplete"


def _capture_status(
    callback: ProspectingInboundCallback,
) -> Literal["none", "provisional", "qualified"]:
    metadata = callback.routing_metadata or {}
    value = metadata.get("lead_capture_status")
    if value in {"provisional", "qualified"}:
        return cast(Literal["provisional", "qualified"], value)
    details = metadata.get("seller_details")
    if (
        isinstance(details, dict)
        and details.get("owner_confirmed") is True
        and details.get("seller_interested") is True
        and metadata.get("verified_lead_id")
    ):
        return "qualified"
    if metadata.get("seller_interest_captured_at") and metadata.get("verified_lead_id"):
        return "provisional"
    return "none"


def _today_start(
    db: Session,
    organization_id: UUID,
    now: datetime,
) -> tuple[str, datetime]:
    timezone_name = (
        db.scalar(
            select(VoiceLine.coverage_timezone)
            .where(
                VoiceLine.organization_id == organization_id,
                VoiceLine.purpose_key == "seller_callback_ai",
                VoiceLine.status == "active",
            )
            .order_by(VoiceLine.is_default.desc(), VoiceLine.created_at)
        )
        or DEFAULT_TIMEZONE
    )
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = DEFAULT_TIMEZONE
        local_timezone = ZoneInfo(DEFAULT_TIMEZONE)
    local_now = now.astimezone(local_timezone)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return timezone_name, local_start.astimezone(UTC)


def _property_label(property_record: Property) -> str | None:
    return _join_address(
        property_record.street_address,
        property_record.city,
        property_record.state,
        property_record.postal_code,
    )


def _prospect_property_label(prospect: Prospect) -> str | None:
    return _join_address(
        prospect.street_address,
        prospect.city,
        prospect.state_code,
        prospect.postal_code,
    )


def _details_property_label(details: dict[str, Any]) -> str | None:
    return _join_address(
        _text(details.get("street_address")),
        _text(details.get("city")),
        _text(details.get("state")),
        _text(details.get("postal_code")),
    )


def _join_address(*parts: str | None) -> str | None:
    values = [part.strip() for part in parts if part and part.strip()]
    return ", ".join(values) or None


def _uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
