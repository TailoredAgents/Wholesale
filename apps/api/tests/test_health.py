import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.routers import health as health_router
from app.services.operations import (
    COMMUNICATIONS_WORKER,
    record_operation_failure,
    record_worker_heartbeat,
    register_worker,
    safe_meta_runtime_metadata,
)


def test_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_checks_database_without_requiring_worker(
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {"APP_ENV": "local", "WORKER_READINESS_REQUIRED": False}
    )
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "ready",
        "checks": {
            "database": "ready",
        },
    }


def test_ready_does_not_gate_api_traffic_on_worker_health(
    db_session: Session,
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {"APP_ENV": "local", "WORKER_READINESS_REQUIRED": True}
    )
    try:
        missing = TestClient(app).get("/ready")
        register_worker(db_session)
        record_worker_heartbeat(db_session, had_error=True)
        degraded = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert missing.status_code == 200
    assert degraded.status_code == 200
    assert degraded.json()["checks"] == {"database": "ready"}


def test_ready_does_not_gate_api_traffic_on_optional_provider_configuration(
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {
            "APP_ENV": "production",
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "",
        }
    )
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ready"}


def test_operational_health_requires_worker_when_configured(
    db_session: Session,
    api_db_override: None,
) -> None:
    runtime_settings = Settings.model_validate(
        {"APP_ENV": "local", "WORKER_READINESS_REQUIRED": True}
    )
    app.dependency_overrides[get_settings] = lambda: runtime_settings
    try:
        missing = TestClient(app).get("/health/operations")
        register_worker(
            db_session,
            runtime_metadata=safe_meta_runtime_metadata(runtime_settings),
        )
        record_worker_heartbeat(db_session)
        available = TestClient(app).get("/health/operations")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert missing.status_code == 503
    missing_payload = missing.json()
    available_payload = available.json()
    assert (
        set(missing_payload)
        == set(available_payload)
        == {
            "status",
            "database",
            "worker",
            "providers",
            "operations",
        }
    )
    assert missing_payload["status"] == "unhealthy"
    assert missing_payload["database"] == {"status": "ready"}
    assert missing_payload["worker"]["status"] == "missing"
    assert missing.headers["cache-control"] == "no-store"
    assert available.status_code == 200
    assert available_payload["status"] == "healthy"
    assert available_payload["database"] == {"status": "ready"}
    assert available.headers["cache-control"] == "no-store"


def test_health_endpoints_return_stable_payloads_when_database_is_unavailable(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_database(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "execute", unavailable_database)

    ready = TestClient(app).get("/ready")
    operational = TestClient(app).get("/health/operations")

    assert ready.status_code == 503
    assert ready.headers["cache-control"] == "no-store"
    assert ready.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }
    assert operational.status_code == 503
    assert operational.headers["cache-control"] == "no-store"
    assert operational.json() == {
        "status": "unhealthy",
        "database": {"status": "unavailable"},
        "worker": {
            "status": "unknown",
            "required": False,
            "heartbeat_at": None,
            "current_operation": None,
            "consecutive_failures": None,
            "open_failure_depth": None,
            "oldest_open_failure_age_seconds": None,
        },
        "providers": [],
        "operations": [],
    }


def test_operational_health_keeps_stable_shape_when_diagnostic_query_fails(
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_diagnostic(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("heartbeat table unavailable")

    monkeypatch.setattr(
        health_router,
        "get_worker_operational_health",
        unavailable_diagnostic,
    )

    response = TestClient(app).get("/health/operations")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "unhealthy",
        "database": {"status": "ready"},
        "worker": {
            "status": "unknown",
            "required": False,
            "heartbeat_at": None,
            "current_operation": None,
            "consecutive_failures": None,
            "open_failure_depth": None,
            "oldest_open_failure_age_seconds": None,
        },
        "providers": [],
        "operations": [],
    }


def test_operational_health_keeps_provider_failure_visible_during_backoff(
    db_session: Session,
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {
            "APP_ENV": "local",
            "WORKER_READINESS_REQUIRED": True,
            "BATCHDIALER_API_KEY": "configured-api-key-value",
        }
    )
    try:
        register_worker(db_session)
        record_operation_failure(
            db_session,
            service_name=COMMUNICATIONS_WORKER,
            operation_name="batchdialer_direct_poll",
            error=TimeoutError("provider timed out"),
        )
        # A later sweep that is merely waiting for next_retry_at is healthy; the
        # open provider incident remains visible in operational health.
        record_worker_heartbeat(db_session, had_error=False)
        response = TestClient(app).get("/health/operations")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == {"status": "ready"}
    assert payload["worker"]["status"] == "healthy"
    assert payload["worker"]["open_failure_depth"] == 1
    batchdialer = next(item for item in payload["providers"] if item["name"] == "batchdialer")
    assert batchdialer["status"] == "degraded"
    assert batchdialer["open_failure_depth"] == 1
    operation = next(
        item for item in payload["operations"] if item["name"] == "batchdialer_direct_poll"
    )
    assert operation["open_failure_depth"] == 1
    assert operation["open_failure_attempts"] == 1
    assert operation["error_types"] == ["TimeoutError"]
    assert operation["oldest_open_failure_age_seconds"] >= 0


def test_operational_health_reports_enabled_provider_configuration_blockers(
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {
            "APP_ENV": "production",
            "WORKER_READINESS_REQUIRED": False,
            "ZAPIER_FACEBOOK_LEADS_ENABLED": True,
            "ZAPIER_FACEBOOK_PAGE_ID": "123456789",
            "ZAPIER_FACEBOOK_ALLOWED_FORM_IDS": "",
        }
    )
    try:
        response = TestClient(app).get("/health/operations")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["database"] == {"status": "ready"}
    zapier = next(item for item in payload["providers"] if item["name"] == "zapier_facebook_leads")
    assert zapier["status"] == "degraded"
    assert zapier["configuration_blockers"] == ["ZAPIER_FACEBOOK_ALLOWED_FORM_IDS"]
