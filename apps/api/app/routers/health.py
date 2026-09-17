from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.observability import database_observability_snapshot
from app.services.operations import get_worker_operational_health

router = APIRouter(tags=["health"])
logger = structlog.get_logger()


def _unavailable_operations_payload(
    settings: Settings,
    *,
    database_status: str,
) -> dict[str, object]:
    return {
        "status": "unhealthy",
        "database": {"status": database_status},
        "worker": {
            "status": "unknown",
            "required": settings.worker_readiness_required,
            "heartbeat_at": None,
            "current_operation": None,
            "consecutive_failures": None,
            "open_failure_depth": None,
            "oldest_open_failure_age_seconds": None,
        },
        "providers": [],
        "operations": [],
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/database-observability")
def database_observability(
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    snapshot = database_observability_snapshot(db)
    return {
        "database": {
            "dialect": snapshot.dialect,
            "pg_stat_statements": snapshot.pg_stat_statements,
        },
        "pool": {
            "class": snapshot.pool.pool_class,
            "size": snapshot.pool.size,
            "checked_in": snapshot.pool.checked_in,
            "checked_out": snapshot.pool.checked_out,
            "overflow": snapshot.pool.overflow,
        },
    }


@router.get("/ready")
def ready(
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    payload: dict[str, object] = {
        "status": "ready",
        "checks": {
            "database": "ready",
        },
    }
    try:
        db.execute(text("select 1"))
    except Exception:
        response.status_code = 503
        payload["status"] = "not_ready"
        payload["checks"] = {"database": "unavailable"}
    return payload


@router.get("/health/operations")
def operations_health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    try:
        db.execute(text("select 1"))
    except Exception as exc:
        logger.error(
            "operational_health_database_check_failed",
            error_type=type(exc).__name__,
        )
        response.status_code = 503
        return _unavailable_operations_payload(settings, database_status="unavailable")
    try:
        operational = get_worker_operational_health(db, settings)
    except Exception as exc:
        logger.error(
            "operational_health_aggregation_failed",
            error_type=type(exc).__name__,
        )
        response.status_code = 503
        return _unavailable_operations_payload(settings, database_status="ready")
    payload: dict[str, object] = {
        "status": operational.status,
        "database": {"status": "ready"},
        "worker": {
            "status": operational.worker.status,
            "required": operational.worker.required,
            "heartbeat_at": (
                operational.worker.heartbeat_at.isoformat()
                if operational.worker.heartbeat_at is not None
                else None
            ),
            "current_operation": operational.worker.current_operation,
            "consecutive_failures": operational.worker.consecutive_failures,
            "open_failure_depth": operational.open_failure_depth,
            "oldest_open_failure_age_seconds": (operational.oldest_open_failure_age_seconds),
        },
        "providers": [
            {
                "name": provider.provider_name,
                "status": provider.status,
                "configuration_blockers": list(provider.configuration_blockers),
                "open_failure_depth": provider.open_failure_depth,
                "oldest_open_failure_age_seconds": (provider.oldest_open_failure_age_seconds),
            }
            for provider in operational.providers
        ],
        "operations": [
            {
                "name": operation.operation_name,
                "last_outcome": operation.last_outcome,
                "last_duration_ms": operation.last_duration_ms,
                "last_finished_at": (
                    operation.last_finished_at.isoformat()
                    if operation.last_finished_at is not None
                    else None
                ),
                "open_failure_depth": operation.open_failure_depth,
                "open_failure_attempts": operation.open_failure_attempts,
                "oldest_open_failure_age_seconds": (operation.oldest_open_failure_age_seconds),
                "next_retry_at": (
                    operation.next_retry_at.isoformat()
                    if operation.next_retry_at is not None
                    else None
                ),
                "error_types": list(operation.error_types),
            }
            for operation in operational.operations
        ],
    }
    if operational.status != "healthy":
        response.status_code = 503
    return payload
