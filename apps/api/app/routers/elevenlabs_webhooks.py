from __future__ import annotations

import hmac
import json
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.integrations.elevenlabs_webhooks import (
    ElevenLabsWebhookError,
    verify_elevenlabs_webhook,
)
from app.services.elevenlabs_seller_agent import (
    execute_elevenlabs_tool,
    process_elevenlabs_failure,
    process_elevenlabs_transcription,
    record_elevenlabs_audio_notice,
    register_elevenlabs_call,
)
from app.services.realtime_seller_agent import RealtimeSellerAgentError
from app.services.request_rate_limit import RequestBodyTooLargeError, read_bounded_request_body

router = APIRouter(prefix="/api/v1/webhooks/elevenlabs", tags=["elevenlabs-webhooks"])
logger = structlog.get_logger()
SUPPORTED_TOOLS = frozenset(
    {
        "lookup_callback_context",
        "capture_seller_interest",
        "save_seller_details",
        "schedule_human_callback",
        "record_call_outcome",
    }
)


@router.post("/conversation-initiation")
async def elevenlabs_conversation_initiation(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    settings = get_settings()
    _require_tool_auth(request, settings)
    _require_elevenlabs_enabled(settings)
    payload = await _json_body(request, settings)
    try:
        caller_number = _required_text(payload, "caller_id")
        called_number = _required_text(payload, "called_number")
        agent_id = _required_text(payload, "agent_id")
        conversation_id = _required_text(payload, "conversation_id")
        registered = register_elevenlabs_call(
            db,
            conversation_id=conversation_id,
            caller_number=caller_number,
            called_number=called_number,
            call_sid=_optional_text(payload.get("call_sid")),
            agent_id=agent_id,
            settings=settings,
        )
    except RealtimeSellerAgentError as exc:
        logger.warning(
            "elevenlabs_conversation_initiation_rejected",
            reason=str(exc),
            conversation_id=payload.get("conversation_id"),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {
        "type": "conversation_initiation_client_data",
        "dynamic_variables": {},
        "user_id": str(registered.callback_id),
    }


@router.post("/tools/{tool_name}")
async def elevenlabs_tool(
    tool_name: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    settings = get_settings()
    _require_tool_auth(request, settings)
    _require_elevenlabs_enabled(settings)
    if tool_name not in SUPPORTED_TOOLS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent tool.")
    payload = await _json_body(request, settings)
    try:
        result = execute_elevenlabs_tool(
            db,
            tool_name=tool_name,
            payload=payload,
            settings=settings,
        )
    except RealtimeSellerAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return result


@router.post("/post-call")
async def elevenlabs_post_call(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="ElevenLabs-Signature")] = None,
) -> dict[str, object]:
    settings = get_settings()
    try:
        raw_body = await read_bounded_request_body(
            request,
            max_bytes=settings.elevenlabs_webhook_max_bytes,
        )
    except RequestBodyTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="ElevenLabs webhook payload is too large.",
        ) from exc
    try:
        event = verify_elevenlabs_webhook(
            raw_body,
            signature,
            settings.elevenlabs_webhook_secret,
        )
    except ElevenLabsWebhookError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    event_type = _optional_text(event.get("type"))
    try:
        if event_type == "post_call_transcription":
            registered = process_elevenlabs_transcription(db, event, settings)
            return {
                "received": True,
                "conversation_id": registered.conversation_id,
                "callback_id": str(registered.callback_id),
            }
        if event_type == "post_call_audio":
            record_elevenlabs_audio_notice(db, event)
            return {"received": True, "audio_stored": False}
        if event_type == "call_initiation_failure":
            registered = process_elevenlabs_failure(db, event, settings)
            return {
                "received": True,
                "failure_recorded": True,
                "conversation_id": registered.conversation_id,
                "callback_id": str(registered.callback_id),
            }
    except RealtimeSellerAgentError as exc:
        logger.warning("elevenlabs_post_call_rejected", event_type=event_type, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {"received": True, "ignored": True}


def _require_elevenlabs_enabled(settings: Settings) -> None:
    if settings.seller_callback_agent_provider != "elevenlabs":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs is not the active seller callback provider.",
        )
    if not settings.elevenlabs_agent_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ElevenLabs seller callback integration is not configured.",
        )


def _require_tool_auth(request: Request, settings: Settings) -> None:
    configured = (settings.elevenlabs_tool_secret or "").strip()
    authorization = request.headers.get("authorization", "").strip()
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    supplied = request.headers.get("x-stonegate-agent-secret", "").strip() or bearer
    if not configured or not supplied or not hmac.compare_digest(configured, supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ElevenLabs tool authentication failed.",
        )


async def _json_body(request: Request, settings: Settings) -> dict[str, Any]:
    try:
        raw_body = await read_bounded_request_body(
            request,
            max_bytes=min(settings.elevenlabs_webhook_max_bytes, 262_144),
        )
    except RequestBodyTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="ElevenLabs request payload is too large.",
        ) from exc
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ElevenLabs request body is invalid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ElevenLabs request body must be an object.",
        )
    return payload


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _optional_text(payload.get(key))
    if not value:
        raise RealtimeSellerAgentError(f"ElevenLabs request is missing {key}.")
    return value


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
