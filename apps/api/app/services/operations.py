import hashlib
from collections.abc import Sequence
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
    current_operation: str | None


@dataclass(frozen=True)
class OperationOperationalHealth:
    operation_name: str
    last_outcome: str | None
    last_duration_ms: int | None
    last_finished_at: datetime | None
    open_failure_depth: int
    open_failure_attempts: int
    oldest_open_failure_age_seconds: int | None
    next_retry_at: datetime | None
    error_types: tuple[str, ...]


@dataclass(frozen=True)
class ProviderOperationalHealth:
    provider_name: str
    status: str
    configuration_blockers: tuple[str, ...]
    open_failure_depth: int
    oldest_open_failure_age_seconds: int | None


@dataclass(frozen=True)
class WorkerOperationalHealth:
    status: str
    worker: WorkerReadiness
    open_failure_depth: int
    oldest_open_failure_age_seconds: int | None
    operations: tuple[OperationOperationalHealth, ...]
    providers: tuple[ProviderOperationalHealth, ...]


def meta_pixel_id_fingerprint(pixel_id: str | None) -> str | None:
    normalized = (pixel_id or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]


def safe_meta_runtime_metadata(settings: Settings) -> dict[str, object]:
    """Return safe worker/provider state without IDs, tokens, or test codes."""
    blockers = list(settings.meta_conversion_configuration_blockers)
    batchdialer_blockers = list(settings.batchdialer_configuration_blockers)
    return {
        "runtime_metadata_schema_version": 1,
        "marketing_conversion_mode": settings.marketing_conversion_mode,
        "meta_pixel_id_fingerprint": meta_pixel_id_fingerprint(settings.meta_pixel_id),
        "meta_test_mode_enabled": bool(settings.meta_test_event_code),
        "meta_configured": not blockers,
        "meta_configuration_blockers": blockers,
        "meta_access_token_present": bool(settings.meta_conversions_access_token),
        "zapier_facebook_leads_enabled": settings.zapier_facebook_leads_enabled,
        "batchdialer_configured": not batchdialer_blockers,
        "batchdialer_configuration_blockers": batchdialer_blockers,
    }


def register_worker(
    db: Session,
    service_name: str = COMMUNICATIONS_WORKER,
    *,
    runtime_metadata: dict[str, object] | None = None,
) -> WorkerHeartbeat:
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
            worker_metadata={
                "process_started_at": now.isoformat(),
                "main_loop_progress_at": now.isoformat(),
                "current_operation": None,
                "operation_started_at": None,
                **(runtime_metadata or {}),
            },
        )
        db.add(heartbeat)
    else:
        heartbeat.status = "starting"
        heartbeat.started_at = now
        heartbeat.heartbeat_at = now
        heartbeat.consecutive_failures = 0
        heartbeat.worker_metadata = {
            "process_started_at": now.isoformat(),
            "main_loop_progress_at": now.isoformat(),
            "current_operation": None,
            "operation_started_at": None,
            **(runtime_metadata or {}),
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
    heartbeat.worker_metadata = {
        **(heartbeat.worker_metadata or {}),
        "main_loop_progress_at": now.isoformat(),
        "current_operation": None,
        "operation_started_at": None,
    }
    if not had_error:
        heartbeat.last_success_at = now
        heartbeat.consecutive_failures = 0
    db.commit()


def touch_worker_heartbeat(
    db: Session,
    *,
    service_name: str = COMMUNICATIONS_WORKER,
) -> None:
    """Refresh liveness without hiding a degraded worker state."""
    now = datetime.now(UTC)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        register_worker(db, service_name)
        return
    heartbeat.heartbeat_at = now
    db.commit()


def mark_worker_operation_started(
    db: Session,
    operation_name: str,
    *,
    service_name: str = COMMUNICATIONS_WORKER,
) -> None:
    """Record main-loop progress separately from the liveness heartbeat."""
    now = datetime.now(UTC)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        heartbeat = register_worker(db, service_name)
    heartbeat.heartbeat_at = now
    heartbeat.worker_metadata = {
        **(heartbeat.worker_metadata or {}),
        "main_loop_progress_at": now.isoformat(),
        "current_operation": operation_name,
        "operation_started_at": now.isoformat(),
    }
    db.commit()


def mark_worker_operation_finished(
    db: Session,
    operation_name: str,
    *,
    service_name: str = COMMUNICATIONS_WORKER,
    outcome: str = "idle",
    duration_ms: int | None = None,
) -> None:
    """Clear the in-flight marker and retain bounded, low-cardinality timing data."""
    now = datetime.now(UTC)
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        heartbeat = register_worker(db, service_name)
    metadata = dict(heartbeat.worker_metadata or {})
    if metadata.get("current_operation") == operation_name:
        metadata["current_operation"] = None
        metadata["operation_started_at"] = None
    metadata["main_loop_progress_at"] = now.isoformat()
    operation_metrics = metadata.get("operation_metrics")
    if not isinstance(operation_metrics, dict):
        operation_metrics = {}
    operation_metrics = dict(operation_metrics)
    operation_metrics[operation_name] = {
        "last_outcome": outcome,
        "last_duration_ms": (
            max(0, min(duration_ms, 86_400_000)) if duration_ms is not None else None
        ),
        "last_finished_at": now.isoformat(),
    }
    metadata["operation_metrics"] = operation_metrics
    heartbeat.worker_metadata = metadata
    heartbeat.heartbeat_at = now
    db.commit()


def touch_worker_operation_progress(
    db: Session,
    operation_name: str,
    *,
    service_name: str = COMMUNICATIONS_WORKER,
) -> None:
    """Record progress within a long operation without changing its outcome."""
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == service_name)
    )
    if heartbeat is None:
        return
    metadata = dict(heartbeat.worker_metadata or {})
    if metadata.get("current_operation") != operation_name:
        return
    now = datetime.now(UTC)
    metadata["main_loop_progress_at"] = now.isoformat()
    heartbeat.worker_metadata = metadata
    heartbeat.heartbeat_at = now
    db.commit()


def resolve_retired_operation_failures(
    db: Session,
    active_operation_names: set[str],
    *,
    service_name: str = COMMUNICATIONS_WORKER,
) -> int:
    """Close failures for worker operations removed from the active registry."""
    failures = db.scalars(
        select(OperationalFailure).where(
            OperationalFailure.service_name == service_name,
            OperationalFailure.status == "open",
        )
    ).all()
    retired = [
        failure
        for failure in failures
        if failure.operation_name not in active_operation_names
    ]
    if not retired:
        return 0
    resolved_at = datetime.now(UTC)
    for failure in retired:
        failure.status = "resolved"
        failure.resolved_at = resolved_at
        failure.failure_metadata = {
            **(failure.failure_metadata or {}),
            "resolution_reason": "operation_retired",
        }
    db.commit()
    return len(retired)


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
            next_retry_at=now + timedelta(seconds=min(retry_base_seconds, retry_max_seconds)),
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
    return worker_readiness_from_heartbeat(heartbeat, settings)


def worker_readiness_from_heartbeat(
    heartbeat: WorkerHeartbeat | None,
    settings: Settings,
) -> WorkerReadiness:
    if heartbeat is None:
        return WorkerReadiness(
            status="missing" if settings.worker_readiness_required else "not_required",
            required=settings.worker_readiness_required,
            heartbeat_at=None,
            consecutive_failures=0,
            current_operation=None,
        )
    heartbeat_at = heartbeat.heartbeat_at
    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.worker_stale_after_seconds)
    progress_stale_before = now - timedelta(seconds=settings.worker_operation_stall_seconds)
    metadata = heartbeat.worker_metadata or {}
    current_operation = str(metadata.get("current_operation") or "").strip() or None
    progress_at = parse_heartbeat_metadata_datetime(metadata.get("main_loop_progress_at"))
    if heartbeat_at < stale_before:
        status = "stale"
    elif progress_at is not None and progress_at < progress_stale_before:
        status = "stalled"
    else:
        status = heartbeat.status
    return WorkerReadiness(
        status=status,
        required=settings.worker_readiness_required,
        heartbeat_at=heartbeat_at,
        consecutive_failures=heartbeat.consecutive_failures,
        current_operation=current_operation,
    )


def get_worker_operational_health(
    db: Session,
    settings: Settings,
) -> WorkerOperationalHealth:
    """Return worker/provider health without exposing provider payloads or secrets."""
    heartbeat = db.scalar(
        select(WorkerHeartbeat).where(WorkerHeartbeat.service_name == COMMUNICATIONS_WORKER)
    )
    worker = worker_readiness_from_heartbeat(heartbeat, settings)
    failures = db.scalars(
        select(OperationalFailure).where(
            OperationalFailure.service_name == COMMUNICATIONS_WORKER,
            OperationalFailure.status == "open",
        )
    ).all()
    now = datetime.now(UTC)
    failures_by_operation: dict[str, list[OperationalFailure]] = {}
    for failure in failures:
        failures_by_operation.setdefault(failure.operation_name, []).append(failure)

    raw_metrics: dict[str, object] = {}
    if heartbeat is not None:
        metrics = (heartbeat.worker_metadata or {}).get("operation_metrics")
        if isinstance(metrics, dict):
            raw_metrics = metrics

    operations: list[OperationOperationalHealth] = []
    for operation_name in sorted(set(raw_metrics) | set(failures_by_operation)):
        metric = raw_metrics.get(operation_name)
        metric = metric if isinstance(metric, dict) else {}
        operation_failures = failures_by_operation.get(operation_name, [])
        first_failure_at = _oldest_failure_at(operation_failures)
        next_retry_at = _earliest_retry_at(operation_failures)
        duration = metric.get("last_duration_ms")
        operations.append(
            OperationOperationalHealth(
                operation_name=operation_name,
                last_outcome=_optional_string(metric.get("last_outcome")),
                last_duration_ms=duration if isinstance(duration, int) else None,
                last_finished_at=parse_heartbeat_metadata_datetime(metric.get("last_finished_at")),
                open_failure_depth=len(operation_failures),
                open_failure_attempts=sum(item.attempt_count for item in operation_failures),
                oldest_open_failure_age_seconds=_age_seconds(now, first_failure_at),
                next_retry_at=next_retry_at,
                error_types=tuple(sorted({item.error_type for item in operation_failures})),
            )
        )

    oldest_failure_at = _oldest_failure_at(failures)
    batchdialer_failures = [
        failure for failure in failures if failure.operation_name.startswith("batchdialer_")
    ]
    batchdialer_oldest = _oldest_failure_at(batchdialer_failures)
    worker_metadata = heartbeat.worker_metadata if heartbeat is not None else {}
    worker_metadata = worker_metadata if isinstance(worker_metadata, dict) else {}
    runtime_metadata_current = worker_metadata.get("runtime_metadata_schema_version") == 1
    batchdialer_blockers = _runtime_blockers(
        worker_metadata,
        "batchdialer_configuration_blockers",
        settings.batchdialer_configuration_blockers,
    )
    if heartbeat is not None and worker.required and not runtime_metadata_current:
        batchdialer_blockers = (
            *batchdialer_blockers,
            "worker:runtime_metadata_schema_version=1",
        )
    if batchdialer_failures or (
        heartbeat is not None and worker.required and not runtime_metadata_current
    ):
        batchdialer_status = "degraded"
    elif not batchdialer_blockers:
        batchdialer_status = "configured"
    else:
        batchdialer_status = "not_configured"

    zapier_enabled = _runtime_bool(
        worker_metadata,
        "zapier_facebook_leads_enabled",
        settings.zapier_facebook_leads_enabled,
    )
    zapier_failures = failures_by_operation.get("meta_lead_ads", [])
    zapier_oldest = _oldest_failure_at(zapier_failures)
    zapier_blockers = list(settings.production_zapier_facebook_leads_configuration_blockers)
    if heartbeat is not None and worker.required and not runtime_metadata_current:
        zapier_blockers.append("worker:runtime_metadata_schema_version=1")
    api_zapier_enabled = settings.zapier_facebook_leads_enabled
    if api_zapier_enabled and not zapier_enabled:
        zapier_blockers.append("worker:ZAPIER_FACEBOOK_LEADS_ENABLED=true")
    elif zapier_enabled and not api_zapier_enabled:
        zapier_blockers.append("api:ZAPIER_FACEBOOK_LEADS_ENABLED=true")
    if zapier_failures:
        zapier_status = "degraded"
    elif not api_zapier_enabled and not zapier_enabled:
        zapier_status = "disabled"
    elif zapier_blockers:
        zapier_status = "degraded"
    else:
        zapier_status = "configured"

    providers = (
        ProviderOperationalHealth(
            provider_name="batchdialer",
            status=batchdialer_status,
            configuration_blockers=batchdialer_blockers,
            open_failure_depth=len(batchdialer_failures),
            oldest_open_failure_age_seconds=_age_seconds(now, batchdialer_oldest),
        ),
        ProviderOperationalHealth(
            provider_name="zapier_facebook_leads",
            status=zapier_status,
            configuration_blockers=tuple(zapier_blockers),
            open_failure_depth=len(zapier_failures),
            oldest_open_failure_age_seconds=_age_seconds(now, zapier_oldest),
        ),
    )

    if worker.required and worker.status in {"missing", "stale", "stalled"}:
        status = "unhealthy"
    elif (
        worker.status in {"starting", "degraded"}
        or failures
        or any(provider.status == "degraded" for provider in providers)
    ):
        status = "degraded"
    else:
        status = "healthy"

    return WorkerOperationalHealth(
        status=status,
        worker=worker,
        open_failure_depth=len(failures),
        oldest_open_failure_age_seconds=_age_seconds(now, oldest_failure_at),
        operations=tuple(operations),
        providers=providers,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _runtime_bool(metadata: dict[str, object], key: str, fallback: bool) -> bool:
    value = metadata.get(key)
    return value if isinstance(value, bool) else fallback


def _runtime_blockers(
    metadata: dict[str, object],
    key: str,
    fallback: Sequence[str],
) -> tuple[str, ...]:
    value = metadata.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return tuple(fallback)
    return tuple(item for item in value if item)


def _aware_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _oldest_failure_at(failures: Sequence[OperationalFailure]) -> datetime | None:
    if not failures:
        return None
    return min(_aware_datetime(failure.first_occurred_at) for failure in failures)


def _earliest_retry_at(failures: Sequence[OperationalFailure]) -> datetime | None:
    if not failures:
        return None
    return min(_aware_datetime(failure.next_retry_at) for failure in failures)


def _age_seconds(now: datetime, then: datetime | None) -> int | None:
    if then is None:
        return None
    return max(0, int((now - then).total_seconds()))


def parse_heartbeat_metadata_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
