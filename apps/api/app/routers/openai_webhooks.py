from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.openai_realtime import (
    OpenAIRealtimeCallClient,
    OpenAIRealtimeError,
    OpenAIRealtimeSignatureError,
    unwrap_openai_webhook,
)
from app.services.realtime_seller_agent import (
    RealtimeSellerAgentError,
    mark_realtime_call_accepted,
    mark_realtime_call_failed,
    realtime_session_configuration,
    register_realtime_call,
    start_realtime_call_monitor,
)

router = APIRouter(prefix="/api/v1/webhooks/openai", tags=["webhooks"])
logger = structlog.get_logger()


@router.post("/realtime", status_code=204)
async def openai_realtime_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    settings = get_settings()
    body = await request.body()
    try:
        event = unwrap_openai_webhook(body, dict(request.headers), settings)
    except OpenAIRealtimeSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OpenAIRealtimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if event.get("type") != "realtime.call.incoming":
        return Response(status_code=204)
    call_id = _event_call_id(event)
    if settings.seller_callback_agent_provider != "openai_realtime":
        await _reject_if_possible(call_id, status_code=480)
        logger.warning(
            "realtime_seller_agent_provider_inactive",
            call_id=call_id,
            active_provider=settings.seller_callback_agent_provider,
        )
        return Response(status_code=204)
    if not settings.openai_realtime_voice_configured:
        await _reject_if_possible(call_id, status_code=480)
        logger.warning(
            "realtime_seller_agent_disabled",
            call_id=call_id,
            blockers=settings.openai_realtime_voice_configuration_blockers,
        )
        return Response(status_code=204)
    try:
        registered = register_realtime_call(
            db,
            event=event,
            webhook_id=request.headers.get("webhook-id", ""),
            settings=settings,
        )
    except RealtimeSellerAgentError as exc:
        await _reject_if_possible(call_id, status_code=404)
        logger.warning("realtime_seller_agent_rejected", call_id=call_id, reason=str(exc))
        return Response(status_code=204)
    if registered.terminal:
        return Response(status_code=204)
    client = OpenAIRealtimeCallClient(settings)
    if not registered.accepted:
        try:
            await client.accept(registered.call_id, realtime_session_configuration(settings))
        except OpenAIRealtimeError as exc:
            if exc.status_code != 409:
                mark_realtime_call_failed(db, registered, error=str(exc))
                await _reject_if_possible(call_id, status_code=480)
                logger.exception("realtime_seller_agent_accept_failed", call_id=call_id)
                return Response(status_code=204)
        mark_realtime_call_accepted(db, registered)
    start_realtime_call_monitor(registered)
    return Response(status_code=204)


def _event_call_id(event: dict[str, object]) -> str:
    data = event.get("data")
    return str(data.get("call_id", "")) if isinstance(data, dict) else ""


async def _reject_if_possible(call_id: str, *, status_code: int) -> None:
    settings = get_settings()
    if not call_id or not settings.openai_api_key:
        return
    try:
        await OpenAIRealtimeCallClient(settings).reject(call_id, status_code=status_code)
    except OpenAIRealtimeError:
        logger.warning("realtime_seller_agent_reject_failed", call_id=call_id)
