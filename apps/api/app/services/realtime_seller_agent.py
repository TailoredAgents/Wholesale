from __future__ import annotations

# ruff: noqa: E501
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import aiohttp
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.integrations.openai_realtime import (
    OpenAIRealtimeCallClient,
    OpenAIRealtimeError,
    encode_realtime_event,
)
from app.models.foundation import (
    ActivityEvent,
    CallRecord,
    CommunicationProviderEvent,
    CommunicationRecord,
    ConsentRecord,
    Contact,
    ContactMethod,
    Lead,
    Property,
    Prospect,
    ProspectContactPoint,
    ProspectingInboundCallback,
    SuppressionRecord,
    Task,
    VoiceLine,
)
from app.services.acquisition_operations import create_notification
from app.services.communication_compliance import format_e164, phone_lookup_values
from app.services.inbox import ensure_primary_conversation, update_conversation_activity
from app.services.property_identity import refresh_property_identity_keys
from app.services.staff_lead_alerts import queue_staff_lead_alerts_for_lead
from app.services.tasks import supersede_open_primary_tasks

PROVIDER = "openai_realtime"
AGENT_NAME = "Marin"
PROMPT_VERSION = "stonegate-seller-callback-v1"
MAX_TRANSCRIPT_CHARS = 40_000
FINAL_OUTCOMES = {
    "interested",
    "callback_scheduled",
    "transferred",
    "not_interested",
    "wrong_number",
    "unrelated",
    "do_not_contact",
}
logger = structlog.get_logger()
_active_call_tasks: dict[str, asyncio.Task[None]] = {}


class RealtimeSellerAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegisteredRealtimeCall:
    call_id: str
    callback_id: UUID
    call_record_id: UUID
    line_id: UUID
    caller_number: str
    called_number: str
    created: bool
    accepted: bool
    terminal: bool


def realtime_agent_instructions() -> str:
    return """# Identity
You are Marin, the phone concierge for Stonegate Home Buyers, a real-estate investment company.

# Primary situation
Most callers are possible property owners returning a missed cold call from a Stonegate VA. The caller may not know why Stonegate called. Never imply that they do. Some calls may be unrelated.

# Opening
Begin every call exactly: "Thank you for calling Stonegate Home Buyers. This is Marin. How can I help you?"
If they say they are returning a call, say: "Absolutely. Let me pull that up for you. May I ask your name?"

# Style
- Sound warm, calm, natural, and concise. Use contractions.
- Speak in one or two short sentences, then listen.
- Ask one question at a time. Do not interrogate or read a script.
- Allow interruptions and brief silence. Use wait_for_user when the caller asks for a moment.
- Do not say you are human. If directly asked whether you are AI, answer honestly that you are Stonegate's virtual phone assistant.
- Never pressure a caller, invent facts, promise an offer, or give legal, tax, or financial advice.

# Privacy and identity
- Do not reveal a stored name, property address, ownership fact, or other CRM detail until the caller supplies identifying information and lookup_callback_context confirms it.
- A phone-number match alone is not identity verification.
- If verification fails, politely collect information as a new possible seller without revealing stored data.

# Seller conversation
When the call concerns a possible property sale, naturally learn: caller name, property address, whether they own it, house or vacant land, whether they are open to selling, occupancy, condition, desired timing, motivation, asking price if they have one, and best next step.
Do not demand every optional fact. Save useful verified facts during the conversation with save_seller_details. A lead may be created only when the caller confirms ownership and genuine interest in discussing a sale.

# Follow-up and transfers
- Create a callback only when the caller agrees to a specific future date and time. Confirm the time aloud first.
- Transfer only when the caller asks for a person or agrees to speak with Acquisitions. Confirm before using transfer_to_acquisitions.
- If a caller says not to call again, confirm the request once and then use record_call_outcome with do_not_contact.
- A simple "not interested" is not automatically a do-not-contact request.

# Closing
Before ending, briefly confirm the next step. Record one accurate outcome. Thank the caller. Do not manufacture a follow-up.
"""


def realtime_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "lookup_callback_context",
            "description": (
                "Privately match the caller after they state their own name or property address. "
                "Never use the result to reveal facts that the caller did not first verify."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_name": {"type": "string"},
                    "property_address": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "save_seller_details",
            "description": (
                "Save caller-supplied seller and property facts. Creates or updates a lead only "
                "when owner_confirmed and seller_interested are both true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "seller_name": {"type": "string"},
                    "street_address": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": "string"},
                    "postal_code": {"type": "string"},
                    "property_type": {"type": "string"},
                    "owner_confirmed": {"type": "boolean"},
                    "seller_interested": {"type": "boolean"},
                    "occupancy_status": {"type": "string"},
                    "property_condition": {"type": "string"},
                    "desired_timeline": {"type": "string"},
                    "motivation": {"type": "string"},
                    "asking_price": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": [
                    "seller_name",
                    "street_address",
                    "city",
                    "state",
                    "owner_confirmed",
                    "seller_interested",
                ],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "schedule_human_callback",
            "description": (
                "Schedule exactly one human callback after the caller agrees to a specific time. "
                "Use an ISO 8601 timestamp with an offset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "callback_at": {"type": "string"},
                    "reason": {"type": "string"},
                    "caller_confirmed": {"type": "boolean"},
                },
                "required": ["callback_at", "reason", "caller_confirmed"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "transfer_to_acquisitions",
            "description": (
                "Transfer to Stonegate's configured human Acquisitions line only after the caller "
                "requests or clearly agrees to the transfer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "caller_confirmed": {"type": "boolean"},
                },
                "required": ["reason", "caller_confirmed"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "record_call_outcome",
            "description": (
                "Record the current call outcome. Use do_not_contact only for an explicit, "
                "confirmed request to stop future contact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "outcome": {
                        "type": "string",
                        "enum": sorted(FINAL_OUTCOMES),
                    },
                    "notes": {"type": "string"},
                    "do_not_contact_confirmed": {"type": "boolean"},
                },
                "required": ["outcome", "notes", "do_not_contact_confirmed"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "wait_for_user",
            "description": "Wait silently when the caller asks for a moment or there is benign silence.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "finish_call",
            "description": "Save the concise final summary before politely ending the call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "outcome": {"type": "string", "enum": sorted(FINAL_OUTCOMES)},
                },
                "required": ["summary", "outcome"],
                "additionalProperties": False,
            },
        },
    ]


def realtime_session_configuration(settings: Settings) -> dict[str, Any]:
    return {
        "type": "realtime",
        "model": settings.openai_realtime_model,
        "output_modalities": ["audio"],
        "instructions": realtime_agent_instructions(),
        "reasoning": {"effort": "low"},
        "audio": {
            "input": {
                "transcription": {"model": "gpt-4o-mini-transcribe", "language": "en"},
                "noise_reduction": {"type": "far_field"},
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": "auto",
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output": {"voice": settings.openai_realtime_voice, "speed": 1.0},
        },
        "tools": realtime_tools(),
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "max_output_tokens": 300,
        "truncation": "auto",
    }


def sip_phone_number(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:sip:|tel:)?(\+?\d{10,15})", value, flags=re.IGNORECASE)
    return format_e164(match.group(1)) if match else None


def sip_header(payload: dict[str, Any], name: str) -> str | None:
    headers = payload.get("data", {}).get("sip_headers", [])
    if not isinstance(headers, list):
        return None
    for item in headers:
        value = item.get("value") if isinstance(item, dict) else None
        if (
            isinstance(item, dict)
            and str(item.get("name", "")).lower() == name.lower()
            and isinstance(value, str)
        ):
            return value
    return None


def register_realtime_call(
    db: Session,
    *,
    event: dict[str, Any],
    webhook_id: str,
    settings: Settings | None = None,
) -> RegisteredRealtimeCall:
    active_settings = settings or get_settings()
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("call_id"), str):
        raise RealtimeSellerAgentError("OpenAI incoming call did not include a call ID.")
    call_id = data["call_id"].strip()
    caller_number = sip_phone_number(sip_header(event, "From"))
    called_number = sip_phone_number(sip_header(event, "To"))
    expected_number = format_e164(active_settings.openai_realtime_line_number)
    if not call_id or caller_number is None or called_number is None:
        raise RealtimeSellerAgentError("OpenAI incoming call had invalid SIP addressing.")
    if called_number != expected_number:
        raise RealtimeSellerAgentError("Incoming SIP call was not addressed to the Marin line.")
    line = db.scalar(
        select(VoiceLine).where(
            VoiceLine.phone_number == called_number,
            VoiceLine.department_key == "acquisitions",
            VoiceLine.purpose_key == "seller_callback_ai",
            VoiceLine.status == "active",
        )
    )
    if line is None:
        raise RealtimeSellerAgentError("The Marin seller-callback line is not active in Stonegate.")
    existing = db.scalar(
        select(ProspectingInboundCallback).where(
            ProspectingInboundCallback.organization_id == line.organization_id,
            ProspectingInboundCallback.provider == PROVIDER,
            ProspectingInboundCallback.provider_call_id == call_id,
        )
    )
    if existing is not None:
        call_record = db.scalar(
            select(CallRecord).where(
                CallRecord.prospecting_inbound_callback_id == existing.id,
            )
        )
        if call_record is None:
            raise RealtimeSellerAgentError("Existing callback is missing its call record.")
        return RegisteredRealtimeCall(
            call_id=call_id,
            callback_id=existing.id,
            call_record_id=call_record.id,
            line_id=line.id,
            caller_number=caller_number,
            called_number=called_number,
            created=False,
            accepted=bool((existing.routing_metadata or {}).get("accepted_at")),
            terminal=existing.status in {"completed", "failed", "canceled"},
        )

    now = datetime.now(UTC)
    callback = ProspectingInboundCallback(
        organization_id=line.organization_id,
        voice_line_id=line.id,
        provider=PROVIDER,
        provider_call_id=call_id,
        normalized_caller=caller_number,
        caller_number=caller_number,
        matched_prospect_id=None,
        matched_attempt_id=None,
        match_status="pending",
        match_strategy="awaiting_caller_verification",
        match_confidence_basis_points=None,
        candidate_count=0,
        assigned_user_id=line.assigned_user_id,
        fallback_user_id=line.fallback_user_id,
        status="routing",
        received_at=now,
        answered_at=None,
        completed_at=None,
        routing_metadata={
            "source": "openai_realtime_sip",
            "agent_name": AGENT_NAME,
            "model": active_settings.openai_realtime_model,
            "voice": active_settings.openai_realtime_voice,
            "prompt_version": PROMPT_VERSION,
            "webhook_id": webhook_id,
            "sip_call_id": sip_header(event, "Call-ID"),
            "tool_call_ids": [],
        },
    )
    db.add(callback)
    db.flush()
    call_record = CallRecord(
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
        provider_call_id=call_id,
        child_provider_call_id=None,
        direction="inbound",
        status="ringing",
        from_number=caller_number,
        to_number=called_number,
        started_at=now,
        answered_at=None,
        ended_at=None,
        duration_seconds=None,
        disposition=None,
        recording_consent_status="not_requested",
        call_metadata={
            "source": "openai_realtime_sip",
            "agent_name": AGENT_NAME,
            "prompt_version": PROMPT_VERSION,
        },
    )
    db.add(call_record)
    db.add(
        ActivityEvent(
            organization_id=line.organization_id,
            actor_user_id=None,
            entity_type="prospecting_inbound_callback",
            entity_id=callback.id,
            event_type="voice.ai_seller_callback_received",
            summary="Marin received a possible seller callback.",
        )
    )
    db.add(
        CommunicationProviderEvent(
            organization_id=line.organization_id,
            conversation_id=None,
            provider=PROVIDER,
            event_type="realtime.call.incoming",
            external_event_id=webhook_id or f"realtime.call.incoming:{call_id}",
            processing_status="processed",
            payload={"call_id": call_id, "callback_id": str(callback.id)},
            received_at=now,
            processed_at=now,
            next_attempt_at=None,
            processing_started_at=None,
            processing_token=None,
            error_message=None,
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
                ProspectingInboundCallback.provider_call_id == call_id,
            )
        )
        if existing is None:
            raise
        existing_call = db.scalar(
            select(CallRecord).where(CallRecord.prospecting_inbound_callback_id == existing.id)
        )
        if existing_call is None:
            raise RealtimeSellerAgentError(
                "Duplicate callback is missing its call record."
            ) from None
        return RegisteredRealtimeCall(
            call_id=call_id,
            callback_id=existing.id,
            call_record_id=existing_call.id,
            line_id=line.id,
            caller_number=caller_number,
            called_number=called_number,
            created=False,
            accepted=bool((existing.routing_metadata or {}).get("accepted_at")),
            terminal=existing.status in {"completed", "failed", "canceled"},
        )
    return RegisteredRealtimeCall(
        call_id=call_id,
        callback_id=callback.id,
        call_record_id=call_record.id,
        line_id=line.id,
        caller_number=caller_number,
        called_number=called_number,
        created=True,
        accepted=False,
        terminal=False,
    )


def mark_realtime_call_accepted(db: Session, call: RegisteredRealtimeCall) -> None:
    now = datetime.now(UTC)
    callback = db.get(ProspectingInboundCallback, call.callback_id)
    record = db.get(CallRecord, call.call_record_id)
    if callback is None or record is None:
        return
    callback.status = "answered"
    callback.answered_at = callback.answered_at or now
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "accepted_at": now.isoformat(),
    }
    record.status = "in-progress"
    record.answered_at = record.answered_at or now
    db.commit()


def mark_realtime_call_failed(
    db: Session,
    call: RegisteredRealtimeCall,
    *,
    error: str,
) -> None:
    now = datetime.now(UTC)
    callback = db.get(ProspectingInboundCallback, call.callback_id)
    record = db.get(CallRecord, call.call_record_id)
    if callback is not None:
        callback.status = "failed"
        callback.completed_at = now
        callback.routing_metadata = {
            **(callback.routing_metadata or {}),
            "error": error[:1000],
        }
    if record is not None:
        record.status = "failed"
        record.ended_at = now
        record.disposition = "agent_failed"
        record.call_metadata = {
            **(record.call_metadata or {}),
            "error": error[:1000],
        }
    db.commit()


def start_realtime_call_monitor(call: RegisteredRealtimeCall) -> None:
    existing = _active_call_tasks.get(call.call_id)
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(_monitor_realtime_call(call), name=f"marin:{call.call_id}")
    _active_call_tasks[call.call_id] = task

    def cleanup(completed: asyncio.Task[None]) -> None:
        _active_call_tasks.pop(call.call_id, None)
        if completed.cancelled():
            return
        error = completed.exception()
        if error is not None:
            logger.error(
                "realtime_seller_agent_task_failed", call_id=call.call_id, error=str(error)
            )

    task.add_done_callback(cleanup)


async def _monitor_realtime_call(call: RegisteredRealtimeCall) -> None:
    settings = get_settings()
    client = OpenAIRealtimeCallClient(settings)
    transcript: list[dict[str, str]] = []
    finish_after_response = False
    try:
        async with client.monitor(call.call_id) as websocket:
            await websocket.send_str(encode_realtime_event({"type": "response.create"}))
            async with asyncio.timeout(settings.openai_realtime_max_call_seconds):
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        payload = json.loads(message.data)
                        event_type = str(payload.get("type", ""))
                        _capture_transcript_event(transcript, payload)
                        if event_type == "response.done":
                            function_calls = _function_calls(payload)
                            if function_calls:
                                for tool_call in function_calls:
                                    result = await _run_tool(call, tool_call, client)
                                    await websocket.send_str(
                                        encode_realtime_event(
                                            {
                                                "type": "conversation.item.create",
                                                "item": {
                                                    "type": "function_call_output",
                                                    "call_id": tool_call["call_id"],
                                                    "output": json.dumps(result, ensure_ascii=True),
                                                },
                                            }
                                        )
                                    )
                                    if tool_call["name"] == "wait_for_user":
                                        continue
                                    if tool_call[
                                        "name"
                                    ] == "transfer_to_acquisitions" and result.get("transferred"):
                                        _finish_realtime_call(
                                            call,
                                            transcript,
                                            forced_outcome="transferred",
                                        )
                                        return
                                    if tool_call["name"] == "finish_call" and result.get("saved"):
                                        finish_after_response = True
                                if not all(
                                    item["name"] == "wait_for_user" for item in function_calls
                                ):
                                    await websocket.send_str(
                                        encode_realtime_event({"type": "response.create"})
                                    )
                            elif finish_after_response:
                                await asyncio.sleep(0.75)
                                await client.hangup(call.call_id)
                                _finish_realtime_call(call, transcript)
                                return
                        elif event_type == "error":
                            logger.warning(
                                "realtime_seller_agent_event_error",
                                call_id=call.call_id,
                                detail=payload.get("error"),
                            )
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        break
    except TimeoutError:
        await _safe_hangup(client, call.call_id)
        _finish_realtime_call(call, transcript, forced_outcome="timed_out")
        return
    except Exception as exc:
        logger.exception("realtime_seller_agent_monitor_failed", call_id=call.call_id)
        await _safe_transfer(client, call.call_id, settings.openai_realtime_transfer_number)
        with SessionLocal() as db:
            mark_realtime_call_failed(db, call, error=str(exc))
        return
    _finish_realtime_call(call, transcript)


def _capture_transcript_event(transcript: list[dict[str, str]], payload: dict[str, Any]) -> None:
    event_type = str(payload.get("type", ""))
    if event_type == "conversation.item.input_audio_transcription.completed":
        text = _clean(payload.get("transcript"), 4000)
        if text:
            transcript.append({"speaker": "caller", "text": text})
    elif event_type in {"response.output_audio_transcript.done", "response.audio_transcript.done"}:
        text = _clean(payload.get("transcript"), 4000)
        if text:
            transcript.append({"speaker": AGENT_NAME.lower(), "text": text})
    while sum(len(item["text"]) for item in transcript) > MAX_TRANSCRIPT_CHARS:
        transcript.pop(0)


def _function_calls(payload: dict[str, Any]) -> list[dict[str, str]]:
    response = payload.get("response")
    output = response.get("output", []) if isinstance(response, dict) else []
    calls: list[dict[str, str]] = []
    if not isinstance(output, list):
        return calls
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        if not all(isinstance(item.get(key), str) for key in ("name", "call_id", "arguments")):
            continue
        calls.append(
            {
                "name": item["name"],
                "call_id": item["call_id"],
                "arguments": item["arguments"],
            }
        )
    return calls


async def _run_tool(
    call: RegisteredRealtimeCall,
    tool_call: dict[str, str],
    client: OpenAIRealtimeCallClient,
) -> dict[str, Any]:
    try:
        arguments = json.loads(tool_call["arguments"] or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error": "The tool arguments were invalid. Ask the caller again."}
    if tool_call["name"] == "transfer_to_acquisitions":
        result = await asyncio.to_thread(
            execute_realtime_tool,
            call.call_id,
            tool_call["call_id"],
            tool_call["name"],
            arguments,
        )
        if result.get("should_transfer"):
            settings = get_settings()
            await client.refer(call.call_id, settings.openai_realtime_transfer_number)
            await asyncio.to_thread(mark_call_transferred, call.call_id)
            result["transferred"] = True
        return result
    return await asyncio.to_thread(
        execute_realtime_tool,
        call.call_id,
        tool_call["call_id"],
        tool_call["name"],
        arguments,
    )


def execute_realtime_tool(
    call_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    with SessionLocal() as db:
        callback = db.scalar(
            select(ProspectingInboundCallback).where(
                ProspectingInboundCallback.provider == PROVIDER,
                ProspectingInboundCallback.provider_call_id == call_id,
            )
        )
        if callback is None:
            return {"ok": False, "error": "The current call record is unavailable."}
        metadata = dict(callback.routing_metadata or {})
        tool_ids = list(metadata.get("tool_call_ids") or [])
        prior_results = dict(metadata.get("tool_results") or {})
        if tool_call_id in tool_ids:
            if tool_name == "transfer_to_acquisitions" and metadata.get("transferred_at"):
                return {
                    "ok": True,
                    "should_transfer": False,
                    "transferred": True,
                    "duplicate": True,
                }
            prior = prior_results.get(tool_call_id)
            return prior if isinstance(prior, dict) else {"ok": True, "duplicate": True}
        handlers = {
            "lookup_callback_context": _tool_lookup_callback_context,
            "save_seller_details": _tool_save_seller_details,
            "schedule_human_callback": _tool_schedule_human_callback,
            "transfer_to_acquisitions": _tool_prepare_transfer,
            "record_call_outcome": _tool_record_call_outcome,
            "wait_for_user": _tool_wait_for_user,
            "finish_call": _tool_finish_call,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            result: dict[str, Any] = {"ok": False, "error": "Unsupported tool."}
        else:
            try:
                result = handler(db, callback, arguments)
            except (RealtimeSellerAgentError, ValueError) as exc:
                result = {"ok": False, "error": str(exc)}
        tool_ids.append(tool_call_id)
        prior_results[tool_call_id] = result
        callback.routing_metadata = {
            **(callback.routing_metadata or {}),
            "tool_call_ids": tool_ids[-100:],
            "tool_results": dict(list(prior_results.items())[-50:]),
        }
        db.commit()
        return result


def _tool_lookup_callback_context(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    caller_name = _clean(arguments.get("caller_name"), 255)
    supplied_address = _clean(arguments.get("property_address"), 500)
    leads = _phone_matched_leads(db, callback.organization_id, callback.normalized_caller)
    for lead, contact, property_record in leads:
        name_matches = bool(caller_name and _identity_matches(caller_name, contact.legal_name))
        address_matches = bool(
            supplied_address
            and _address_matches(
                supplied_address,
                " ".join(
                    value
                    for value in (
                        property_record.street_address,
                        property_record.city,
                        property_record.state,
                        property_record.postal_code,
                    )
                    if value
                ),
            )
        )
        if name_matches or address_matches:
            callback.match_status = "unknown"
            callback.match_strategy = "verified_existing_lead"
            callback.match_confidence_basis_points = 9500
            callback.routing_metadata = {
                **(callback.routing_metadata or {}),
                "verified_lead_id": str(lead.id),
                "verified_contact_id": str(contact.id),
                "verified_property_id": str(property_record.id),
                "verification_basis": "name" if name_matches else "address",
            }
            return {
                "ok": True,
                "verified": True,
                "record_type": "lead",
                "seller_name": contact.legal_name,
                "property_address": _property_label(property_record),
                "lead_stage": lead.stage_key,
                "known_context": {
                    "property_type": property_record.property_type,
                    "motivation": lead.motivation,
                    "desired_timeline": lead.desired_timeline,
                    "occupancy_status": lead.occupancy_status,
                },
            }
    prospects = _phone_matched_prospects(db, callback.organization_id, callback.normalized_caller)
    for prospect in prospects:
        name_matches = bool(caller_name and _identity_matches(caller_name, prospect.legal_name))
        prospect_address = " ".join(
            value
            for value in (
                prospect.street_address,
                prospect.city,
                prospect.state_code,
                prospect.postal_code,
            )
            if value
        )
        address_matches = bool(
            supplied_address
            and prospect_address
            and _address_matches(supplied_address, prospect_address)
        )
        if name_matches or address_matches:
            callback.match_status = "unknown"
            callback.match_strategy = "verified_prospect"
            callback.match_confidence_basis_points = 9000
            callback.routing_metadata = {
                **(callback.routing_metadata or {}),
                "verified_prospect_id": str(prospect.id),
                "verification_basis": "name" if name_matches else "address",
            }
            return {
                "ok": True,
                "verified": True,
                "record_type": "prospect",
                "seller_name": prospect.legal_name,
                "property_address": prospect_address,
                "property_type": "land" if prospect.asset_class == "land" else "house",
            }
    callback.candidate_count = len(leads) + len(prospects)
    callback.match_status = "ambiguous" if callback.candidate_count > 1 else "unknown"
    callback.match_strategy = "phone_match_not_identity_verified"
    return {
        "ok": True,
        "verified": False,
        "possible_phone_matches": callback.candidate_count,
        "instruction": "Do not reveal any stored details. Continue using caller-supplied information.",
    }


def _tool_save_seller_details(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    details = _seller_details(arguments)
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "seller_details": details,
    }
    if not details["owner_confirmed"] or not details["seller_interested"]:
        return {"ok": True, "saved": True, "lead_created": False}

    lead = _verified_lead(db, callback)
    created = False
    if lead is None:
        lead = _create_realtime_lead(db, callback, details)
        created = True
    else:
        _update_realtime_lead(db, lead, details)
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise RealtimeSellerAgentError("Seller lead context could not be saved.")
    conversation = ensure_primary_conversation(db, lead)
    _ensure_call_communication(db, callback, lead, contact, conversation.id)
    now = datetime.now(UTC)
    update_conversation_activity(conversation, direction="inbound", occurred_at=now, db=db)
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "verified_lead_id": str(lead.id),
        "verified_contact_id": str(contact.id),
        "verified_property_id": str(property_record.id),
        "lead_created_by_agent": created,
    }
    db.add(
        ActivityEvent(
            organization_id=lead.organization_id,
            actor_user_id=None,
            entity_type="lead",
            entity_id=lead.id,
            event_type=(
                "lead.created_from_ai_seller_callback"
                if created
                else "lead.updated_from_ai_seller_callback"
            ),
            summary=(
                "Marin created this lead from a verified interested seller callback."
                if created
                else "Marin added verified seller details from an inbound callback."
            ),
        )
    )
    _notify_realtime_lead(db, callback, lead, contact, created=created)
    if created:
        queue_staff_lead_alerts_for_lead(
            db,
            lead=lead,
            source_type="openai_realtime_callback",
            source_event_id=callback.id,
            source_label="Marin callback",
            source_entity_type="prospecting_inbound_callback",
        )
    db.flush()
    return {
        "ok": True,
        "saved": True,
        "lead_created": created,
        "lead_id": str(lead.id),
        "seller_name": contact.legal_name,
        "property_address": _property_label(property_record),
    }


def _tool_schedule_human_callback(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if arguments.get("caller_confirmed") is not True:
        raise RealtimeSellerAgentError("Confirm the callback time with the caller first.")
    lead = _verified_lead(db, callback)
    if lead is None:
        raise RealtimeSellerAgentError("Save the verified interested seller before scheduling.")
    due_at = _parse_callback_time(arguments.get("callback_at"))
    if due_at <= datetime.now(UTC):
        raise RealtimeSellerAgentError("The callback time must be in the future.")
    reason = _clean(arguments.get("reason"), 500) or "Seller requested a callback."
    existing = db.scalar(
        select(Task).where(
            Task.organization_id == callback.organization_id,
            Task.lead_id == lead.id,
            Task.task_type == "seller_callback",
            Task.status.in_(("open", "in_progress")),
        )
    )
    if existing is None:
        supersede_open_primary_tasks(db, lead_id=lead.id)
        existing = Task(
            organization_id=callback.organization_id,
            lead_id=lead.id,
            deal_id=None,
            prospecting_inbound_callback_id=callback.id,
            prospect_id=None,
            call_record_id=_call_for_callback(db, callback).id,
            responsible_user_id=lead.assigned_user_id or callback.assigned_user_id,
            task_type="seller_callback",
            work_kind="primary_next_action",
            title="Call seller at the agreed time",
            status="open",
            priority="high",
            due_at=due_at,
            completed_at=None,
            completion_notes=reason,
        )
        db.add(existing)
    else:
        existing.due_at = due_at
        existing.title = "Call seller at the agreed time"
        existing.completion_notes = reason
    lead.next_follow_up_at = due_at
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "callback_at": due_at.isoformat(),
        "callback_reason": reason,
        "outcome": "callback_scheduled",
    }
    db.flush()
    return {"ok": True, "scheduled": True, "callback_at": due_at.isoformat()}


def _tool_prepare_transfer(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if arguments.get("caller_confirmed") is not True:
        raise RealtimeSellerAgentError("Ask the caller to confirm the transfer first.")
    metadata = callback.routing_metadata or {}
    if metadata.get("transferred_at"):
        return {"ok": True, "should_transfer": False, "transferred": True}
    reason = _clean(arguments.get("reason"), 500) or "Caller requested a human."
    callback.routing_metadata = {
        **metadata,
        "transfer_requested_at": datetime.now(UTC).isoformat(),
        "transfer_reason": reason,
        "outcome": "transferred",
    }
    return {
        "ok": True,
        "should_transfer": True,
        "message": "Tell the caller you are connecting them now.",
    }


def _tool_record_call_outcome(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    outcome = str(arguments.get("outcome", "")).strip()
    if outcome not in FINAL_OUTCOMES:
        raise RealtimeSellerAgentError("Choose a supported call outcome.")
    notes = _clean(arguments.get("notes"), 2000) or "No additional notes."
    if outcome == "do_not_contact":
        if arguments.get("do_not_contact_confirmed") is not True:
            raise RealtimeSellerAgentError("Confirm the do-not-contact request first.")
        _suppress_callback_number(db, callback)
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "outcome": outcome,
        "outcome_notes": notes,
        "outcome_recorded_at": datetime.now(UTC).isoformat(),
    }
    record = _call_for_callback(db, callback)
    record.disposition = outcome
    return {"ok": True, "saved": True, "outcome": outcome}


def _tool_wait_for_user(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    del db, callback, arguments
    return {"ok": True, "waiting": True}


def _tool_finish_call(
    db: Session,
    callback: ProspectingInboundCallback,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    outcome = str(arguments.get("outcome", "")).strip()
    if outcome not in FINAL_OUTCOMES:
        raise RealtimeSellerAgentError("Choose a supported final outcome.")
    summary = _clean(arguments.get("summary"), 2000)
    if not summary:
        raise RealtimeSellerAgentError("Save a concise call summary.")
    callback.routing_metadata = {
        **(callback.routing_metadata or {}),
        "outcome": outcome,
        "summary": summary,
        "finish_requested_at": datetime.now(UTC).isoformat(),
    }
    record = _call_for_callback(db, callback)
    record.disposition = outcome
    return {"ok": True, "saved": True}


def mark_call_transferred(call_id: str) -> None:
    with SessionLocal() as db:
        callback = db.scalar(
            select(ProspectingInboundCallback).where(
                ProspectingInboundCallback.provider == PROVIDER,
                ProspectingInboundCallback.provider_call_id == call_id,
            )
        )
        if callback is None:
            return
        now = datetime.now(UTC)
        callback.status = "completed"
        callback.completed_at = now
        callback.routing_metadata = {
            **(callback.routing_metadata or {}),
            "outcome": "transferred",
            "transferred_at": now.isoformat(),
            "transfer_number": get_settings().openai_realtime_transfer_number,
        }
        record = _call_for_callback(db, callback)
        record.status = "completed"
        record.ended_at = now
        record.disposition = "transferred"
        _set_call_duration(record, now)
        db.commit()


def _finish_realtime_call(
    call: RegisteredRealtimeCall,
    transcript: list[dict[str, str]],
    *,
    forced_outcome: str | None = None,
) -> None:
    with SessionLocal() as db:
        callback = db.get(ProspectingInboundCallback, call.callback_id)
        record = db.get(CallRecord, call.call_record_id)
        if callback is None or record is None:
            return
        now = datetime.now(UTC)
        metadata = dict(callback.routing_metadata or {})
        outcome = forced_outcome or str(metadata.get("outcome") or "incomplete")
        callback.status = "completed"
        callback.completed_at = now
        callback.routing_metadata = {
            **metadata,
            "outcome": outcome,
            "transcript": transcript,
            "ended_at": now.isoformat(),
        }
        record.status = "completed"
        record.ended_at = now
        record.disposition = outcome
        record.call_metadata = {
            **(record.call_metadata or {}),
            "outcome": outcome,
            "summary": metadata.get("summary"),
            "transcript": transcript,
        }
        _set_call_duration(record, now)
        communication = db.scalar(
            select(CommunicationRecord).where(
                CommunicationRecord.organization_id == callback.organization_id,
                CommunicationRecord.provider == PROVIDER,
                CommunicationRecord.provider_message_id == call.call_id,
            )
        )
        if communication is not None:
            communication.status = "received"
            communication.body = _communication_body(metadata, transcript, outcome)
            communication.communication_metadata = {
                **(communication.communication_metadata or {}),
                "outcome": outcome,
                "summary": metadata.get("summary"),
                "transcript": transcript,
            }
        db.add(
            ActivityEvent(
                organization_id=callback.organization_id,
                actor_user_id=None,
                entity_type="prospecting_inbound_callback",
                entity_id=callback.id,
                event_type="voice.ai_seller_callback_completed",
                summary=f"Marin completed a seller callback: {outcome.replace('_', ' ')}.",
            )
        )
        db.commit()


def _seller_details(arguments: dict[str, Any]) -> dict[str, Any]:
    required = {
        "seller_name": 255,
        "street_address": 255,
        "city": 120,
        "state": 2,
    }
    details: dict[str, Any] = {}
    for key, limit in required.items():
        value = _clean(arguments.get(key), limit)
        if not value:
            raise RealtimeSellerAgentError(f"Ask the caller for {key.replace('_', ' ')} first.")
        details[key] = value.upper() if key == "state" else value
    if len(details["state"]) != 2:
        raise RealtimeSellerAgentError("Use a two-letter property state.")
    details["owner_confirmed"] = arguments.get("owner_confirmed") is True
    details["seller_interested"] = arguments.get("seller_interested") is True
    for key, limit in (
        ("postal_code", 20),
        ("property_type", 80),
        ("occupancy_status", 120),
        ("property_condition", 120),
        ("desired_timeline", 120),
        ("motivation", 500),
        ("asking_price", 120),
        ("notes", 1000),
    ):
        details[key] = _clean(arguments.get(key), limit)
    return details


def _create_realtime_lead(
    db: Session,
    callback: ProspectingInboundCallback,
    details: dict[str, Any],
) -> Lead:
    contact = Contact(
        organization_id=callback.organization_id,
        legal_name=details["seller_name"],
        preferred_name=None,
        contact_type="seller",
        assigned_user_id=callback.assigned_user_id,
    )
    db.add(contact)
    db.flush()
    db.add(
        ContactMethod(
            organization_id=callback.organization_id,
            contact_id=contact.id,
            method_type="phone",
            value=callback.normalized_caller,
            normalized_value="".join(
                character for character in callback.normalized_caller if character.isdigit()
            ),
            is_primary=True,
        )
    )
    property_record = Property(
        organization_id=callback.organization_id,
        street_address=details["street_address"],
        city=details["city"],
        state=details["state"],
        postal_code=details.get("postal_code") or "",
        county=None,
        property_type=details.get("property_type"),
        normalized_address_key=None,
    )
    refresh_property_identity_keys(property_record)
    db.add(property_record)
    db.flush()
    property_type = str(details.get("property_type") or "").lower()
    lead = Lead(
        organization_id=callback.organization_id,
        contact_id=contact.id,
        property_id=property_record.id,
        assigned_user_id=callback.assigned_user_id,
        source="ai_seller_callback",
        asset_class=("land" if any(word in property_type for word in ("land", "lot")) else "house"),
        qualification_context={
            "source": "openai_realtime_seller_callback",
            "callback_id": str(callback.id),
            "owner_confirmed": True,
            "seller_interested": True,
            "notes": details.get("notes"),
        },
        stage_key="new",
        lead_temperature=None,
        motivation=details.get("motivation"),
        desired_timeline=details.get("desired_timeline"),
        property_condition=details.get("property_condition"),
        occupancy_status=details.get("occupancy_status"),
        asking_price=details.get("asking_price"),
        mortgage_balance=None,
        appointment_status=None,
        next_follow_up_at=None,
        archived_at=None,
    )
    db.add(lead)
    db.flush()
    ensure_primary_conversation(db, lead)
    db.add(
        ConsentRecord(
            organization_id=callback.organization_id,
            contact_id=contact.id,
            channel="phone",
            status="granted",
            source="inbound_call",
            wording_version="caller-initiated-v1",
            wording="Seller initiated a call to the Stonegate seller callback line.",
            normalized_address=callback.normalized_caller,
            captured_ip=None,
            user_agent=None,
        )
    )
    return lead


def _update_realtime_lead(db: Session, lead: Lead, details: dict[str, Any]) -> None:
    contact = db.get(Contact, lead.contact_id)
    property_record = db.get(Property, lead.property_id)
    if contact is None or property_record is None:
        raise RealtimeSellerAgentError("The matched lead is incomplete.")
    if contact.legal_name.startswith("Inbound caller "):
        contact.legal_name = details["seller_name"]
    for field, value in (
        ("motivation", details.get("motivation")),
        ("desired_timeline", details.get("desired_timeline")),
        ("property_condition", details.get("property_condition")),
        ("occupancy_status", details.get("occupancy_status")),
        ("asking_price", details.get("asking_price")),
    ):
        if value and not getattr(lead, field):
            setattr(lead, field, value)
    if property_record.street_address in {"Address pending", "Unknown", ""}:
        property_record.street_address = details["street_address"]
        property_record.city = details["city"]
        property_record.state = details["state"]
        property_record.postal_code = details.get("postal_code") or ""
    if not property_record.property_type and details.get("property_type"):
        property_record.property_type = details["property_type"]
    refresh_property_identity_keys(property_record)
    lead.qualification_context = {
        **(lead.qualification_context or {}),
        "openai_realtime_seller_callback": {
            "owner_confirmed": True,
            "seller_interested": True,
            "notes": details.get("notes"),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    }


def _ensure_call_communication(
    db: Session,
    callback: ProspectingInboundCallback,
    lead: Lead,
    contact: Contact,
    conversation_id: UUID,
) -> CommunicationRecord:
    existing = db.scalar(
        select(CommunicationRecord).where(
            CommunicationRecord.organization_id == callback.organization_id,
            CommunicationRecord.provider == PROVIDER,
            CommunicationRecord.provider_message_id == callback.provider_call_id,
        )
    )
    if existing is not None:
        return existing
    call_record = _call_for_callback(db, callback)
    communication = CommunicationRecord(
        organization_id=callback.organization_id,
        conversation_id=conversation_id,
        lead_id=lead.id,
        contact_id=contact.id,
        source_call_record_id=call_record.id,
        actor_user_id=None,
        direction="inbound",
        channel="call",
        status="in-progress",
        provider=PROVIDER,
        provider_message_id=callback.provider_call_id,
        subject="Inbound seller callback with Marin",
        body="Inbound seller callback is in progress with Marin.",
        occurred_at=callback.received_at,
        external_payload={"call_id": callback.provider_call_id},
        communication_metadata={
            "source": "openai_realtime_sip",
            "agent_name": AGENT_NAME,
            "callback_id": str(callback.id),
        },
    )
    db.add(communication)
    db.flush()
    return communication


def _notify_realtime_lead(
    db: Session,
    callback: ProspectingInboundCallback,
    lead: Lead,
    contact: Contact,
    *,
    created: bool,
) -> None:
    recipients = {callback.assigned_user_id, callback.fallback_user_id} - {None}
    for recipient_id in recipients:
        create_notification(
            db,
            organization_id=callback.organization_id,
            recipient_user_id=recipient_id,
            notification_type="ai_seller_callback",
            title=("New interested seller callback" if created else "Seller called Marin"),
            body=f"{contact.legal_name} is speaking with Marin about a property sale.",
            entity_type="lead",
            entity_id=lead.id,
            action_url=f"/os/leads/{lead.id}",
            dedupe_key=f"ai-seller-callback:{callback.id}:{recipient_id}",
        )


def _suppress_callback_number(db: Session, callback: ProspectingInboundCallback) -> None:
    contact_id_raw = (callback.routing_metadata or {}).get("verified_contact_id")
    contact_id = UUID(contact_id_raw) if isinstance(contact_id_raw, str) else None
    now = datetime.now(UTC)
    for channel in ("phone", "sms"):
        existing = db.scalar(
            select(SuppressionRecord).where(
                SuppressionRecord.organization_id == callback.organization_id,
                SuppressionRecord.channel == channel,
                SuppressionRecord.normalized_address == callback.normalized_caller,
            )
        )
        if existing is None:
            db.add(
                SuppressionRecord(
                    organization_id=callback.organization_id,
                    contact_id=contact_id,
                    channel=channel,
                    normalized_address=callback.normalized_caller,
                    status="active",
                    reason="Caller explicitly asked Stonegate not to contact them.",
                    source="openai_realtime_seller_callback",
                    provider=PROVIDER,
                    external_event_id=callback.provider_call_id,
                    suppressed_at=now,
                    lifted_at=None,
                    suppression_metadata={"callback_id": str(callback.id)},
                )
            )
        else:
            existing.contact_id = existing.contact_id or contact_id
            existing.status = "active"
            existing.reason = "Caller explicitly asked Stonegate not to contact them."
            existing.source = "openai_realtime_seller_callback"
            existing.provider = PROVIDER
            existing.external_event_id = callback.provider_call_id
            existing.suppressed_at = now
            existing.lifted_at = None


def _phone_matched_leads(
    db: Session,
    organization_id: UUID,
    phone_number: str,
) -> list[tuple[Lead, Contact, Property]]:
    values = phone_lookup_values(phone_number)
    rows = db.execute(
        select(Lead, Contact, Property)
        .join(Contact, Contact.id == Lead.contact_id)
        .join(ContactMethod, ContactMethod.contact_id == Contact.id)
        .join(Property, Property.id == Lead.property_id)
        .where(
            Lead.organization_id == organization_id,
            ContactMethod.organization_id == organization_id,
            ContactMethod.method_type == "phone",
            ContactMethod.normalized_value.in_(values),
        )
        .order_by(Lead.created_at.desc())
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def _phone_matched_prospects(
    db: Session,
    organization_id: UUID,
    phone_number: str,
) -> list[Prospect]:
    values = phone_lookup_values(phone_number)
    direct = list(
        db.scalars(
            select(Prospect).where(
                Prospect.organization_id == organization_id,
                Prospect.normalized_phone.in_(values),
            )
        )
    )
    contact_point_ids = db.scalars(
        select(ProspectContactPoint.prospect_id).where(
            ProspectContactPoint.organization_id == organization_id,
            ProspectContactPoint.contact_type == "phone",
            ProspectContactPoint.normalized_value.in_(values),
        )
    ).all()
    seen = {item.id for item in direct}
    for prospect in db.scalars(
        select(Prospect).where(
            Prospect.organization_id == organization_id,
            Prospect.id.in_(contact_point_ids),
        )
    ):
        if prospect.id not in seen:
            direct.append(prospect)
            seen.add(prospect.id)
    return direct


def _verified_lead(db: Session, callback: ProspectingInboundCallback) -> Lead | None:
    raw_id = (callback.routing_metadata or {}).get("verified_lead_id")
    if not isinstance(raw_id, str):
        return None
    try:
        lead_id = UUID(raw_id)
    except ValueError:
        return None
    return db.scalar(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == callback.organization_id,
        )
    )


def _call_for_callback(db: Session, callback: ProspectingInboundCallback) -> CallRecord:
    record = db.scalar(
        select(CallRecord).where(CallRecord.prospecting_inbound_callback_id == callback.id)
    )
    if record is None:
        raise RealtimeSellerAgentError("The current call record is unavailable.")
    return record


def _parse_callback_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RealtimeSellerAgentError("Ask for a specific callback date and time.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise RealtimeSellerAgentError("Use a valid callback date and time.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("America/New_York"))
    return parsed.astimezone(UTC)


def _identity_matches(supplied: str, stored: str) -> bool:
    left = _identity_tokens(supplied)
    right = _identity_tokens(stored)
    return bool(left and right and (left == right or (len(left) >= 2 and left.issubset(right))))


def _address_matches(supplied: str, stored: str) -> bool:
    left = _identity_tokens(supplied)
    right = _identity_tokens(stored)
    meaningful = {token for token in left if len(token) > 1}
    return bool(meaningful and len(meaningful) >= 2 and meaningful.issubset(right))


def _identity_tokens(value: str) -> set[str]:
    return {token for token in re.sub(r"[^a-z0-9]+", " ", value.lower()).split() if token}


def _property_label(property_record: Property) -> str:
    return ", ".join(
        value
        for value in (
            property_record.street_address,
            property_record.city,
            property_record.state,
            property_record.postal_code,
        )
        if value
    )


def _communication_body(
    metadata: dict[str, Any],
    transcript: list[dict[str, str]],
    outcome: str,
) -> str:
    summary = _clean(metadata.get("summary"), 2000) or "Marin handled an inbound seller callback."
    lines = [summary, f"Outcome: {outcome.replace('_', ' ')}."]
    if transcript:
        lines.extend(
            [
                "",
                "Transcript:",
                *[f"{item['speaker'].title()}: {item['text']}" for item in transcript],
            ]
        )
    return "\n".join(lines)[:50_000]


def _set_call_duration(record: CallRecord, ended_at: datetime) -> None:
    started_at = record.started_at
    if started_at is None:
        return
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    record.duration_seconds = max(0, int((ended_at - started_at.astimezone(UTC)).total_seconds()))


def _clean(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned[:limit] or None


async def _safe_transfer(client: OpenAIRealtimeCallClient, call_id: str, number: str) -> None:
    try:
        await client.refer(call_id, number)
    except OpenAIRealtimeError:
        logger.exception("realtime_seller_agent_fallback_transfer_failed", call_id=call_id)


async def _safe_hangup(client: OpenAIRealtimeCallClient, call_id: str) -> None:
    try:
        await client.hangup(call_id)
    except OpenAIRealtimeError:
        logger.warning("realtime_seller_agent_hangup_failed", call_id=call_id)
