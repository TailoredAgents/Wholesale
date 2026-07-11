from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
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
        organization_name="Georgia Wholesale Operating Company",
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
