from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.resend_webhooks import (
    ResendWebhookVerificationError,
    verify_resend_webhook,
)
from app.services.resend_email_events import ingest_resend_event

router = APIRouter(prefix="/api/v1/webhooks/resend", tags=["resend-webhooks"])
MAX_WEBHOOK_BYTES = 1_000_000


@router.post("")
async def receive_resend_event(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    event_id: Annotated[str | None, Header(alias="svix-id")] = None,
    timestamp: Annotated[str | None, Header(alias="svix-timestamp")] = None,
    signature: Annotated[str | None, Header(alias="svix-signature")] = None,
) -> dict[str, object]:
    raw_body = await request.body()
    if len(raw_body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Resend webhook payload is too large.",
        )
    try:
        payload = verify_resend_webhook(
            payload=raw_body,
            event_id=event_id,
            timestamp=timestamp,
            signature=signature,
            webhook_secret=get_settings().resend_webhook_secret,
        )
        event, created = ingest_resend_event(
            db,
            external_event_id=event_id or "",
            payload=payload,
        )
    except ResendWebhookVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {
        "received": True,
        "created": created,
        "event_id": str(event.id),
        "processing_status": event.processing_status,
    }
