from typing import Any, cast
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import AuditEvent, Prospect
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "caller@example.com"


def test_market_campaign_and_prospect_foundation_is_scoped_and_audited(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}

    va_response = client.post(
        "/api/v1/operations/users",
        headers=owner_headers,
        json={
            "email": VA_EMAIL,
            "display_name": "VA Caller",
            "role_key": "prospecting_caller",
        },
    )
    assert va_response.status_code == 201, va_response.text
    va = cast(dict[str, Any], va_response.json())

    market_response = client.post(
        "/api/v1/operations/markets",
        headers=owner_headers,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-metro",
            "state_code": "ga",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    market = cast(dict[str, Any], market_response.json())
    assert market["state_code"] == "GA"
    assert market["is_primary"] is True

    territory_response = client.post(
        "/api/v1/operations/territories",
        headers=owner_headers,
        json={
            "market_id": market["id"],
            "name": "North Atlanta",
            "code": "north-atlanta",
            "county_names": ["Gwinnett", "Forsyth", "Gwinnett"],
            "postal_codes": ["30024", "30518", "30024"],
        },
    )
    assert territory_response.status_code == 201, territory_response.text
    territory = cast(dict[str, Any], territory_response.json())
    assert territory["county_names"] == ["Gwinnett", "Forsyth"]
    assert territory["postal_codes"] == ["30024", "30518"]

    campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market["id"],
            "territory_id": territory["id"],
            "owner_user_id": va["id"],
            "name": "North Atlanta Absentee Owners",
            "code": "atl-absentee-2026-07",
            "channel": "cold_call",
            "starts_on": "2026-07-22",
            "budget_cents": 250000,
        },
    )
    assert campaign_response.status_code == 201, campaign_response.text
    campaign = cast(dict[str, Any], campaign_response.json())
    assert campaign["status"] == "draft"
    assert campaign["prospect_count"] == 0

    prospect_response = client.post(
        "/api/v1/operations/prospects",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "assigned_user_id": va["id"],
            "source_record_key": "vendor-row-1001",
            "legal_name": "Example Property Owner",
            "phone": "(404) 555-0199",
            "email": "Owner@Example.test",
            "street_address": "123 Peachtree Street",
            "city": "Atlanta",
            "state_code": "ga",
            "postal_code": "30303",
            "source_payload": {"vendor": "test-fixture"},
        },
    )
    assert prospect_response.status_code == 201, prospect_response.text
    prospect_payload = cast(dict[str, Any], prospect_response.json())
    assert prospect_payload["status"] == "new"
    assert prospect_payload["suppression_status"] == "pending"
    assert prospect_payload["converted_lead_id"] is None

    prospect = db_session.get(Prospect, UUID(prospect_payload["id"]))
    assert prospect is not None
    assert prospect.normalized_phone == "14045550199"
    assert prospect.normalized_email == "owner@example.test"
    assert prospect.normalized_address_key == "123 peachtree st|atlanta|GA|30303"

    duplicate_response = client.post(
        "/api/v1/operations/prospects",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "source_record_key": "vendor-row-1001",
            "legal_name": "Duplicate Source Row",
            "phone": "404-555-0198",
        },
    )
    assert duplicate_response.status_code == 422

    overview_response = client.get("/api/v1/operations", headers=owner_headers)
    assert overview_response.status_code == 200, overview_response.text
    overview = cast(dict[str, Any], overview_response.json())
    assert overview["markets"][0]["prospect_count"] == 1
    assert overview["territories"][0]["prospect_count"] == 1
    assert overview["campaigns"][0]["prospect_count"] == 1
    assert len(overview["prospects"]) == 1

    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    va_overview_response = client.get("/api/v1/operations", headers=va_headers)
    assert va_overview_response.status_code == 200, va_overview_response.text
    assert va_overview_response.json()["markets"] == []
    assert va_overview_response.json()["prospects"] == []
    forbidden_response = client.post(
        "/api/v1/operations/markets",
        headers=va_headers,
        json={
            "name": "Unauthorized",
            "code": "unauthorized",
            "state_code": "GA",
            "timezone": "America/New_York",
        },
    )
    assert forbidden_response.status_code == 403

    actions = set(
        db_session.scalars(
            select(AuditEvent.action).where(
                AuditEvent.action.in_(
                    ("market.create", "territory.create", "campaign.create", "prospect.create")
                )
            )
        )
    )
    assert actions == {
        "market.create",
        "territory.create",
        "campaign.create",
        "prospect.create",
    }
    assert db_session.scalar(select(func.count()).select_from(Prospect)) == 1
