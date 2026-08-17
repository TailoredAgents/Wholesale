import hashlib
import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.zapier import ZapierBatchDialerEventCreate, ZapierFacebookLeadCreate
from app.services.batchdialer_zapier import receive_zapier_batchdialer_event
from app.services.meta_lead_ads import MetaLeadIntakeThrottled, receive_zapier_facebook_lead
from app.services.request_rate_limit import (
    RequestBodyTooLargeError,
    read_bounded_request_body,
    trusted_client_address,
    zapier_batchdialer_rate_limiter,
    zapier_lead_rate_limiter,
)

router = APIRouter(prefix="/api/v1/webhooks/zapier", tags=["zapier-webhooks"])


@router.post("/batchdialer", status_code=status.HTTP_202_ACCEPTED)
async def receive_zapier_batchdialer_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    settings = get_settings()
    if not settings.zapier_batchdialer_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zapier BatchDialer ingestion is disabled.",
        )
    if not settings.zapier_batchdialer_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zapier BatchDialer ingestion is not configured.",
        )
    try:
        raw_body = await read_bounded_request_body(
            request,
            max_bytes=settings.zapier_batchdialer_max_payload_bytes,
        )
    except RequestBodyTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Zapier BatchDialer payload is too large.",
        ) from exc
    signature = request.headers.get("X-Stonegate-BatchDialer-Signature")
    secret = settings.zapier_batchdialer_webhook_secret or ""
    if not valid_batchdialer_signature(raw_body, signature, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid BatchDialer webhook signature.",
        )
    try:
        decoded = json.loads(raw_body)
        if not isinstance(decoded, dict):
            raise ValueError("Payload must be an object.")
        payload = ZapierBatchDialerEventCreate.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Zapier BatchDialer payload is invalid.",
        ) from exc
    if payload.campaign_id not in settings.zapier_batchdialer_allowed_campaign_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BatchDialer event does not belong to an allowed campaign.",
        )
    client_address = trusted_client_address(
        request,
        production=settings.app_env == "production",
    )
    retry_after = zapier_batchdialer_rate_limiter.check(
        f"zapier-batchdialer:{client_address}",
        limit=settings.zapier_batchdialer_burst_limit,
        window_seconds=settings.zapier_batchdialer_burst_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zapier BatchDialer intake is temporarily rate limited.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        accepted = receive_zapier_batchdialer_event(db, payload, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"received": True, "accepted": accepted}


def valid_batchdialer_signature(
    raw_body: bytes,
    provided_signature: str | None,
    secret: str,
) -> bool:
    if not provided_signature or not secret:
        return False
    candidate = provided_signature.strip().lower()
    if candidate.startswith("sha256="):
        candidate = candidate.removeprefix("sha256=")
    if len(candidate) != 64 or any(character not in "0123456789abcdef" for character in candidate):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(candidate, expected)


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
    try:
        raw_body = await read_bounded_request_body(
            request,
            max_bytes=settings.zapier_facebook_leads_max_payload_bytes,
        )
    except RequestBodyTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Zapier payload is too large.",
        ) from exc
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
    if payload.page_id != settings.zapier_facebook_page_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zapier Facebook lead does not belong to the configured Page.",
        )
    allowed_form_ids = settings.zapier_facebook_allowed_form_ids
    if allowed_form_ids and payload.form_id not in allowed_form_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zapier Facebook lead does not belong to an allowed form.",
        )
    client_address = trusted_client_address(
        request,
        production=settings.app_env == "production",
    )
    retry_after = zapier_lead_rate_limiter.check(
        f"zapier-facebook-leads:{client_address}",
        limit=settings.zapier_facebook_leads_burst_limit,
        window_seconds=settings.zapier_facebook_leads_burst_window_seconds,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zapier Facebook lead intake is temporarily rate limited.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        accepted = receive_zapier_facebook_lead(db, payload, settings)
    except MetaLeadIntakeThrottled as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        accepted = 0
    return {"received": True, "accepted": accepted}
