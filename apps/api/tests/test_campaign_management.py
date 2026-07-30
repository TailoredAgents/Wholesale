from datetime import UTC, datetime
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    Prospect,
    ProspectContactPoint,
    ProspectImportRow,
    ProspectSourceMembership,
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


def test_import_cost_and_calling_batch_workflow_without_dnc_evidence_gate(
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
    assert preview["eligible_rows"] == 2
    assert preview["invalid_rows"] == 1
    assert preview["duplicate_rows"] == 1
    assert preview["suppressed_rows"] == 2
    assert preview["review_required_rows"] == 0
    assert {row["status"] for row in preview["rows"]} == {
        "valid",
        "invalid",
        "duplicate",
        "suppressed",
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
        int(db_session.scalar(select(func.count()).select_from(ProspectSuppressionCheck)) or 0) == 4
    )
    prospects = db_session.scalars(select(Prospect).order_by(Prospect.legal_name)).all()
    assert {prospect.call_eligibility for prospect in prospects} == {"eligible", "blocked"}

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
    assert calling_batch["total_entries"] == 2
    assert {entry["legal_name"] for entry in calling_batch["entries"]} == {
        "Eligible Owner",
        "Review Owner",
    }
    assert {entry["call_eligibility"] for entry in calling_batch["entries"]} == {"eligible"}

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


def test_propstream_refresh_preserves_history_and_cohort_lineage(
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
    va = create_user(client, headers)
    campaign = create_campaign(client, headers)
    cohort_response = client.post(
        "/api/v1/campaign-management/cohorts",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "name": "Atlanta PropStream Power Cohort",
            "code": "atl-propstream-power-refresh",
            "source_name": "PropStream",
            "list_type": "absentee_high_equity",
            "market_label": "Atlanta Metro",
            "dialer_mode": "one_line_power",
            "call_window_start_hour": 9,
            "call_window_end_hour": 17,
            "timezone": "America/New_York",
            "starts_on": "2026-07-30",
        },
    )
    assert cohort_response.status_code == 201, cohort_response.text
    cohort = cohort_response.json()
    preset_response = client.post(
        "/api/v1/campaign-management/import-mappings/propstream-preset",
        headers=headers,
    )
    assert preset_response.status_code == 201, preset_response.text
    preset = preset_response.json()
    assert preset["source_name"] == "PropStream"

    csv_header = (
        "Property ID,Owner 1 First Name,Owner 1 Last Name,Phone 1,Phone 2,Phone 3,"
        "Email 1,Email 2,Email 3,Property Address,Property City,Property State,"
        "Property Zip\n"
    )
    first_csv = csv_header + (
        "PS-100,Avery,Seller,4045550101,4045550102,4045550103,"
        "avery@example.com,avery.work@example.com,,100 Oak St,Atlanta,GA,30303\n"
    )
    base_payload = {
        "campaign_id": campaign["id"],
        "mapping_id": preset["id"],
        "cohort_id": cohort["id"],
        "default_assignee_user_id": va["id"],
        "source_profile": "propstream",
        "source_export_id": "export-001",
        "source_list_id": "list-absentee-atl",
        "source_list_name": "Atlanta absentee high equity",
        "source_exported_at": "2026-07-30T13:00:00Z",
        "source_filters": {
            "county": "Fulton",
            "minimum_equity_percent": "40",
            "occupancy": "absentee",
        },
    }
    first_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=headers,
        json={
            **base_payload,
            "file_name": "propstream-atlanta-001.csv",
            "csv_content": first_csv,
        },
    )
    assert first_response.status_code == 201, first_response.text
    assert first_response.json()["imported_rows"] == 1
    assert first_response.json()["matched_existing_rows"] == 0

    prospect = db_session.scalar(select(Prospect).where(Prospect.source_record_key == "PS-100"))
    assert prospect is not None
    original_phone = prospect.phone
    contacted_at = datetime.now(UTC)
    prospect.status = "contacted"
    prospect.last_contacted_at = contacted_at
    db_session.commit()

    second_csv = csv_header + (
        "PS-100,Avery,Seller,4045550101,4045550102,4045550199,"
        "avery@example.com,avery.work@example.com,avery.new@example.com,"
        "100 Oak St,Atlanta,GA,30303\n"
    )
    refresh_payload = {
        **base_payload,
        "source_export_id": "export-002",
        "source_exported_at": "2026-07-31T13:00:00Z",
        "file_name": "propstream-atlanta-002.csv",
        "csv_content": second_csv,
    }
    preview_response = client.post(
        "/api/v1/campaign-management/imports/validate",
        headers=headers,
        json=refresh_payload,
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_row = preview_response.json()["rows"][0]
    assert preview_row["status"] == "duplicate"
    assert preview_row["relationship_state"] == "prior_contact"
    assert preview_row["contact_point_count"] == 6

    refresh_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=headers,
        json=refresh_payload,
    )
    assert refresh_response.status_code == 201, refresh_response.text
    refreshed = refresh_response.json()
    assert refreshed["imported_rows"] == 0
    assert refreshed["matched_existing_rows"] == 1
    assert refreshed["rows"][0]["status"] == "matched_existing"

    db_session.refresh(prospect)
    assert prospect.status == "contacted"
    assert prospect.last_contacted_at == contacted_at.replace(tzinfo=None)
    assert prospect.phone == original_phone
    membership = db_session.scalar(
        select(ProspectSourceMembership).where(
            ProspectSourceMembership.prospect_id == prospect.id
        )
    )
    assert membership is not None
    assert membership.appearance_count == 2
    assert str(membership.latest_import_batch_id) == refreshed["id"]
    assert membership.relationship_state_at_latest_import == "prior_contact"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ProspectContactPoint)
            .where(ProspectContactPoint.prospect_id == prospect.id)
        )
        == 7
    )

    calling_batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "import_batch_id": refreshed["id"],
            "cohort_id": cohort["id"],
            "dialer_mode": "one_line_power",
            "assigned_user_id": va["id"],
            "name": "Refreshed PropStream cohort",
            "maximum_records": 25,
        },
    )
    assert calling_batch_response.status_code == 201, calling_batch_response.text
    assert [entry["prospect_id"] for entry in calling_batch_response.json()["entries"]] == [
        str(prospect.id)
    ]

    replay_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=headers,
        json=refresh_payload,
    )
    assert replay_response.status_code == 422


def test_prospecting_cohort_and_work_session_measurement_contract(
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
    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    va = create_user(client, owner_headers)
    campaign = create_campaign(client, owner_headers)

    cohort_response = client.post(
        "/api/v1/campaign-management/cohorts",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "name": "Atlanta Absentee Power Pilot",
            "code": "atl-absentee-power-2026-07",
            "source_name": "PropStream",
            "list_type": "absentee_high_equity",
            "market_label": "Atlanta Metro",
            "dialer_mode": "one_line_power",
            "call_window_start_hour": 9,
            "call_window_end_hour": 17,
            "timezone": "America/New_York",
            "starts_on": "2026-07-30",
            "cohort_metadata": {
                "county": "Fulton",
                "minimum_equity_percent": 40,
            },
        },
    )
    assert cohort_response.status_code == 201, cohort_response.text
    cohort = cohort_response.json()
    assert cohort["dialer_mode"] == "one_line_power"
    assert cohort["source_name"] == "PropStream"

    session_response = client.post(
        "/api/v1/campaign-management/work-sessions",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "cohort_id": cohort["id"],
            "caller_user_id": va["id"],
            "work_date": "2026-07-30",
            "paid_minutes": 120,
            "productive_calling_minutes": 90,
            "hourly_rate_cents": 800,
            "source": "manual",
        },
    )
    assert session_response.status_code == 201, session_response.text
    session = session_response.json()
    assert session["labor_cost_cents"] == 1600
    assert session["utilization_rate_basis_points"] == 7500

    overview_response = client.get("/api/v1/campaign-management", headers=owner_headers)
    assert overview_response.status_code == 200, overview_response.text
    overview = overview_response.json()
    assert overview["cohorts"][0]["id"] == cohort["id"]
    assert overview["work_sessions"][0]["id"] == session["id"]
    assert overview["costs"][0]["cohort_id"] == cohort["id"]
    assert overview["quality"][0]["actual_cost_cents"] == 1600
    assert overview["quality"][0]["accepted_warm_leads"] == 0
    assert overview["quality"][0]["cost_per_accepted_warm_lead_cents"] is None

    invalid_time = client.post(
        "/api/v1/campaign-management/work-sessions",
        headers=owner_headers,
        json={
            "campaign_id": campaign["id"],
            "cohort_id": cohort["id"],
            "caller_user_id": va["id"],
            "work_date": "2026-07-30",
            "paid_minutes": 30,
            "productive_calling_minutes": 45,
            "hourly_rate_cents": 800,
        },
    )
    assert invalid_time.status_code == 422
    assert (
        client.post(
            "/api/v1/campaign-management/cohorts",
            headers=va_headers,
            json={
                "campaign_id": campaign["id"],
                "name": "Unauthorized",
                "code": "unauthorized-cohort",
                "source_name": "PropStream",
                "list_type": "test",
                "market_label": "Atlanta",
                "dialer_mode": "multi_line_parallel",
                "call_window_start_hour": 9,
                "call_window_end_hour": 17,
                "timezone": "America/New_York",
                "starts_on": "2026-07-30",
            },
        ).status_code
        == 403
    )


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
