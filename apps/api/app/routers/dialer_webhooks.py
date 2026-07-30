import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.campaign_management import DialerProviderEventCreate, DialerProviderEventRead
from app.services.dialer_provider import (
    provider_event_read,
    receive_provider_event,
    verify_webhook_signature,
)

router = APIRouter(prefix="/api/v1/webhooks/dialer", tags=["dialer-webhooks"])


@router.post("/{organization_id}")
async def receive_batchdialer_event(
    organization_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_stonegate_dialer_signature: Annotated[str | None, Header()] = None,
) -> DialerProviderEventRead:
    settings = get_settings()
    if settings.dialer_provider_mode != "live":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live dialer provider webhooks are disabled.",
        )
    raw_body = await request.body()
    if not verify_webhook_signature(
        raw_body,
        x_stonegate_dialer_signature,
        settings.batchdialer_webhook_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature.")
    try:
        decoded = json.loads(raw_body)
        payload = DialerProviderEventCreate.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unsupported dialer provider event.",
        ) from exc
    return provider_event_read(receive_provider_event(db, organization_id, payload))
