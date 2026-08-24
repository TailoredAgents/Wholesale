from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import Lead, Property, Prospect, ProspectingScriptVersion
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "land-va@example.com"
ACQUISITIONS_EMAIL = "land-acquisitions@example.com"


def create_user(
    client: TestClient,
    headers: dict[str, str],
    *,
    email: str,
    display_name: str,
    role_key: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": email,
            "display_name": display_name,
            "role_key": role_key,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def create_script(
    client: TestClient,
    headers: dict[str, str],
    *,
    asset_class: str,
    title: str,
) -> dict[str, Any]:
    qualification_questions: list[dict[str, object]] = [
        {
            "key": "motivation",
            "label": "Reason for selling",
            "prompt": "What has you considering selling the property?",
            "required_for_handoff": True,
        }
    ]
    if asset_class == "land":
        qualification_questions.extend(
            [
                {
                    "key": "parcel_id",
                    "label": "Parcel / APN",
                    "prompt": "What is the parcel number?",
                    "required_for_handoff": False,
                },
                {
                    "key": "access_frontage",
                    "label": "Access and frontage",
                    "prompt": "What access or road frontage does the seller report?",
                    "required_for_handoff": False,
                },
            ]
        )
    response = client.post(
        "/api/v1/prospecting/scripts",
        headers=headers,
        json={
            "asset_class": asset_class,
            "title": title,
            "opening_script": (
                "Hi, this is Stonegate. I am calling about your property and wanted "
                "to ask whether you would consider an offer."
            ),
            "qualification_questions": qualification_questions,
        },
    )
    assert response.status_code == 201, response.text
    script = cast(dict[str, Any], response.json())
    approval = client.post(
        f"/api/v1/prospecting/scripts/{script['id']}/approve",
        headers=headers,
    )
    assert approval.status_code == 200, approval.text
    return cast(dict[str, Any], approval.json())


def test_land_campaign_import_script_isolation_and_warm_handoff(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "property_intelligence_auto_research_enabled", False)
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    va = create_user(
        client,
        owner_headers,
        email=VA_EMAIL,
        display_name="Land VA",
        role_key="prospecting_caller",
    )
    acquisitions = create_user(
        client,
        owner_headers,
        email=ACQUISITIONS_EMAIL,
        display_name="Land Acquisitions",
        role_key="acquisition_rep",
    )

    market_response = client.post(
        "/api/v1/operations/markets",
        headers=owner_headers,
        json={
            "name": "Georgia Land",
            "code": "georgia-land",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    market_id = market_response.json()["id"]
    missing_asset_campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_id,
            "name": "House Owners",
            "code": "house-owners",
            "channel": "cold_call",
        },
    )
    assert missing_asset_campaign_response.status_code == 422
    house_campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_id,
            "name": "House Owners",
            "code": "house-owners",
            "channel": "cold_call",
            "asset_class": "house",
        },
    )
    assert house_campaign_response.status_code == 201, house_campaign_response.text
    assert house_campaign_response.json()["asset_class"] == "house"
    land_campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_id,
            "name": "Vacant Land Owners",
            "code": "vacant-land-owners",
            "channel": "cold_call",
            "asset_class": "land",
        },
    )
    assert land_campaign_response.status_code == 201, land_campaign_response.text
    land_campaign = cast(dict[str, Any], land_campaign_response.json())
    assert land_campaign["asset_class"] == "land"
    invalid_campaign = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_id,
            "name": "Invalid Asset",
            "code": "invalid-asset",
            "channel": "cold_call",
            "asset_class": "commercial",
        },
    )
    assert invalid_campaign.status_code == 422

    house_prospect_response = client.post(
        "/api/v1/operations/prospects",
        headers=owner_headers,
        json={
            "campaign_id": house_campaign_response.json()["id"],
            "source_record_key": "HOUSE-1",
            "legal_name": "Pat Parcel",
            "phone": "4045550161",
            "street_address": "45 Rural Rd",
            "city": "Macon",
            "state_code": "GA",
            "postal_code": "31201",
        },
    )
    assert house_prospect_response.status_code == 201, house_prospect_response.text
    assert house_prospect_response.json()["asset_class"] == "house"

    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=owner_headers,
        json={
            "name": "Land Parcel Import",
            "field_mapping": {
                "source_record_key": "ID",
                "legal_name": "Owner",
                "phone": "Phone",
                "street_address": "Address",
                "city": "City",
                "state_code": "State",
                "postal_code": "ZIP",
                "county": "County",
                "parcel_id": "APN",
            },
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    import_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=owner_headers,
        json={
            "campaign_id": land_campaign["id"],
            "mapping_id": mapping_response.json()["id"],
            "default_assignee_user_id": va["id"],
            "file_name": "land-parcels.csv",
            "csv_content": (
                "ID,Owner,Phone,Address,City,State,ZIP,County,APN\n"
                "LAND-1,Pat Parcel,4045550161,,,GA,,Pickens County,APN-45-100\n"
            ),
        },
    )
    assert import_response.status_code == 201, import_response.text
    assert import_response.json()["imported_rows"] == 1
    assert import_response.json()["duplicate_rows"] == 0
    assert import_response.json()["rows"][0]["property_address"] == (
        "APN APN-45-100, Pickens County, GA"
    )
    prospect = db_session.scalar(select(Prospect).where(Prospect.source_record_key == "LAND-1"))
    assert prospect is not None
    assert prospect.asset_class == "land"
    assert prospect.source_payload == {
        "ID": "LAND-1",
        "Owner": "Pat Parcel",
        "Phone": "4045550161",
        "Address": "",
        "City": "",
        "State": "GA",
        "ZIP": "",
        "County": "Pickens County",
        "APN": "APN-45-100",
        "_stonegate_property": {
            "county": "Pickens County",
            "parcel_id": "APN-45-100",
        },
    }
    operations = client.get("/api/v1/operations", headers=owner_headers)
    assert operations.status_code == 200, operations.text
    imported_read = next(
        item for item in operations.json()["prospects"] if item["id"] == str(prospect.id)
    )
    assert imported_read["asset_class"] == "land"
    assert imported_read["parcel_id"] == "APN-45-100"
    assert imported_read["county"] == "Pickens County"
    assert imported_read["property_address"] == "APN APN-45-100, Pickens County, GA"

    house_script = create_script(
        client,
        owner_headers,
        asset_class="house",
        title="House Owner Conversation",
    )
    land_script = create_script(
        client,
        owner_headers,
        asset_class="land",
        title="Land Owner Conversation",
    )
    db_session.expire_all()
    approved_scripts = db_session.scalars(
        select(ProspectingScriptVersion).where(ProspectingScriptVersion.status == "approved")
    ).all()
    assert {script.asset_class for script in approved_scripts} == {"house", "land"}
    assert house_script["asset_class"] == "house"
    assert land_script["asset_class"] == "land"

    mismatched_cohort = client.post(
        "/api/v1/campaign-management/cohorts",
        headers=owner_headers,
        json={
            "campaign_id": land_campaign["id"],
            "script_version_id": house_script["id"],
            "name": "Mismatched Land Cohort",
            "code": "mismatched-land",
            "source_name": "VA list",
            "list_type": "vacant_land",
            "market_label": "Georgia",
            "dialer_mode": "one_line_power",
            "call_window_start_hour": 9,
            "call_window_end_hour": 17,
            "timezone": "America/New_York",
            "starts_on": "2026-08-08",
        },
    )
    assert mismatched_cohort.status_code == 422
    assert "match the campaign asset class" in mismatched_cohort.json()["detail"]

    batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": land_campaign["id"],
            "import_batch_id": import_response.json()["id"],
            "assigned_user_id": va["id"],
            "name": "Land VA Queue",
            "maximum_records": 10,
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    entry = batch_response.json()["entries"][0]
    assert entry["property_address"] == "APN APN-45-100, Pickens County, GA"
    pre_handoff_workbench = client.get("/api/v1/prospecting", headers=owner_headers)
    assert pre_handoff_workbench.status_code == 200, pre_handoff_workbench.text
    copilot_item = next(
        item
        for item in pre_handoff_workbench.json()["copilot"]["work_items"]
        if item["prospect_id"] == str(prospect.id)
    )
    assert copilot_item["property_address"] == "APN APN-45-100, Pickens County, GA"
    assert "Property address is incomplete." not in copilot_item["data_quality_warnings"]
    start_response = client.post(
        f"/api/v1/prospecting/entries/{entry['id']}/start",
        headers=va_headers,
    )
    assert start_response.status_code == 200, start_response.text
    assert start_response.json()["asset_class"] == "land"
    assert start_response.json()["property_address"] == (
        "APN APN-45-100, Pickens County, GA"
    )
    assert start_response.json()["active_attempt"]["script_version_id"] == land_script["id"]
    assert start_response.json()["script"]["id"] == land_script["id"]
    assert (
        start_response.json()["active_attempt"]["qualification_checklist"][
            "script_version_id"
        ]
        == land_script["id"]
    )

    complete_response = client.post(
        (
            "/api/v1/prospecting/attempts/"
            f"{start_response.json()['active_attempt']['id']}/complete"
        ),
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "No longer needs the parcel",
                "parcel_id": "APN-45-100",
                "access_frontage": "Seller reports county-road frontage",
            },
        },
    )
    assert complete_response.status_code == 200, complete_response.text
    db_session.expire_all()
    lead = db_session.scalar(select(Lead).where(Lead.asset_class == "land"))
    assert lead is not None
    property_record = db_session.get(Property, lead.property_id)
    assert property_record is not None
    assert property_record.parcel_id == "APN-45-100"
    assert property_record.county == "Pickens County"
    assert property_record.normalized_address_key is None
    assert property_record.normalized_parcel_key == "GA|pickens|APN45100"
    assert property_record.property_type == "land"
    assert "parcel_id" not in lead.qualification_context
    prospecting_profile = lead.qualification_context["land_acquisition_v1"]
    assert prospecting_profile["facts"]["access_frontage"] == {
        "value": "Seller reports county-road frontage",
        "source_type": "seller_reported",
        "source_name": "prospecting_qualification",
        "observed_at": prospecting_profile["facts"]["access_frontage"]["observed_at"],
    }
    lead_detail = client.get(f"/api/v1/leads/{lead.id}", headers=owner_headers)
    assert lead_detail.status_code == 200, lead_detail.text
    assert lead_detail.json()["property_address"] == (
        "APN APN-45-100, Pickens County, GA"
    )
    owner_workbench = client.get("/api/v1/prospecting", headers=owner_headers)
    assert owner_workbench.status_code == 200, owner_workbench.text
    handoff = owner_workbench.json()["pending_handoffs"][0]
    assert handoff["asset_class"] == "land"
    assert UUID(handoff["lead_id"]) == lead.id
    assert handoff["property_address"] == "APN APN-45-100, Pickens County, GA"

    accepted = client.post(
        f"/api/v1/prospecting/handoffs/{handoff['id']}/decision",
        headers=owner_headers,
        json={"decision": "accepted", "reason": "Land owner details are complete."},
    )
    assert accepted.status_code == 200, accepted.text

    def create_qualification_script(
        asset_class: str,
        title: str,
        questions: list[dict[str, object]],
    ) -> dict[str, Any]:
        response = client.post(
            "/api/v1/lead-manager/scripts",
            headers=owner_headers,
            json={
                "asset_class": asset_class,
                "title": title,
                "introduction": "Confirm the seller's facts without making legal conclusions.",
                "questions": questions,
            },
        )
        assert response.status_code == 201, response.text
        approval = client.post(
            f"/api/v1/lead-manager/scripts/{response.json()['id']}/approve",
            headers=owner_headers,
        )
        assert approval.status_code == 200, approval.text
        return cast(dict[str, Any], approval.json())

    house_qualification = create_qualification_script(
        "house",
        "House Qualification",
        [
            {
                "key": "property_condition",
                "label": "Condition",
                "prompt": "What repairs are needed?",
                "required": True,
            }
        ],
    )
    land_qualification = create_qualification_script(
        "land",
        "Land Qualification",
        [
            {
                "key": "motivation",
                "label": "Motivation",
                "prompt": "Why sell the parcel now?",
                "required": True,
            },
            {
                "key": "parcel_id",
                "label": "Parcel / APN",
                "prompt": "What is the parcel number?",
                "required": False,
            },
            {
                "key": "acreage",
                "label": "Acreage",
                "prompt": "Approximately how many acres are included?",
                "required": True,
            },
            {
                "key": "access_frontage",
                "label": "Access and frontage",
                "prompt": "What legal access or road frontage is known?",
                "required": True,
            },
        ],
    )
    assert house_qualification["asset_class"] == "house"
    assert land_qualification["asset_class"] == "land"

    lead_manager = client.get("/api/v1/lead-manager", headers=owner_headers)
    assert lead_manager.status_code == 200, lead_manager.text
    overview = lead_manager.json()
    assert set(overview["active_scripts"]) == {"house", "land"}
    land_case = next(
        item for item in overview["qualification_queue"] if item["lead_id"] == str(lead.id)
    )
    assert land_case["asset_class"] == "land"

    qualification = client.post(
        f"/api/v1/lead-manager/cases/{land_case['id']}/qualification",
        headers=owner_headers,
        json={
            "answers": {
                "motivation": "No longer plans to build",
                "parcel_id": "APN-45-100",
                "acreage": "7.2 acres",
                "access_frontage": "County road frontage; legal access not yet verified",
            },
            "next_action_type": "call",
            "next_action_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert qualification.status_code == 200, qualification.text
    db_session.refresh(lead)
    assert lead.motivation == "No longer plans to build"
    assert lead.qualification_context["acreage"] == "7.2 acres"
    assert (
        lead.qualification_context["access_frontage"]
        == "County road frontage; legal access not yet verified"
    )
    assert "parcel_id" not in lead.qualification_context
    manager_profile = lead.qualification_context["land_acquisition_v1"]
    assert manager_profile["facts"]["acreage"]["source_type"] == "seller_reported"
    assert manager_profile["facts"]["acreage"]["source_name"] == (
        "lead_manager_qualification"
    )
