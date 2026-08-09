from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def test_integration_status_is_secret_free(
    api_db_override: None,
    db_session: Session,
) -> None:
    bootstrap_foundation(
        db_session,
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
        organization_name="Stonegate",
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/integrations/status",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["key"] for item in payload["items"]} >= {
        "openai",
        "resend",
        "twilio-sms",
        "twilio-voice",
        "signwell",
        "dealmachine",
        "land-property-research",
    }
    serialized = response.text
    assert "sk-" not in serialized
    assert "AC000" not in serialized
    assert "Bearer " not in serialized
