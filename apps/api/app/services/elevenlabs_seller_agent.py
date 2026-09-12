from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.foundation import (
    ActivityEvent,
    CallRecord,
    CommunicationProviderEvent,
    CommunicationRecord,
    ProspectingInboundCallback,
    VoiceLine,
)
from app.services.communication_compliance import format_e164
from app.services.realtime_seller_agent import (
    FINAL_OUTCOMES,
    RealtimeSellerAgentError,
    _communication_body,
    _set_call_duration,
    execute_seller_agent_tool,
)

PROVIDER = "elevenlabs"
AGENT_NAME = "Caroline"
SOURCE = "elevenlabs_seller_callback"
MAX_TRANSCRIPT_CHARS = 40_000


@dataclass(frozen=True)
class RegisteredElevenLabsCall:
    conversation_id: str
    callback_id: UUID
    call_record_id: UUID
    created: bool


def register_elevenlabs_call(
    db: Session,
    *,
    conversation_id: str,
    caller_number: str,
    called_number: str,
    call_sid: str | None,
    agent_id: str,
    settings: Settings | None = None,
    received_at: datetime | None = None,
) -> RegisteredElevenLabsCall:
    active_settings = settings or get_settings()
    clean_conversation_id = conversation_id.strip()
    clean_agent_id = agent_id.strip()
    normalized_caller = format_e164(caller_number)
    normalized_called = format_e164(called_number)
    expected_number = format_e164(active_settings.elevenlabs_line_number)
    if not clean_conversation_id:
        raise RealtimeSellerAgentError("ElevenLabs did not include a conversation ID.")
    if (
        active_settings.elevenlabs_agent_id
        and clean_agent_id != active_settings.elevenlabs_agent_id
    ):
        raise RealtimeSellerAgentError("The call belongs to a different ElevenLabs agent.")
    if normalized_caller is None or normalized_called is None:
        raise RealtimeSellerAgentError("ElevenLabs supplied invalid call phone numbers.")
    if expected_number is None or normalized_called != expected_number:
        raise RealtimeSellerAgentError(
            "The call was not addressed to Stonegate's AI callback line."
        )
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.phone_number == normalized_called,
            VoiceLine.department_key == "acquisitions",
            VoiceLine.purpose_key == "seller_callback_ai",
            VoiceLine.status == "active",
        )
    )
    if line is None:
        raise RealtimeSellerAgentError("Stonegate's AI callback line is not active.")
    existing = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.organization_id == line.organization_id,
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == clean_conversation_id,
        )
    )
    if existing is not None:
        record = db.scalar(
            select(CallRecord).where(
                CallRecord.prospecting_inbound_callback_id == existing.id,
            )
        )
        if record is None:
            raise RealtimeSellerAgentError("The existing ElevenLabs call is missing its record.")
        return RegisteredElevenLabsCall(
            conversation_id=clean_conversation_id,
            callback_id=existing.id,
            call_record_id=record.id,
            created=False,
        )

    started_at = received_at or datetime.now(UTC)
    callback = ProspectingInboundCallback(
        organization_id=line.organization_id,
        voice_line_id=line.id,
        provider=PROVIDER,
        provider_call_id=clean_conversation_id,
        normalized_caller=normalized_caller,
        caller_number=normalized_caller,
        matched_prospect_id=None,
        matched_attempt_id=None,
        match_status="pending",
        match_strategy="awaiting_caller_verification",
        match_confidence_basis_points=None,
        candidate_count=0,
        assigned_user_id=line.assigned_user_id,
        fallback_user_id=line.fallback_user_id,
        status="routing",
        received_at=started_at,
        answered_at=None,
        completed_at=None,
        routing_metadata={
            "source": SOURCE,
            "agent_name": AGENT_NAME,
            "agent_id": clean_agent_id,
            "model": "ElevenLabs Agent",
            "voice": "ElevenLabs",
            "call_sid": call_sid,
            "tool_call_ids": [],
        },
    )
    db.add(callback)
    db.flush()
    record = CallRecord(
        organization_id=line.organization_id,
        conversation_id=None,
        lead_id=None,
        contact_id=None,
        prospect_id=None,
        prospecting_attempt_id=None,
        prospecting_dial_leg_id=None,
        prospecting_inbound_callback_id=callback.id,
        actor_user_id=line.assigned_user_id,
        communication_record_id=None,
        voice_line_id=line.id,
        call_intent_id=None,
        provider=PROVIDER,
        provider_call_id=clean_conversation_id,
        child_provider_call_id=call_sid,
        direction="inbound",
        status="ringing",
        from_number=normalized_caller,
        to_number=normalized_called,
        started_at=started_at,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status="not_requested",
        call_metadata={
            "source": SOURCE,
            "agent_name": AGENT_NAME,
            "agent_id": clean_agent_id,
        },
    )
    db.add(record)
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="prospecting_inbound_callback",
            entity_id=callback.id,
            event_type="voice.ai_seller_callback_received",
            summary=f"{AGENT_NAME} received a possible seller callback.",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ProspectingInboundCallback).where(
                ProspectingInboundCallback.organization_id == line.organization_id,
                ProspectingInboundCallback.provider == PROVIDER,
                ProspectingInboundCallback.provider_call_id == clean_conversation_id,
            )
        )
        if existing is None:
            raise
        existing_record = db.scalar(
            select(CallRecord).where(
                CallRecord.prospecting_inbound_callback_id == existing.id,
            )
        )
        if existing_record is None:
            raise RealtimeSellerAgentError(
                "The duplicate ElevenLabs call is missing its record."
            ) from None
        return RegisteredElevenLabsCall(
            conversation_id=clean_conversation_id,
            callback_id=existing.id,
            call_record_id=existing_record.id,
            created=False,
        )
    return RegisteredElevenLabsCall(
        conversation_id=clean_conversation_id,
        callback_id=callback.id,
        call_record_id=record.id,
        created=True,
    )


def execute_elevenlabs_tool(
    db: Session,
    *,
    tool_name: str,
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    conversation_id = _text(payload.get("conversation_id"))
    caller_number = _text(payload.get("caller_id") or payload.get("caller_number"))
    called_number = _text(payload.get("called_number"))
    call_sid = _text(payload.get("call_sid"))
    agent_id = _text(payload.get("agent_id")) or active_settings.elevenlabs_agent_id
    if not conversation_id or not agent_id:
        raise RealtimeSellerAgentError("The ElevenLabs tool request is missing call context.")
    if (
        active_settings.elevenlabs_agent_id
        and agent_id != active_settings.elevenlabs_agent_id
    ):
        raise RealtimeSellerAgentError("The tool request belongs to a different ElevenLabs agent.")
    callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == conversation_id,
        )
    )
    if callback is None:
        if not caller_number or not called_number:
            raise RealtimeSellerAgentError("The ElevenLabs call has not been registered yet.")
        register_elevenlabs_call(
            db,
            conversation_id=conversation_id,
            caller_number=caller_number,
            called_number=called_number,
            call_sid=call_sid,
            agent_id=agent_id,
            settings=active_settings,
        )
    arguments = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "conversation_id",
            "caller_id",
            "caller_number",
            "called_number",
            "call_sid",
            "agent_id",
            "tool_call_id",
        }
    }
    tool_call_id = _text(payload.get("tool_call_id")) or _tool_fingerprint(
        conversation_id,
        tool_name,
        arguments,
    )
    return execute_seller_agent_tool(
        db,
        call_id=conversation_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        provider=PROVIDER,
    )


def process_elevenlabs_transcription(
    db: Session,
    event: dict[str, Any],
    settings: Settings | None = None,
) -> RegisteredElevenLabsCall:
    active_settings = settings or get_settings()
    data = event.get("data")
    if not isinstance(data, dict):
        raise RealtimeSellerAgentError("ElevenLabs transcription data is missing.")
    conversation_id = _text(data.get("conversation_id"))
    agent_id = _text(data.get("agent_id"))
    if not conversation_id or not agent_id:
        raise RealtimeSellerAgentError("ElevenLabs transcription is missing call identifiers.")
    raw_metadata = data.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    existing_callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == conversation_id,
        )
    )
    existing_record = (
        db.scalar(
            select(CallRecord).where(
                CallRecord.prospecting_inbound_callback_id == existing_callback.id,
            )
        )
        if existing_callback is not None
        else None
    )
    if existing_callback is not None and existing_record is not None:
        caller_number = existing_callback.caller_number
        called_number = existing_record.to_number
        call_sid = existing_record.child_provider_call_id
    else:
        caller_number, called_number, call_sid = _phone_context(data, metadata)
    started_at = _unix_datetime(metadata.get("start_time_unix_secs"))
    registered = register_elevenlabs_call(
        db,
        conversation_id=conversation_id,
        caller_number=caller_number,
        called_number=called_number,
        call_sid=call_sid,
        agent_id=agent_id,
        settings=active_settings,
        received_at=started_at,
    )
    callback = db.get(ProspectingInboundCallback, registered.callback_id)
    record = db.get(CallRecord, registered.call_record_id)
    if callback is None or record is None:
        raise RealtimeSellerAgentError("The ElevenLabs call could not be loaded.")

    transcript = _transcript(data.get("transcript"))
    raw_analysis = data.get("analysis")
    analysis: dict[str, Any] = raw_analysis if isinstance(raw_analysis, dict) else {}
    duration = _nonnegative_int(metadata.get("call_duration_secs"))
    completed_at = (
        started_at + timedelta(seconds=duration)
        if started_at is not None and duration is not None
        else datetime.now(UTC)
    )
    provider_status = _text(data.get("status")) or "done"
    provider_error = metadata.get("error")
    error_text = (
        _text(provider_error.get("reason"))
        if isinstance(provider_error, dict)
        else _text(provider_error)
    )
    failed = provider_status in {"failed", "error"} or bool(error_text)
    existing_metadata = dict(callback.routing_metadata or {})
    outcome = _outcome(existing_metadata, transcript, data, analysis)
    summary = _text(analysis.get("transcript_summary")) or existing_metadata.get("summary")
    provider_agent_name = _text(data.get("agent_name"))
    agent_name = AGENT_NAME
    diagnostics = _diagnostics(transcript, data, metadata)
    callback.status = "failed" if failed else "completed"
    callback.received_at = started_at or callback.received_at
    callback.answered_at = callback.answered_at or started_at or callback.received_at
    callback.completed_at = completed_at
    callback.routing_metadata = {
        **existing_metadata,
        "source": SOURCE,
        "agent_name": agent_name,
        "provider_agent_name": provider_agent_name,
        "agent_id": agent_id,
        "version_id": _text(data.get("version_id")),
        "environment": _text(data.get("environment")),
        "prompt_version": _text(data.get("version_id")),
        "outcome": "agent_failed" if failed else outcome,
        "summary": summary,
        "transcript": transcript,
        "transcript_complete": True,
        "call_diagnostics": diagnostics,
        "elevenlabs_analysis": analysis,
        "termination_reason": _text(metadata.get("termination_reason")),
        "has_audio": bool(data.get("has_audio")),
        "has_user_audio": bool(data.get("has_user_audio")),
        "has_response_audio": bool(data.get("has_response_audio")),
        "ended_at": completed_at.isoformat(),
        **({"error": error_text} if error_text else {}),
    }
    record.status = "failed" if failed else "completed"
    record.started_at = started_at or record.started_at
    record.answered_at = record.answered_at or started_at or record.started_at
    record.ended_at = completed_at
    record.duration_seconds = duration
    record.disposition = "agent_failed" if failed else outcome
    record.child_provider_call_id = call_sid or record.child_provider_call_id
    record.call_metadata = {
        **(record.call_metadata or {}),
        "source": SOURCE,
        "agent_name": agent_name,
        "agent_id": agent_id,
        "outcome": record.disposition,
        "summary": summary,
        "transcript": transcript,
        "transcript_complete": True,
        "call_diagnostics": diagnostics,
        "termination_reason": _text(metadata.get("termination_reason")),
        **({"error": error_text} if error_text else {}),
    }
    if duration is None:
        _set_call_duration(record, completed_at)
    communication = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == callback.organization_id,
            CommunicationRecord.provider == PROVIDER,
            CommunicationRecord.provider_message_id == conversation_id,
        )
    )
    if communication is not None:
        communication.status = "failed" if failed else "received"
        communication.body = _communication_body(
            callback.routing_metadata,
            transcript,
            record.disposition,
        )
        communication.communication_metadata = {
            **(communication.communication_metadata or {}),
            "outcome": record.disposition,
            "summary": summary,
            "transcript": transcript,
            "transcript_complete": True,
            "call_diagnostics": diagnostics,
        }
    _record_provider_event(db, callback, event)
    if existing_metadata.get("elevenlabs_post_call_received_at") is None:
        callback.routing_metadata = {
            **callback.routing_metadata,
            "elevenlabs_post_call_received_at": datetime.now(UTC).isoformat(),
        }
        db.add(
            ActivityEvent(
                organization_id=callback.organization_id,
                actor_user_id=None,
                entity_type="prospecting_inbound_callback",
                entity_id=callback.id,
                event_type=(
                    "voice.ai_seller_callback_failed"
                    if failed
                    else "voice.ai_seller_callback_completed"
                ),
                summary=(
                    f"{agent_name}'s seller callback failed and was saved for review."
                    if failed
                    else f"{agent_name} completed a seller callback: "
                    f"{outcome.replace('_', ' ')}."
                ),
            )
        )
    db.commit()
    return registered


def record_elevenlabs_audio_notice(db: Session, event: dict[str, Any]) -> None:
    """Record delivery without duplicating a large base64 MP3 in Stonegate's database."""

    data = event.get("data")
    if not isinstance(data, dict):
        return
    conversation_id = _text(data.get("conversation_id"))
    if not conversation_id:
        return
    callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == conversation_id,
        )
    )
    if callback is None:
        return
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "elevenlabs_audio_webhook_received": True,
    }
    _record_provider_event(db, callback, event, include_payload=False)
    db.commit()


def process_elevenlabs_failure(
    db: Session,
    event: dict[str, Any],
    settings: Settings | None = None,
) -> RegisteredElevenLabsCall:
    active_settings = settings or get_settings()
    data = event.get("data")
    if not isinstance(data, dict):
        raise RealtimeSellerAgentError("ElevenLabs failure data is missing.")
    conversation_id = _text(data.get("conversation_id"))
    agent_id = _text(data.get("agent_id"))
    if not conversation_id or not agent_id:
        raise RealtimeSellerAgentError("ElevenLabs failure is missing call identifiers.")
    if (
        active_settings.elevenlabs_agent_id
        and agent_id != active_settings.elevenlabs_agent_id
    ):
        raise RealtimeSellerAgentError("The failure belongs to a different ElevenLabs agent.")
    callback = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == conversation_id,
        )
    )
    if callback is None:
        raw_metadata = data.get("metadata")
        failure_metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        body = failure_metadata.get("body")
        body = body if isinstance(body, dict) else {}
        caller = _text(body.get("From") or body.get("from_number"))
        called = _text(body.get("To") or body.get("to_number"))
        call_sid = _text(body.get("CallSid") or body.get("call_sid"))
        if not caller or not called:
            raise RealtimeSellerAgentError("ElevenLabs failure is missing inbound phone context.")
        registered = register_elevenlabs_call(
            db,
            conversation_id=conversation_id,
            caller_number=caller,
            called_number=called,
            call_sid=call_sid,
            agent_id=agent_id,
            settings=active_settings,
            received_at=_unix_datetime(event.get("event_timestamp")),
        )
        callback = db.get(ProspectingInboundCallback, registered.callback_id)
    else:
        record = db.scalar(
            select(CallRecord).where(
                CallRecord.prospecting_inbound_callback_id == callback.id,
            )
        )
        if record is None:
            raise RealtimeSellerAgentError("The ElevenLabs failure is missing its call record.")
        registered = RegisteredElevenLabsCall(
            conversation_id=conversation_id,
            callback_id=callback.id,
            call_record_id=record.id,
            created=False,
        )
    if callback is None:
        raise RealtimeSellerAgentError("The ElevenLabs failure could not be loaded.")
    record = db.get(CallRecord, registered.call_record_id)
    if record is None:
        raise RealtimeSellerAgentError("The ElevenLabs failure call record could not be loaded.")
    now = _unix_datetime(event.get("event_timestamp")) or datetime.now(UTC)
    reason = _text(data.get("failure_reason")) or "unknown"
    existing_metadata = dict(callback.routing_metadata or {})
    callback.status = "failed"
    callback.completed_at = now
    callback.routing_metadata = {
        **existing_metadata,
        "outcome": "agent_failed",
        "error": f"ElevenLabs call initiation failed: {reason}",
        "failure_reason": reason,
        "ended_at": now.isoformat(),
    }
    record.status = "failed"
    record.ended_at = now
    record.disposition = "agent_failed"
    record.call_metadata = {
        **(record.call_metadata or {}),
        "outcome": "agent_failed",
        "error": f"ElevenLabs call initiation failed: {reason}",
        "failure_reason": reason,
    }
    _set_call_duration(record, now)
    _record_provider_event(db, callback, event)
    if existing_metadata.get("elevenlabs_failure_received_at") is None:
        callback.routing_metadata = {
            **callback.routing_metadata,
            "elevenlabs_failure_received_at": datetime.now(UTC).isoformat(),
        }
        db.add(
            ActivityEvent(
                organization_id=callback.organization_id,
                actor_user_id=None,
                entity_type="prospecting_inbound_callback",
                entity_id=callback.id,
                event_type="voice.ai_seller_callback_failed",
                summary=f"{AGENT_NAME}'s call could not start: {reason}.",
            )
        )
    db.commit()
    return registered


def _record_provider_event(
    db: Session,
    callback: ProspectingInboundCallback,
    event: dict[str, Any],
    *,
    include_payload: bool = True,
) -> None:
    event_type = _text(event.get("type")) or "unknown"
    external_event_id = f"{event_type}:{callback.provider_call_id}"
    existing = db.scalar(
        select(CommunicationProviderEvent).where(
            CommunicationProviderEvent.organization_id == callback.organization_id,
            CommunicationProviderEvent.provider == PROVIDER,
            CommunicationProviderEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return
    payload = event if include_payload else {
        "type": event_type,
        "conversation_id": callback.provider_call_id,
        "audio_omitted": True,
    }
    now = datetime.now(UTC)
    db.add(
        CommunicationProviderEvent(
            organization_id=callback.organization_id,
            conversation_id=None,
            provider=PROVIDER,
            event_type=event_type,
            external_event_id=external_event_id,
            processing_status="processed",
            payload=payload,
            received_at=now,
            processed_at=now,
            next_attempt_at=None,
            processing_started_at=None,
            processing_token=None,
            error_message=None,
        )
    )


def _phone_context(
    data: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[str, str, str | None]:
    phone_call = metadata.get("phone_call")
    phone_call = phone_call if isinstance(phone_call, dict) else {}
    direction = _text(phone_call.get("direction")) or "inbound"
    if direction != "inbound":
        raise RealtimeSellerAgentError("Only inbound ElevenLabs calls belong in this workspace.")
    caller = _text(phone_call.get("external_number"))
    called = _text(phone_call.get("agent_number"))
    call_sid = _text(phone_call.get("call_sid"))
    initiation = data.get("conversation_initiation_client_data")
    initiation = initiation if isinstance(initiation, dict) else {}
    dynamic = initiation.get("dynamic_variables")
    dynamic = dynamic if isinstance(dynamic, dict) else {}
    caller = caller or _text(dynamic.get("stonegate_caller_number"))
    called = called or _text(dynamic.get("stonegate_called_number"))
    call_sid = call_sid or _text(dynamic.get("stonegate_call_sid"))
    if not caller or not called:
        raise RealtimeSellerAgentError("ElevenLabs transcription is missing inbound phone context.")
    return caller, called, call_sid


def _transcript(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    character_count = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = _text(item.get("role"))
        message = _text(item.get("message"))
        if role not in {"agent", "user"} or not message:
            continue
        remaining = MAX_TRANSCRIPT_CHARS - character_count
        if remaining <= 0:
            break
        text = message[:remaining]
        result.append({"speaker": "marin" if role == "agent" else "caller", "text": text})
        character_count += len(text)
    return result


def _diagnostics(
    transcript: list[dict[str, str]],
    data: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    caller_turns = sum(turn.get("speaker") == "caller" for turn in transcript)
    agent_turns = sum(turn.get("speaker") == "marin" for turn in transcript)
    has_user_audio = bool(data.get("has_user_audio"))
    return {
        "caller_speech_started_count": caller_turns or (1 if has_user_audio else 0),
        "caller_transcript_count": caller_turns,
        "transcription_failed_count": 1 if has_user_audio and not caller_turns else 0,
        "discarded_transcription_count": 0,
        "output_audio_started_count": agent_turns,
        "output_audio_stopped_count": agent_turns,
        "monitor_close_type": _text(metadata.get("termination_reason")),
        "monitor_close_code": None,
    }


def _outcome(
    existing_metadata: dict[str, Any],
    transcript: list[dict[str, str]],
    data: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    existing = _text(existing_metadata.get("outcome"))
    if existing in FINAL_OUTCOMES:
        return existing
    collected = analysis.get("data_collection_results")
    collected = collected if isinstance(collected, dict) else {}
    for key in ("call_outcome", "outcome", "disposition"):
        value = _collection_value(collected.get(key))
        if value in FINAL_OUTCOMES:
            return value
    raw_transcript = data.get("transcript")
    if isinstance(raw_transcript, list):
        for item in raw_transcript:
            if not isinstance(item, dict):
                continue
            calls = item.get("tool_calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if isinstance(call, dict) and _text(call.get("tool_name") or call.get("name")) in {
                    "transfer_to_number",
                    "transfer_to_acquisitions",
                }:
                    return "transferred"
    if not any(turn.get("speaker") == "caller" for turn in transcript):
        return "incomplete"
    return "incomplete"


def _collection_value(raw: Any) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("value")
    return _text(raw)


def _tool_fingerprint(conversation_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{conversation_id}:{tool_name}:{canonical}".encode()).hexdigest()
    return f"elevenlabs:{digest}"


def _unix_datetime(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or value < 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return round(value)
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
