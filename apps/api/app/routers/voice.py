from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import Principal, require_any_permission, require_permission
from app.core.config import get_settings
from app.core.database import get_db
from app.domain.rbac import PermissionKeys
from app.schemas.voice import (
    VoiceCallIntentCreate,
    VoiceCallIntentRead,
    VoiceLineAssignmentUpdate,
    VoiceLineCreate,
    VoiceLineListResponse,
    VoiceLineRead,
    VoiceSessionRead,
)
from app.services.voice import (
    VoiceComplianceError,
    VoiceConfigurationError,
    VoiceIntentConflictError,
    create_call_intent,
    create_voice_line,
    create_voice_session,
    get_scoped_recording,
    list_voice_lines,
    update_voice_line,
)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
call_dependency = require_any_permission(
    PermissionKeys.PLACE_CALLS,
    PermissionKeys.PLACE_ASSIGNED_CALLS,
)
manage_lines_dependency = require_permission(PermissionKeys.MANAGE_VOICE_LINES)
recording_dependency = require_permission(PermissionKeys.ACCESS_RECORDINGS)


@router.get("/session")
def read_voice_session(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(call_dependency)],
) -> VoiceSessionRead:
    return create_voice_session(db, principal)


@router.post("/conversations/{conversation_id}/call-intents", status_code=201)
def create_conversation_call_intent(
    conversation_id: UUID,
    payload: VoiceCallIntentCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(call_dependency)],
) -> VoiceCallIntentRead:
    try:
        intent = create_call_intent(db, principal, conversation_id, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except VoiceComplianceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except VoiceConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VoiceIntentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    return intent


@router.get("/lines")
def read_voice_lines(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_lines_dependency)],
) -> VoiceLineListResponse:
    return VoiceLineListResponse(items=list_voice_lines(db, principal))


@router.post("/lines", status_code=201)
def create_company_voice_line(
    payload: VoiceLineCreate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_lines_dependency)],
) -> VoiceLineRead:
    try:
        return create_voice_line(db, principal, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except VoiceIntentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/lines/{line_id}")
def update_company_voice_line(
    line_id: UUID,
    payload: VoiceLineAssignmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(manage_lines_dependency)],
) -> VoiceLineRead:
    try:
        line = update_voice_line(db, principal, line_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice line not found.")
    return line


@router.get("/recordings/{recording_id}/media")
def read_voice_recording_media(
    recording_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(recording_dependency)],
) -> Response:
    recording = get_scoped_recording(db, principal, recording_id)
    if recording is None or not recording.provider_recording_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found.")
    if recording.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recording is not ready.",
        )
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio recording access is not configured.",
        )
    media_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}"
        f"/Recordings/{recording.provider_recording_id}.mp3"
    )
    try:
        provider_response = httpx.get(
            media_url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=30,
        )
        provider_response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Twilio recording media could not be retrieved.",
        ) from exc
    return Response(
        content=provider_response.content,
        media_type=provider_response.headers.get("content-type", "audio/mpeg"),
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="stonegate-call-{recording.id}.mp3"',
        },
    )
