import threading
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.core.config import Settings
from app.services.batchdialer_call_facts import (
    backfill_next_batchdialer_call_fact_batch,
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
