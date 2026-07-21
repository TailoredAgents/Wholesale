from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.services.operations import register_worker


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
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ready", "worker": "not_required"},
    }


def test_ready_requires_worker_heartbeat(
    db_session: Session,
    api_db_override: None,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings.model_validate(
        {"APP_ENV": "local", "WORKER_READINESS_REQUIRED": True}
    )
    try:
        missing = TestClient(app).get("/ready")
        register_worker(db_session)
        available = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert missing.status_code == 503
    assert missing.json()["detail"]["checks"]["worker"] == "missing"
    assert available.status_code == 200
    assert available.json()["checks"]["worker"] == "starting"
