from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.operations import get_worker_readiness

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    try:
        db.execute(text("select 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    worker = get_worker_readiness(db, settings)
    if worker.required and worker.status in {"missing", "stale"}:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": {"database": "ready", "worker": worker.status},
            },
        )
    return {
        "status": "ready",
        "checks": {
            "database": "ready",
            "worker": worker.status,
        },
    }
