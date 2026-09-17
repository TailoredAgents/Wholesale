import threading
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.core.config import Settings
from app.models.foundation import OperationalFailure, WorkerHeartbeat
from app.services.batchdialer_call_facts import (
    backfill_next_batchdialer_call_fact_batch,
)
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    record_operation_failure,
    register_worker,
)


def test_worker_registers_batchdialer_call_fact_backfill() -> None:
    operation = (
        "batchdialer_call_fact_backfill",
        backfill_next_batchdialer_call_fact_batch,
    )
    assert operation in worker.WORKER_OPERATIONS
    assert worker.WORKER_OPERATIONS[-1] == operation


def test_worker_cycle_services_each_queue_before_restarting_priority(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = threading.Event()
    calls: list[str] = []

    def operation(name: str, *, stop: bool = False) -> Callable[[Session, Settings], UUID]:
        def process(_db: Session, _settings: Settings) -> UUID:
            calls.append(name)
            if stop:
                stop_event.set()
            return uuid4()

        return process

    testing_session = sessionmaker(
        bind=db_session.get_bind(),
        autocommit=False,
        autoflush=False,
    )
    monkeypatch.setattr(worker, "SessionLocal", testing_session)
    monkeypatch.setattr(
        worker,
        "WORKER_OPERATIONS",
        (
            ("first_queue", operation("first_queue")),
            ("second_queue", operation("second_queue", stop=True)),
        ),
    )

    worker.run_worker(stop_event)

    assert calls == ["first_queue", "second_queue"]


def test_worker_retry_backoff_does_not_poison_sweep_health(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = threading.Event()
    operation_name = "batchdialer_direct_poll"
    register_worker(db_session)
    record_operation_failure(
        db_session,
        service_name=COMMUNICATIONS_WORKER,
        operation_name=operation_name,
        error=TimeoutError("provider timed out"),
        retry_base_seconds=300,
    )

    def operation_must_not_run(_db: Session, _settings: Settings) -> UUID:
        raise AssertionError("operation ran before its retry window")

    testing_session = sessionmaker(
        bind=db_session.get_bind(),
        autocommit=False,
        autoflush=False,
    )
    retry_due = worker.operation_retry_due

    def stop_after_backoff(
        db: Session,
        *,
        service_name: str,
        operation_name: str,
    ) -> bool:
        due = retry_due(
            db,
            service_name=service_name,
            operation_name=operation_name,
        )
        stop_event.set()
        return due

    monkeypatch.setattr(worker, "SessionLocal", testing_session)
    monkeypatch.setattr(
        worker,
        "WORKER_OPERATIONS",
        ((operation_name, operation_must_not_run),),
    )
    monkeypatch.setattr(worker, "operation_retry_due", stop_after_backoff)

    worker.run_worker(stop_event)

    heartbeat = db_session.query(WorkerHeartbeat).one()
    failure = db_session.query(OperationalFailure).one()
    assert heartbeat.status == "healthy"
    assert heartbeat.consecutive_failures == 0
    assert failure.status == "open"
    metrics = (heartbeat.worker_metadata or {})["operation_metrics"]
    assert metrics[operation_name]["last_outcome"] == "backing_off"
