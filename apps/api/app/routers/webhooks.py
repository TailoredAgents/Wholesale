from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.twilio_messaging import validate_twilio_signature
from app.integrations.twilio_voice import disclosure_twiml, hangup_twiml
from app.services.messaging import process_twilio_inbound, process_twilio_status
from app.services.voice import (
    VoiceConfigurationError,
    process_inbound_voice_request,
    process_outbound_voice_request,
    process_voice_recording,
    process_voice_recording_disclosure,
    process_voice_status,
)

router = APIRouter(prefix="/api/v1/webhooks/twilio", tags=["webhooks"])


@router.post("/messaging/incoming")
async def twilio_incoming_message(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    try:
        process_twilio_inbound(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/messaging/status", status_code=204)
async def twilio_message_status(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    try:
        process_twilio_status(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return Response(status_code=204)


@router.post("/voice/outbound")
async def twilio_outbound_voice(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    raw_intent_id = payload.get("CallIntentId")
    if not raw_intent_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Missing Stonegate call intent.",
        )
    try:
        intent_id = UUID(raw_intent_id)
        content = process_outbound_voice_request(db, payload, intent_id=intent_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except (ValueError, VoiceConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return Response(content=content, media_type="application/xml")


@router.post("/voice/incoming")
async def twilio_inbound_voice(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    try:
        content = process_inbound_voice_request(db, payload)
    except VoiceConfigurationError:
        content = hangup_twiml("Stonegate is unavailable. Please try again shortly.")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return Response(content=content, media_type="application/xml")


@router.post("/voice/status", status_code=204)
async def twilio_voice_status(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    process_voice_status(
        db,
        payload,
        intent_id=intent_id,
        call_id=call_id,
    )
    return Response(status_code=204)


@router.post("/voice/dial-result")
async def twilio_voice_dial_result(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    process_voice_status(
        db,
        payload,
        intent_id=intent_id,
        call_id=call_id,
    )
    return Response(content=hangup_twiml(), media_type="application/xml")


@router.post("/voice/recording", status_code=204)
async def twilio_voice_recording(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    process_voice_recording(
        db,
        payload,
        intent_id=intent_id,
        call_id=call_id,
    )
    return Response(status_code=204)


@router.post("/voice/disclosure")
async def twilio_voice_recording_disclosure(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
    intent_id: UUID | None = None,
    call_id: UUID | None = None,
) -> Response:
    payload = await parse_twilio_form(request)
    validate_request(request, payload, signature)
    process_voice_recording_disclosure(
        db,
        payload,
        intent_id=intent_id,
        call_id=call_id,
    )
    return Response(content=disclosure_twiml(get_settings()), media_type="application/xml")


async def parse_twilio_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    return dict(parse_qsl(body, keep_blank_values=True))


def validate_request(
    request: Request,
    payload: dict[str, str],
    signature: str | None,
) -> None:
    settings = get_settings()
    if not settings.twilio_validate_webhook_signatures:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Twilio webhook validation cannot be disabled in production.",
            )
        return
    if not settings.twilio_auth_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio webhook validation is not configured.",
        )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing Twilio webhook signature.",
        )
    messaging_service_sid = payload.get("MessagingServiceSid")
    if (
        settings.twilio_messaging_service_sid
        and messaging_service_sid
        and messaging_service_sid != settings.twilio_messaging_service_sid
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Twilio webhook used an unexpected Messaging Service.",
        )
    validation_url = build_validation_url(request)
    if not validate_twilio_signature(
        url=validation_url,
        form_values=payload,
        signature=signature,
        auth_token=settings.twilio_auth_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio webhook signature.",
        )


def build_validation_url(request: Request) -> str:
    settings = get_settings()
    base_url = settings.twilio_webhook_base_url
    if base_url:
        url = f"{base_url.rstrip('/')}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        return url
    return str(request.url)
