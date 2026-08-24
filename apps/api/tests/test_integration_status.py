from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import BatchDialerCampaign
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def test_integration_status_is_secret_free(
    api_db_override: None,
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
        organization_name="Stonegate",
    )
    db_session.add_all(
        [
            BatchDialerCampaign(
                organization_id=foundation.organization.id,
                provider_campaign_id="house-1",
                name="House campaign",
                status="active",
                is_active=True,
                asset_class="house",
                asset_class_mapped_at=datetime.now(UTC),
                provider_snapshot={},
            ),
            BatchDialerCampaign(
                organization_id=foundation.organization.id,
                provider_campaign_id="unmapped-1",
                name="Unmapped campaign",
                status="active",
                is_active=True,
                provider_snapshot={},
            ),
        ]
    )
    db_session.commit()
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
        "batchdialer",
        "signwell",
        "dealmachine",
        "land-property-research",
    }
    serialized = response.text
    assert "sk-" not in serialized
    assert "AC000" not in serialized
    assert "Bearer " not in serialized
    batchdialer = next(item for item in payload["items"] if item["key"] == "batchdialer")
    assert batchdialer["mode"] == "direct_api"
    assert batchdialer["runtime_status"] in {"not_configured", "not_started"}
    assert batchdialer["last_success_at"] is None
    assert "2 active campaign(s) discovered" in batchdialer["details"]
    assert (
        "1 active campaign(s) have an explicit House or Land mapping"
        in batchdialer["details"]
    )
    assert any(
        detail.startswith("1 active campaign(s) lack an explicit House or Land mapping")
        for detail in batchdialer["details"]
    )
