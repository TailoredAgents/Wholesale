from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.integrations.meta_lead_ads import verify_meta_signature
from app.services.meta_lead_ads import receive_meta_lead_webhook

router = APIRouter(prefix="/api/v1/webhooks/meta", tags=["meta-webhooks"])


@router.get("/lead-ads")
def verify_meta_lead_ads_webhook(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    settings = get_settings()
    if (
        mode != "subscribe"
        or not settings.meta_lead_ads_verify_token
        or verify_token != settings.meta_lead_ads_verify_token
        or challenge is None
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed.")
    return Response(content=challenge, media_type="text/plain")


@router.post("/lead-ads")
async def receive_meta_lead_ads_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.meta_lead_ads_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta Lead Ads ingestion is disabled.",
        )
    raw_body = await request.body()
    if not verify_meta_signature(raw_body, signature, settings.meta_lead_ads_app_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature.")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload.")
    accepted = receive_meta_lead_webhook(db, payload, settings)
    return {"received": True, "accepted": accepted}
