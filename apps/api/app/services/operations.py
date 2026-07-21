import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import OperationalFailure, WorkerHeartbeat

COMMUNICATIONS_WORKER = "stonegate-communications-worker"


@dataclass(frozen=True)
class WorkerReadiness:
    status: str
    required: bool
    heartbeat_at: datetime | None
    consecutive_failures: int


def register_worker(db: Session, service_name: str = COMMUNICATIONS_WORKER) -> WorkerHeartbeat:
    now = datetime.now(UTC)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(
            service_name=service_name,
            status="starting",
            started_at=now,
            heartbeat_at=now,
            last_success_at=None,
            last_error_at=None,
            consecutive_failures=0,
            total_failures=0,
            worker_metadata={"process_started_at": now.isoformat()},
        )
        db.add(heartbeat)
    else:
        heartbeat.status = "starting"
        heartbeat.started_at = now
        heartbeat.heartbeat_at = now
        heartbeat.consecutive_failures = 0
        heartbeat.worker_metadata = {
            **(heartbeat.worker_metadata or {}),
            "process_started_at": now.isoformat(),
        }
    db.commit()
    db.refresh(heartbeat)
    return heartbeat


def record_worker_heartbeat(
    db: Session,
    *,
    service_name: str = COMMUNICATIONS_WORKER,
    had_error: bool = False,
) -> None:
    now = datetime.now(UTC)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        heartbeat = register_worker(db, service_name)
    heartbeat.heartbeat_at = now
    heartbeat.status = "degraded" if had_error else "healthy"
    if not had_error:
        heartbeat.last_success_at = now
        heartbeat.consecutive_failures = 0
    db.commit()


def record_operation_failure(
    db: Session,
    *,
    service_name: str,
    operation_name: str,
    error: Exception,
    retry_base_seconds: int = 15,
    retry_max_seconds: int = 900,
) -> OperationalFailure:
    now = datetime.now(UTC)
    error_type = type(error).__name__
    error_message = str(error)[:2000] or error_type
    fingerprint = hashlib.sha256(
        f"{service_name}|{operation_name}|{error_type}".encode()
    ).hexdigest()
    failure = db.scalar(
        select(OperationalFailure)
        .where(
            OperationalFailure.service_name == service_name,
            OperationalFailure.operation_name == operation_name,
            OperationalFailure.fingerprint == fingerprint,
            OperationalFailure.status == "open",
        )
        .order_by(OperationalFailure.last_occurred_at.desc())
    )
    if failure is None:
        attempt_count = 1
        failure = OperationalFailure(
            service_name=service_name,
            operation_name=operation_name,
            status="open",
            fingerprint=fingerprint,
            attempt_count=attempt_count,
            error_type=error_type,
            error_message=error_message,
            first_occurred_at=now,
            last_occurred_at=now,
            next_retry_at=now
            + timedelta(seconds=min(retry_base_seconds, retry_max_seconds)),
            resolved_at=None,
            failure_metadata=None,
        )
        db.add(failure)
    else:
        failure.attempt_count += 1
        failure.last_occurred_at = now
        failure.error_message = error_message
        retry_seconds = min(
            retry_base_seconds * (2 ** min(failure.attempt_count - 1, 16)),
            retry_max_seconds,
        )
        failure.next_retry_at = now + timedelta(seconds=retry_seconds)

    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is not None:
        heartbeat.status = "degraded"
        heartbeat.heartbeat_at = now
        heartbeat.last_error_at = now
        heartbeat.consecutive_failures += 1
        heartbeat.total_failures += 1
    db.commit()
    db.refresh(failure)
    return failure


def operation_retry_due(
    db: Session,
    *,
    service_name: str,
    operation_name: str,
) -> bool:
    failure = db.scalar(
        select(OperationalFailure)
        .where(
            OperationalFailure.service_name == service_name,
            OperationalFailure.operation_name == operation_name,
            OperationalFailure.status == "open",
        )
        .order_by(OperationalFailure.last_occurred_at.desc())
    )
    if failure is None:
        return True
    next_retry_at = failure.next_retry_at
    if next_retry_at.tzinfo is None:
        next_retry_at = next_retry_at.replace(tzinfo=UTC)
    return next_retry_at <= datetime.now(UTC)


def resolve_operation_failures(
    db: Session,
    *,
    service_name: str,
    operation_name: str,
) -> None:
    failures = db.scalars(
        select(OperationalFailure).where(
            OperationalFailure.service_name == service_name,
            OperationalFailure.operation_name == operation_name,
            OperationalFailure.status == "open",
        )
    ).all()
    if not failures:
        return
    resolved_at = datetime.now(UTC)
    for failure in failures:
        failure.status = "resolved"
        failure.resolved_at = resolved_at
    db.commit()


def get_worker_readiness(db: Session, settings: Settings) -> WorkerReadiness:
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == COMMUNICATIONS_WORKER)
    )
    if heartbeat is None:
        return WorkerReadiness(
            status="missing" if settings.worker_readiness_required else "not_required",
            required=settings.worker_readiness_required,
            heartbeat_at=None,
            consecutive_failures=0,
        )
    heartbeat_at = heartbeat.heartbeat_at
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
    stale_before = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_after_seconds)
    status = "stale" if heartbeat_at < stale_before else heartbeat.status
    return WorkerReadiness(
        status=status,
        required=settings.worker_readiness_required,
        heartbeat_at=heartbeat_at,
        consecutive_failures=heartbeat.consecutive_failures,
    )
