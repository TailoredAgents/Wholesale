import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.esign import process_signwell_event, verify_signwell_event
from app.services.request_rate_limit import RequestBodyTooLargeError, read_bounded_request_body

router = APIRouter(prefix="/api/v1/webhooks/esign", tags=["esign-webhooks"])
MAX_SIGNWELL_WEBHOOK_BYTES = 1_000_000


@router.post("/signwell")
async def receive_signwell_event(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    try:
        raw_body = await read_bounded_request_body(
            request,
            max_bytes=MAX_SIGNWELL_WEBHOOK_BYTES,
        )
    except RequestBodyTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="SignWell webhook payload is too large.",
        ) from exc
    try:
        decoded: Any = json.loads(raw_body)
        if not isinstance(decoded, dict):
            raise ValueError("SignWell webhook payload must be an object.")
        payload: dict[str, Any] = decoded
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="SignWell webhook payload is invalid.",
        ) from exc
    try:
        verification = verify_signwell_event(payload, db)
        matched = process_signwell_event(db, payload, verification=verification)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED
            if "signature" in str(exc).lower()
            else status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {"received": True, "matched": matched}
