from datetime import UTC, datetime
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    Prospect,
    ProspectImportRow,
    ProspectSuppressionCheck,
    SuppressionRecord,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "caller@example.com"


def create_user(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": VA_EMAIL,
            "display_name": "Campaign Caller",
            "role_key": "prospecting_caller",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def create_campaign(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    market_response = client.post(
        "/api/v1/operations/markets",
        headers=headers,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-metro",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    response = client.post(
        "/api/v1/operations/campaigns",
        headers=headers,
        json={
            "market_id": market_response.json()["id"],
            "name": "Atlanta Owner List",
            "code": "atlanta-owner-list",
            "channel": "cold_call",
            "budget_cents": 500000,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_phase_three_import_screening_cost_and_calling_batch_workflow(
    db_session: Session,
    api_db_override: None,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    va = create_user(client, owner_headers)
    campaign = create_campaign(client, owner_headers)

    db_session.add(
        SuppressionRecord(
            organization_id=foundation.organization.id,
            contact_id=None,
            channel="phone",
            normalized_address="+14045550144",
            status="active",
            reason="Company-specific do not call request",
            source="manual",
            provider=None,
            external_event_id=None,
            suppressed_at=datetime.now(UTC),
            lifted_at=None,
            suppression_metadata={"test": True},
        )
    )
    db_session.commit()

    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=owner_headers,
        json={
            "name": "Owner List Standard",
            "source_name": "Test Data Vendor",
            "field_mapping": {
                "source_record_key": "Record ID",
                "legal_name": "Owner",
                "phone": "Phone",
                "email": "Email",
                "street_address": "Property Address",
                "city": "City",
                "state_code": "State",
                "postal_code": "ZIP",
                "dnc_status": "DNC",
            },
            "default_values": {},
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    mapping = cast(dict[str, Any], mapping_response.json())

    csv_content = """Record ID,Owner,Phone,Email,Property Address,City,State,ZIP,DNC
1,Eligible Owner,(404) 555-0101,,101 Main St,Atlanta,GA,30303,No
2,DNC Owner,404-555-0102,,102 Main St,Atlanta,GA,30303,Yes
3,Review Owner,404-555-0103,,103 Main St,Atlanta,GA,30303,
4,Bad Data,12,,104 Main St,Atlanta,GA,30303,No
5,Duplicate Owner,(404) 555-0101,,105 Main St,Atlanta,GA,30303,No
6,Company Suppressed,404-555-0144,,106 Main St,Atlanta,GA,30303,No
"""
    import_payload = {
        "campaign_id": campaign["id"],
        "mapping_id": mapping["id"],
        "default_assignee_user_id": va["id"],
        "file_name": "atlanta-owner-list.csv",
        "csv_content": csv_content,
    }
    preview_response = client.post(
        "/api/v1/campaign-management/imports/validate",
        headers=owner_headers,
        json=import_payload,
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["total_rows"] == 6
    assert preview["valid_rows"] == 4
    assert preview["eligible_rows"] == 1
    assert preview["invalid_rows"] == 1
    assert preview["duplicate_rows"] == 1
    assert preview["suppressed_rows"] == 2
    assert preview["review_required_rows"] == 1
    assert {row["status"] for row in preview["rows"]} == {
        "valid",
        "invalid",
        "duplicate",
        "suppressed",
        "review_required",
    }

    import_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=owner_headers,
        json=import_payload,
    )
    assert import_response.status_code == 201, import_response.text
    imported = import_response.json()
    assert imported["status"] == "complete"
    assert imported["imported_rows"] == 4
    assert len(imported["rows"]) == 6
    assert int(db_session.scalar(select(func.count()).select_from(Prospect)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(ProspectImportRow)) or 0) == 6
    assert (
        int(db_session.scalar(select(func.count()).select_from(ProspectSuppressionCheck)) or 0) == 8
    )
    prospects = db_session.scalars(select(Prospect).order_by(Prospect.legal_name)).all()
    assert {prospect.call_eligibility for prospect in prospects} == {
        "eligible",
        "blocked",
        "review_required",
    }

    repeat_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=owner_headers,
        json=import_payload,
    )
    assert repeat_response.status_code == 422

    list_cost_response = client.post(
        "/api/v1/campaign-management/costs",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "import_batch_id": imported["id"],
            "category": "list_purchase",
            "vendor_name": "Test Data Vendor",
            "amount_cents": 10000,
            "incurred_on": "2026-07-21",
        },
    )
    assert list_cost_response.status_code == 201, list_cost_response.text
    labor_response = client.post(
        "/api/v1/campaign-management/costs",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "worker_user_id": va["id"],
            "category": "va_labor",
            "amount_cents": 700,
            "labor_minutes": 60,
            "hourly_rate_cents": 700,
            "incurred_on": "2026-07-21",
        },
    )
    assert labor_response.status_code == 201, labor_response.text

    calling_batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "import_batch_id": imported["id"],
            "assigned_user_id": va["id"],
            "name": "Atlanta Batch 1",
            "maximum_records": 100,
        },
    )
    assert calling_batch_response.status_code == 201, calling_batch_response.text
    calling_batch = calling_batch_response.json()
    assert calling_batch["status"] == "ready"
    assert calling_batch["total_entries"] == 1
    assert calling_batch["entries"][0]["legal_name"] == "Eligible Owner"
    assert calling_batch["entries"][0]["call_eligibility"] == "eligible"

    review_prospect = next(
        prospect for prospect in prospects if prospect.call_eligibility == "review_required"
    )
    screening_response = client.post(
        f"/api/v1/campaign-management/prospects/{review_prospect.id}/screening",
        headers=owner_headers,
        json={
            "dnc_status": "clear",
            "source": "Test DNC Provider",
            "evidence_reference": "screening-report-2026-07-21.csv",
            "notes": "Manager reviewed the retained provider export.",
        },
    )
    assert screening_response.status_code == 200, screening_response.text
    assert screening_response.json()["call_eligibility"] == "eligible"
    second_batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "import_batch_id": imported["id"],
            "assigned_user_id": va["id"],
            "name": "Atlanta Batch 2",
            "maximum_records": 100,
        },
    )
    assert second_batch_response.status_code == 201, second_batch_response.text
    assert second_batch_response.json()["total_entries"] == 1
    assert second_batch_response.json()["entries"][0]["legal_name"] == "Review Owner"

    overview_response = client.get("/api/v1/campaign-management", headers=owner_headers)
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    quality = overview["quality"][0]
    assert quality["actual_cost_cents"] == 10700
    assert quality["imported_prospects"] == 4
    assert quality["callable_prospects"] == 2
    assert quality["blocked_prospects"] == 2
    assert quality["review_required_prospects"] == 0
    assert quality["bad_data_rate_basis_points"] == 1667
    assert quality["duplicate_rate_basis_points"] == 1667
    assert quality["cost_per_imported_prospect_cents"] == 2675
    assert quality["cost_per_callable_prospect_cents"] == 5350

    restricted_response = client.get("/api/v1/campaign-management", headers=va_headers)
    assert restricted_response.status_code == 403
    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert {
        "campaign_management.import_mapping_create",
        "campaign_management.prospect_import_complete",
        "campaign_management.cost_create",
        "campaign_management.calling_batch_create",
        "campaign_management.screening_decision",
    } <= actions


def test_import_mapping_rejects_missing_required_contact_mapping(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    response = TestClient(app).post(
        "/api/v1/campaign-management/import-mappings",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Invalid Mapping",
            "field_mapping": {"legal_name": "Owner", "city": "City"},
        },
    )
    assert response.status_code == 422


def test_import_rejects_missing_mapped_headers(
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
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    campaign = create_campaign(client, headers)
    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=headers,
        json={
            "name": "Required Headers",
            "field_mapping": {"legal_name": "Owner", "phone": "Phone"},
        },
    )
    response = client.post(
        "/api/v1/campaign-management/imports/validate",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "mapping_id": mapping_response.json()["id"],
            "file_name": "missing.csv",
            "csv_content": "Owner,Telephone\nSeller,4045550199\n",
        },
    )
    assert response.status_code == 422
    assert "Phone" in response.json()["detail"]
