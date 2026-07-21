from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auth as auth_module
from app.core.config import get_settings
from app.main import app
from app.models.foundation import User
from app.services.bootstrap import bootstrap_foundation


def test_read_me_requires_development_user_header(api_db_override: None) -> None:
    client = TestClient(app)

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing development user header."


def test_read_me_returns_seeded_principal_permissions(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    client = TestClient(app)

    response = client.get("/api/v1/me", headers={"X-Dev-User-Email": "owner@example.com"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "owner@example.com"
    assert "leads:view" in payload["permissions"]
    assert "integrations:manage_credentials" in payload["permissions"]


def test_read_me_rejects_deactivated_user(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    user = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    user.is_active = False
    db_session.commit()

    response = TestClient(app).get(
        "/api/v1/me",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unknown user."


def test_read_me_rejects_development_header_in_production(
    monkeypatch: MonkeyPatch,
    api_db_override: None,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    client = TestClient(app)

    try:
        response = client.get("/api/v1/me", headers={"X-Dev-User-Email": "owner@example.com"})
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token."


def test_read_me_accepts_mapped_clerk_user(
    monkeypatch: MonkeyPatch,
    db_session: Session,
    api_db_override: None,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    user = db_session.scalar(select(User).where(User.email == "owner@example.com"))
    assert user is not None
    user.external_auth_id = "user_clerk_123"
    db_session.commit()

    def fake_verify_clerk_authorization_header(authorization: str) -> auth_module.ClerkClaims:
        assert authorization == "Bearer test-token"
        return auth_module.ClerkClaims(subject="user_clerk_123", email=None)

    monkeypatch.setattr(
        auth_module,
        "verify_clerk_authorization_header",
        fake_verify_clerk_authorization_header,
    )
    client = TestClient(app)

    try:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "owner@example.com"
    assert "leads:view" in payload["permissions"]
