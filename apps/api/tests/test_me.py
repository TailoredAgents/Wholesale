from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import auth as auth_module
from app.core.config import get_settings
from app.main import app
from app.models.foundation import Organization, Role, RoleAssignment, User
from app.services.bootstrap import bootstrap_foundation


def test_read_me_requires_development_user_header(api_db_override: None) -> None:
    response = TestClient(app).get("/api/v1/me")

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

    response = TestClient(app).get(
        "/api/v1/me",
        headers={"X-Dev-User-Email": "owner@example.com"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "owner@example.com"
    assert payload["display_name"] == "Owner"
    assert "owner" in payload["role_keys"]
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

    try:
        response = TestClient(app).get(
            "/api/v1/me",
            headers={"X-Dev-User-Email": "owner@example.com"},
        )
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

    try:
        response = TestClient(app).get(
            "/api/v1/me",
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"] == "owner@example.com"
    assert "leads:view" in payload["permissions"]


def create_role_user(
    db: Session,
    organization: Organization,
    *,
    email: str,
    display_name: str,
    role_key: str,
) -> User:
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=display_name,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return user


def test_workspace_profile_is_available_to_non_acquisition_roles(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    finance_user = create_role_user(
        db_session,
        foundation.organization,
        email="finance@example.com",
        display_name="Finance Lead",
        role_key="finance_accounting",
    )

    response = TestClient(app).get(
        "/api/v1/me",
        headers={"X-Dev-User-Email": finance_user.email},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(finance_user.id),
        "organization_id": str(foundation.organization.id),
        "email": finance_user.email,
        "display_name": "Finance Lead",
        "role_keys": ["finance_accounting"],
        "permissions": [
            "compensation:change_rules",
            "compensation:view",
            "financials:view",
        ],
        "unread_notification_count": 0,
    }


def test_marketing_role_can_open_marketing_workspace(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    marketing_user = create_role_user(
        db_session,
        foundation.organization,
        email="marketing@example.com",
        display_name="Marketing Lead",
        role_key="marketing_manager",
    )

    response = TestClient(app).get(
        "/api/v1/marketing",
        headers={"X-Dev-User-Email": marketing_user.email},
    )

    assert response.status_code == 200
