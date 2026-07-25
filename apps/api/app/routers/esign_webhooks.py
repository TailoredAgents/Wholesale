from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.esign import process_signwell_event, verify_signwell_event

router = APIRouter(prefix="/api/v1/webhooks/esign", tags=["esign-webhooks"])


@router.post("/signwell")
def receive_signwell_event(
    payload: Annotated[dict[str, Any], Body()],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    try:
        verify_signwell_event(payload)
        matched = process_signwell_event(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED
            if "signature" in str(exc).lower()
            else status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return {"received": True, "matched": matched}
