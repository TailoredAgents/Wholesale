from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.foundation import OperationalFailure, WorkerHeartbeat
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    get_worker_readiness,
    operation_retry_due,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    resolve_operation_failures,
)


def settings(*, required: bool = True, stale_after: int = 120) -> Settings:
    return Settings.model_validate(
        {
            "APP_ENV": "local",
            "WORKER_READINESS_REQUIRED": required,
            "WORKER_STALE_AFTER_SECONDS": stale_after,
        }
    )


def test_worker_heartbeat_reports_healthy_and_stale(db_session: Session) -> None:
    register_worker(db_session)
    record_worker_heartbeat(db_session)

    healthy = get_worker_readiness(db_session, settings())

    assert healthy.status == "healthy"
    assert healthy.required is True
    heartbeat = db_session.query(WorkerHeartbeat).one()
    heartbeat.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()

    stale = get_worker_readiness(db_session, settings(stale_after=60))

    assert stale.status == "stale"


def test_operation_failures_are_grouped_and_resolved(db_session: Session) -> None:
    register_worker(db_session)

    first = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
        error=RuntimeError("provider unavailable"),
    )
    second = record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
        error=RuntimeError("provider unavailable"),
    )

    assert second.id == first.id
    assert second.attempt_count == 2
    assert operation_retry_due(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
    ) is False
    assert db_session.query(OperationalFailure).count() == 1
    heartbeat = db_session.query(WorkerHeartbeat).one()
    assert heartbeat.status == "degraded"
    assert heartbeat.consecutive_failures == 2
    assert heartbeat.total_failures == 2

    resolve_operation_failures(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name="email_sync",
    )

    db_session.refresh(second)
    assert second.status == "resolved"
    assert second.resolved_at is not None
