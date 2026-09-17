import asyncio
from itertools import count
from time import perf_counter
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool, StaticPool
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.config import Settings, get_settings
from app.core.observability import RequestObservabilityMiddleware, database_pool_snapshot
from app.main import app


class CapturingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **values: Any) -> None:
        self.events.append((event, values))


class FailingLogger:
    def info(self, _event: str, **_values: Any) -> None:
        raise RuntimeError("logging unavailable")


def _observability_events(logger: CapturingLogger) -> list[dict[str, Any]]:
    return [values for event, values in logger.events if event == "api_request_completed"]


def test_request_observability_records_route_payload_and_sql_metrics(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)
    monkeypatch.setattr(observability, "HEALTHY_REQUEST_SAMPLE_EVERY", 1)
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {"APP_ENV": "local", "WORKER_READINESS_REQUIRED": False}
    )
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    [event] = _observability_events(logger)
    assert event["method"] == "GET"
    assert event["route"] == "/ready"
    assert event["status_code"] == 200
    assert event["duration_ms"] >= 0
    assert event["request_content_length_bytes"] == 0
    assert event["request_body_bytes_read"] == 0
    assert event["response_body_bytes"] == len(response.content)
    assert event["db_query_count"] >= 1
    assert event["db_query_time_ms"] >= 0
    assert event["db_max_query_time_ms"] >= 0
    assert event["db_pool_class"] == "StaticPool"
    assert event["performance_flags"] == ()
    assert event["error_type"] is None

    # The SQL listener is request-scoped; unrelated database work is not
    # accidentally carried into later request metrics.
    db_session.execute(text("select 1"))
    response = TestClient(app).get("/missing/123456789")
    assert response.status_code == 404
    assert _observability_events(logger)[-1]["route"] == "__unmatched__"
    assert _observability_events(logger)[-1]["db_query_count"] == 0


def test_request_observability_suppresses_healthy_liveness_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)
    monkeypatch.setattr(observability, "HEALTHY_REQUEST_SAMPLE_EVERY", 1)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert _observability_events(logger) == []


def test_request_observability_failure_does_not_change_api_response(
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import observability

    monkeypatch.setattr(observability, "logger", FailingLogger())

    response = TestClient(app).get("/ready")
    diagnostic = TestClient(app).get("/health/database-observability")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert diagnostic.status_code == 200


def test_request_observability_stops_at_final_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import observability

    logger = CapturingLogger()
    monkeypatch.setattr(observability, "logger", logger)
    monkeypatch.setattr(observability, "HEALTHY_REQUEST_SAMPLE_EVERY", 1)
    local_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def post_response_work() -> None:
        await asyncio.sleep(0.08)
        with local_engine.connect() as connection:
            connection.execute(text("select 1"))

    async def probe(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok", background=BackgroundTask(post_response_work))

    local_app = Starlette(routes=[Route("/probe", probe)])
    observed_app = RequestObservabilityMiddleware(local_app, database_engine=local_engine)
    started_at = perf_counter()
    try:
        response = TestClient(observed_app).get("/probe")
    finally:
        local_engine.dispose()
    wall_time_ms = (perf_counter() - started_at) * 1_000

    assert response.status_code == 200
    [event] = _observability_events(logger)
    assert event["db_query_count"] == 0
    assert wall_time_ms - event["duration_ms"] >= 40


def test_request_observability_samples_ordinary_successes_but_never_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import observability

    monkeypatch.setattr(observability, "HEALTHY_REQUEST_SAMPLE_EVERY", 20)
    monkeypatch.setattr(observability, "_healthy_request_counter", count(1))

    assert not observability._should_log_request(
        route_template="/api/v1/leads",
        status_code=200,
        performance_flags=(),
    )
    assert observability._should_log_request(
        route_template="/api/v1/leads",
        status_code=500,
        performance_flags=(),
    )
    assert observability._should_log_request(
        route_template="/api/v1/leads",
        status_code=200,
        performance_flags=("slow_request",),
    )
    assert observability._should_log_request(
        route_template="/api/v1/leads",
        status_code=200,
        performance_flags=(),
        error_type="RuntimeError",
    )


def test_database_pool_snapshot_reports_queue_pool_capacity() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=3,
    )
    try:
        snapshot = database_pool_snapshot(engine)
    finally:
        engine.dispose()

    assert snapshot.pool_class == "QueuePool"
    assert snapshot.size == 2
    assert snapshot.checked_in == 0
    assert snapshot.checked_out == 0
    assert snapshot.overflow == -2
