import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.zapier import ZapierFacebookLeadCreate
from app.services.meta_lead_ads import receive_zapier_facebook_lead

router = APIRouter(prefix="/api/v1/webhooks/zapier", tags=["zapier-webhooks"])


@router.post("/facebook-leads")
async def receive_zapier_facebook_lead_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    settings = get_settings()
    if not settings.zapier_facebook_leads_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zapier Facebook lead ingestion is disabled.",
        )
    if not settings.zapier_facebook_leads_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zapier Facebook lead ingestion is not configured.",
        )
    content_length = request.headers.get("content-length")
    if (
        content_length
        and content_length.isdigit()
        and int(content_length) > settings.zapier_facebook_leads_max_payload_bytes
    ):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Zapier payload is too large.",
        )
    raw_body = await request.body()
    if len(raw_body) > settings.zapier_facebook_leads_max_payload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Zapier payload is too large.",
        )
    try:
        decoded = json.loads(raw_body)
        if not isinstance(decoded, dict):
            raise ValueError("Payload must be an object.")
        payload = ZapierFacebookLeadCreate.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Zapier Facebook lead payload is invalid.",
        ) from exc
    try:
        accepted = receive_zapier_facebook_lead(db, payload, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        accepted = 0
    return {"received": True, "accepted": accepted}
