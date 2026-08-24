from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    AiOrchestratorEvent,
    Appointment,
    AuditEvent,
    CallRecord,
    CallRecording,
    CallTranscript,
    Contact,
    Conversation,
    Lead,
    LeadManagementCase,
    LeadQualificationSession,
    Notification,
    Prospect,
    ProspectCallingBatchEntry,
    ProspectContactPoint,
    ProspectHandoff,
    ProspectingAttempt,
    ProspectingCallQualityReview,
    ProspectingCopilotRecommendation,
    ProspectingQualificationResponse,
    ProspectingScriptVersion,
    SuppressionRecord,
)
from app.schemas.prospecting import ProspectingQualificationAutosaveRequest
from app.services.bootstrap import bootstrap_foundation
from app.services.lead_manager import process_next_escalation
from app.services.prospecting import autosave_attempt_qualification, list_queue_entries

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "va@example.com"
ACQUISITIONS_EMAIL = "acquisitions@example.com"
OTHER_VA_EMAIL = "other-va@example.com"


def create_user(
    client: TestClient,
    headers: dict[str, str],
    email: str,
    name: str,
    role_key: str,
    *,
    calling_enabled: bool = False,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": email,
            "display_name": name,
            "role_key": role_key,
            "calling_enabled": calling_enabled,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_cold_calling_can_be_added_to_another_staff_role_without_broadening_access(
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
    caller_email = "disposition-caller@example.com"
    other_caller_email = "other-disposition-caller@example.com"
    disabled_email = "disposition-only@example.com"
    caller = create_user(
        client,
        owner_headers,
        caller_email,
        "Disposition Caller",
        "disposition_rep",
        calling_enabled=True,
    )
    create_user(
        client,
        owner_headers,
        other_caller_email,
        "Other Disposition Caller",
        "disposition_rep",
        calling_enabled=True,
    )
    disabled = create_user(
        client,
        owner_headers,
        disabled_email,
        "Disposition Only",
        "disposition_rep",
    )
    assert caller["calling_enabled"] is True
    assert disabled["calling_enabled"] is False

    batch = create_prospecting_batch(client, owner_headers, caller["id"])
    create_approved_script(client, owner_headers)
    caller_headers = {"X-Dev-User-Email": caller_email}
    caller_workbench = client.get("/api/v1/prospecting", headers=caller_headers)
    assert caller_workbench.status_code == 200, caller_workbench.text
    assert caller_workbench.json()["can_manage"] is False
    assert len(caller_workbench.json()["queue_entries"]) == 3
    assert {entry["assigned_user_name"] for entry in caller_workbench.json()["queue_entries"]} == {
        "Disposition Caller"
    }

    other_workbench = client.get(
        "/api/v1/prospecting",
        headers={"X-Dev-User-Email": other_caller_email},
    )
    assert other_workbench.status_code == 200, other_workbench.text
    assert other_workbench.json()["current_entry"] is None
    assert other_workbench.json()["queue_entries"] == []
    assert (
        client.get(
            "/api/v1/prospecting",
            headers={"X-Dev-User-Email": disabled_email},
        ).status_code
        == 403
    )
    operations = client.get("/api/v1/operations", headers=caller_headers)
    assert operations.status_code == 200, operations.text
    assert operations.json()["can_manage"] is False
    assert [user["id"] for user in operations.json()["users"]] == [caller["id"]]
    assert client.get("/api/v1/campaign-management", headers=caller_headers).status_code == 403

    start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=caller_headers,
    )
    assert start.status_code == 200, start.text
    attempt = db_session.get(
        ProspectingAttempt,
        UUID(start.json()["active_attempt"]["id"]),
    )
    assert attempt is not None
    assert str(attempt.caller_user_id) == caller["id"]

    prospect_response = client.post(
        "/api/v1/operations/prospects",
        headers=owner_headers,
        json={
            "campaign_id": batch["campaign_id"],
            "legal_name": "Unassigned Seller",
            "phone": "4045550199",
        },
    )
    assert prospect_response.status_code == 201, prospect_response.text
    disabled_batch = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": batch["campaign_id"],
            "assigned_user_id": disabled["id"],
            "name": "Disabled Caller Batch",
            "maximum_records": 10,
        },
    )
    assert disabled_batch.status_code == 422
    assert "Enable cold calling" in disabled_batch.json()["detail"]

    disabled_va_email = "disabled-va@example.com"
    disabled_va = create_user(
        client,
        owner_headers,
        disabled_va_email,
        "Temporarily Disabled VA",
        "prospecting_caller",
    )
    assert disabled_va["calling_enabled"] is True
    disable_response = client.patch(
        f"/api/v1/operations/users/{disabled_va['id']}",
        headers=owner_headers,
        json={
            "calling_enabled": False,
            "reason": "Caller is temporarily unavailable for batch assignments.",
        },
    )
    assert disable_response.status_code == 200, disable_response.text
    assert disable_response.json()["calling_enabled"] is False
    assert (
        client.get(
            "/api/v1/prospecting",
            headers={"X-Dev-User-Email": disabled_va_email},
        ).status_code
        == 403
    )


def create_prospecting_batch(
    client: TestClient,
    owner_headers: dict[str, str],
    va_id: str,
) -> dict[str, Any]:
    market_response = client.post(
        "/api/v1/operations/markets",
        headers=owner_headers,
        json={
            "name": "Atlanta Metro",
            "code": "atlanta-metro",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=owner_headers,
        json={
            "market_id": market_response.json()["id"],
            "name": "Owner Outreach",
            "code": "owner-outreach",
            "channel": "cold_call",
            "asset_class": "house",
        },
    )
    assert campaign_response.status_code == 201, campaign_response.text
    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=owner_headers,
        json={
            "name": "VA Workbench Import",
            "field_mapping": {
                "source_record_key": "ID",
                "legal_name": "Owner",
                "phone": "Phone",
                "street_address": "Address",
                "city": "City",
                "state_code": "State",
                "postal_code": "ZIP",
                "dnc_status": "DNC",
            },
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    csv_content = """ID,Owner,Phone,Address,City,State,ZIP,DNC
1,Interested Seller,4045550101,101 Main St,Atlanta,GA,30303,No
2,DNC Seller,4045550102,102 Main St,Atlanta,GA,30303,No
3,Callback Seller,4045550103,103 Main St,Atlanta,GA,30303,No
"""
    import_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=owner_headers,
        json={
            "campaign_id": campaign_response.json()["id"],
            "mapping_id": mapping_response.json()["id"],
            "default_assignee_user_id": va_id,
            "file_name": "va-workbench.csv",
            "csv_content": csv_content,
        },
    )
    assert import_response.status_code == 201, import_response.text
    batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=owner_headers,
        json={
            "campaign_id": campaign_response.json()["id"],
            "import_batch_id": import_response.json()["id"],
            "assigned_user_id": va_id,
            "name": "VA Daily Queue",
            "maximum_records": 100,
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    return cast(dict[str, Any], batch_response.json())


def create_approved_script(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/prospecting/scripts",
        headers=headers,
        json={
            "title": "Stonegate Seller Conversation",
            "opening_script": (
                "Hi, this is Stonegate Home Buyers. I am calling about the property. "
                "Did I catch you at an okay time?"
            ),
            "qualification_questions": [
                {
                    "key": "motivation",
                    "label": "Reason for selling",
                    "prompt": "What has you considering selling the property?",
                    "required_for_handoff": True,
                },
                {
                    "key": "timeline",
                    "label": "Timeline",
                    "prompt": "When would you ideally like to sell?",
                    "required_for_handoff": True,
                },
                {
                    "key": "property_condition",
                    "label": "Property condition",
                    "prompt": "What repairs or updates does the property need?",
                    "required_for_handoff": True,
                },
                {
                    "key": "occupancy",
                    "label": "Occupancy",
                    "prompt": "Is the property owner occupied, tenant occupied, or vacant?",
                    "answer_type": "choice",
                    "choices": ["Owner occupied", "Tenant occupied", "Vacant"],
                    "required_for_handoff": True,
                },
                {
                    "key": "asking_price",
                    "label": "Price expectation",
                    "prompt": "Do you have a price in mind?",
                    "required_for_handoff": False,
                },
            ],
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


def test_qualification_autosave_is_scoped_idempotent_and_authoritative(
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
    caller = create_user(
        client,
        owner_headers,
        VA_EMAIL,
        "Qualification VA",
        "prospecting_caller",
    )
    create_user(
        client,
        owner_headers,
        OTHER_VA_EMAIL,
        "Other Qualification VA",
        "prospecting_caller",
    )
    acquisitions = create_user(
        client,
        owner_headers,
        ACQUISITIONS_EMAIL,
        "Acquisitions Owner",
        "acquisition_rep",
        calling_enabled=True,
    )
    batch = create_prospecting_batch(client, owner_headers, caller["id"])
    pinned_script = create_approved_script(client, owner_headers)
    caller_headers = {"X-Dev-User-Email": VA_EMAIL}
    start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=caller_headers,
    )
    assert start.status_code == 200, start.text
    attempt_id = start.json()["active_attempt"]["id"]
    assert start.json()["script"]["id"] == pinned_script["id"]
    assert start.json()["source_name"]
    assert isinstance(start.json()["warnings"], list)
    replacement_script = create_approved_script(client, owner_headers)
    assert replacement_script["id"] != pinned_script["id"]
    refreshed_workbench = client.get("/api/v1/prospecting", headers=caller_headers)
    assert refreshed_workbench.status_code == 200
    assert refreshed_workbench.json()["current_entry"]["script"]["id"] == pinned_script["id"]

    checklist_url = f"/api/v1/prospecting/attempts/{attempt_id}/qualification"
    checklist = client.get(checklist_url, headers=caller_headers)
    assert checklist.status_code == 200, checklist.text
    assert checklist.headers["cache-control"] == "private, no-store"
    assert checklist.json()["script_version_id"] == pinned_script["id"]
    assert checklist.json()["answered_count"] == 0
    assert checklist.json()["required_count"] == 4
    assert checklist.json()["complete"] is False
    assert {item["state"] for item in checklist.json()["items"]} == {"not_covered"}

    assert (
        client.get(
            checklist_url,
            headers={"X-Dev-User-Email": OTHER_VA_EMAIL},
        ).status_code
        == 403
    )
    assert client.get(checklist_url, headers=owner_headers).status_code == 200
    mutation_url = f"{checklist_url}/motivation"
    mutation_id = "670b4bf6-b085-46f6-8dd5-4691718c5309"
    owner_write = client.put(
        mutation_url,
        headers=owner_headers,
        json={
            "state": "answered",
            "answer_value": "Inherited property",
            "expected_revision": 0,
            "mutation_id": mutation_id,
        },
    )
    assert owner_write.status_code == 403
    assigned_manager_attempt = db_session.get(ProspectingAttempt, UUID(attempt_id))
    assert assigned_manager_attempt is not None
    saved_by_assigned_manager = autosave_attempt_qualification(
        db_session,
        Principal(
            user_id=UUID(caller["id"]),
            organization_id=assigned_manager_attempt.organization_id,
            email=VA_EMAIL,
            permission_keys=frozenset(
                {
                    PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
                    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
                }
            ),
        ),
        UUID(attempt_id),
        "timeline",
        ProspectingQualificationAutosaveRequest(
            state="answered",
            answer_value="Within 90 days",
            expected_revision=0,
            mutation_id="32d4a12c-1432-44aa-a155-98d6b41581ce",
        ),
    )
    assert saved_by_assigned_manager is not None
    assert saved_by_assigned_manager.answer_value == "Within 90 days"
    blank = client.put(
        mutation_url,
        headers=caller_headers,
        json={
            "state": "answered",
            "answer_value": "   ",
            "expected_revision": 0,
            "mutation_id": "5e837b92-9104-4fcc-a510-d5ebdf835d28",
        },
    )
    assert blank.status_code == 422
    for state in ("needs_follow_up", "conflict"):
        blank_state = client.put(
            f"{checklist_url}/asking_price",
            headers=caller_headers,
            json={
                "state": state,
                "answer_value": " ",
                "expected_revision": 0,
                "mutation_id": (
                    "2c9c6440-9e03-461e-9318-fb41365d0428"
                    if state == "needs_follow_up"
                    else "f7b18d6d-51d5-45f3-ab3e-60275d96224c"
                ),
            },
        )
        assert blank_state.status_code == 422
    invalid_choice = client.put(
        f"{checklist_url}/occupancy",
        headers=caller_headers,
        json={
            "state": "answered",
            "answer_value": "Sometimes",
            "expected_revision": 0,
            "mutation_id": "573196eb-1544-4124-8556-8be3f42058b4",
        },
    )
    assert invalid_choice.status_code == 422
    choice_follow_up = client.put(
        f"{checklist_url}/occupancy",
        headers=caller_headers,
        json={
            "state": "needs_follow_up",
            "answer_value": "Seller was unsure who is currently staying there",
            "expected_revision": 0,
            "mutation_id": "41cd8b1c-cc20-4d7f-85f6-82b42f5c4c08",
        },
    )
    assert choice_follow_up.status_code == 200, choice_follow_up.text
    assert choice_follow_up.json()["answer_value"] == (
        "Seller was unsure who is currently staying there"
    )

    payload = {
        "state": "answered",
        "answer_value": "Inherited property",
        "expected_revision": 0,
        "mutation_id": mutation_id,
    }
    saved = client.put(mutation_url, headers=caller_headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.headers["cache-control"] == "private, no-store"
    assert saved.json()["revision"] == 1
    assert saved.json()["source"] == "va_entry"
    replay = client.put(mutation_url, headers=caller_headers, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json() == saved.json()
    motivation_response_id = db_session.scalar(
        select(ProspectingQualificationResponse.id).where(
            ProspectingQualificationResponse.attempt_id == UUID(attempt_id),
            ProspectingQualificationResponse.question_key == "motivation",
        )
    )
    assert motivation_response_id is not None
    mutation_audits = db_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "prospecting.qualification_response_saved",
            AuditEvent.entity_id == motivation_response_id,
        )
    )
    assert mutation_audits == 1
    changed_replay = client.put(
        mutation_url,
        headers=caller_headers,
        json={**payload, "answer_value": "Different answer"},
    )
    assert changed_replay.status_code == 409
    stale = client.put(
        mutation_url,
        headers=caller_headers,
        json={
            **payload,
            "mutation_id": "f6675085-90cf-46aa-b64b-71032d65f6a0",
            "expected_revision": 0,
        },
    )
    assert stale.status_code == 409

    optional_url = f"{checklist_url}/asking_price"
    follow_up = client.put(
        optional_url,
        headers=caller_headers,
        json={
            "state": "needs_follow_up",
            "answer_value": "Seller deferred the answer",
            "expected_revision": 0,
            "mutation_id": "77271b80-8f12-4ad3-9255-40b1cab617fd",
        },
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["state"] == "needs_follow_up"
    first_capture = follow_up.json()["captured_at"]
    conflict = client.put(
        optional_url,
        headers=caller_headers,
        json={
            "state": "conflict",
            "answer_value": "Seller gave two prices",
            "expected_revision": 1,
            "mutation_id": "eb3683c9-7788-4fda-bf6c-c4c89d0dd3db",
        },
    )
    assert conflict.status_code == 200
    assert conflict.json()["state"] == "conflict"
    assert conflict.json()["captured_at"] == first_capture
    cleared = client.put(
        optional_url,
        headers=caller_headers,
        json={
            "state": "not_covered",
            "answer_value": "This must be cleared",
            "expected_revision": 2,
            "mutation_id": "7141d365-5be2-4727-8a70-7382a5927157",
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["state"] == "not_covered"
    assert cleared.json()["answer_value"] is None
    assert cleared.json()["captured_at"] == first_capture
    occupancy_saved = client.put(
        f"{checklist_url}/occupancy",
        headers=caller_headers,
        json={
            "state": "answered",
            "answer_value": "Owner occupied",
            "expected_revision": 1,
            "mutation_id": "9b49000c-d353-46eb-a94a-975a47e2d599",
        },
    )
    assert occupancy_saved.status_code == 200

    refreshed = client.get(checklist_url, headers=caller_headers)
    motivation = next(
        item for item in refreshed.json()["items"] if item["question_key"] == "motivation"
    )
    assert motivation["answer_value"] == "Inherited property"
    assert motivation["state"] == "answered"
    assert refreshed.json()["answered_count"] == 3

    completed = client.post(
        f"/api/v1/prospecting/attempts/{attempt_id}/complete",
        headers=caller_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "Stale browser value",
                "timeline": "Within 30 days",
                "property_condition": "Needs paint",
                "occupancy": "Invalid stale browser choice",
            },
        },
    )
    assert completed.status_code == 200, completed.text
    completed_attempt = next(
        item for item in completed.json()["attempts"] if item["id"] == attempt_id
    )
    assert completed_attempt["qualification_answers"]["motivation"] == "Inherited property"
    assert completed_attempt["qualification_answers"]["timeline"] == "Within 90 days"
    assert completed_attempt["qualification_answers"]["occupancy"] == "Owner occupied"
    persisted = db_session.scalar(
        select(ProspectingQualificationResponse).where(
            ProspectingQualificationResponse.attempt_id == UUID(attempt_id),
            ProspectingQualificationResponse.question_key == "motivation",
        )
    )
    assert persisted is not None
    assert persisted.source == "va_entry"
    assert str(persisted.actor_user_id) == caller["id"]
    materialized = db_session.scalar(
        select(ProspectingQualificationResponse).where(
            ProspectingQualificationResponse.attempt_id == UUID(attempt_id),
            ProspectingQualificationResponse.question_key == "property_condition",
        )
    )
    assert materialized is not None
    assert materialized.answer_value == "Needs paint"
    assert materialized.source == "legacy_completion"
    assert materialized.actor_user_id == UUID(caller["id"])
    assert materialized.captured_at is not None
    assert materialized.response_metadata["revision"] == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "prospecting.qualification_response_materialized",
                AuditEvent.entity_id == materialized.id,
            )
        )
        == 1
    )
    after_complete = client.put(
        mutation_url,
        headers=caller_headers,
        json={
            "state": "not_covered",
            "answer_value": None,
            "expected_revision": 1,
            "mutation_id": "ae4a3b25-6ec4-4af8-b4e1-dca6960dbb91",
        },
    )
    assert after_complete.status_code == 409


def test_queue_serialization_query_count_is_constant_for_twenty_five_entries(
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
    caller = create_user(
        client,
        owner_headers,
        VA_EMAIL,
        "Queue Performance VA",
        "prospecting_caller",
    )
    batch_payload = create_prospecting_batch(client, owner_headers, caller["id"])
    script_payload = create_approved_script(client, owner_headers)
    batch_id = UUID(batch_payload["id"])
    organization_id = foundation.organization.id
    caller_id = UUID(caller["id"])
    script_id = UUID(script_payload["id"])
    now = datetime.now(UTC)

    existing_entries = db_session.scalars(
        select(ProspectCallingBatchEntry)
        .where(ProspectCallingBatchEntry.prospect_calling_batch_id == batch_id)
        .order_by(ProspectCallingBatchEntry.sequence_number)
    ).all()
    assert len(existing_entries) == 3
    template = db_session.get(Prospect, existing_entries[0].prospect_id)
    assert template is not None
    for sequence_number in range(4, 26):
        suffix = f"{sequence_number:02d}"
        phone = f"40455501{sequence_number:02d}"
        prospect = Prospect(
            organization_id=organization_id,
            campaign_id=template.campaign_id,
            asset_class=template.asset_class,
            territory_id=template.territory_id,
            assigned_user_id=caller_id,
            converted_lead_id=None,
            import_batch_id=template.import_batch_id,
            source_record_key=f"queue-perf-{suffix}",
            status="ready",
            legal_name=f"Queue Seller {suffix}",
            phone=phone,
            normalized_phone=f"+1{phone}",
            email=None,
            normalized_email=None,
            street_address=f"{sequence_number} Performance Way",
            city="Atlanta",
            state_code="GA",
            postal_code="30303",
            normalized_address_key=f"{sequence_number} performance way atlanta ga 30303",
            suppression_status="clear",
            suppression_checked_at=now,
            phone_validation_status="valid",
            address_validation_status="valid",
            call_eligibility="eligible",
            last_contacted_at=None,
            source_payload={},
        )
        db_session.add(prospect)
        db_session.flush()
        entry = ProspectCallingBatchEntry(
            organization_id=organization_id,
            prospect_calling_batch_id=batch_id,
            prospect_id=prospect.id,
            assigned_user_id=caller_id,
            sequence_number=sequence_number,
            status="ready",
            attempt_count=1,
            disposition=None,
            last_attempt_at=None,
            next_attempt_at=None,
            completed_at=None,
        )
        contact_point = ProspectContactPoint(
            organization_id=organization_id,
            prospect_id=prospect.id,
            source_membership_id=None,
            contact_type="phone",
            value=phone,
            normalized_value=f"+1{phone}",
            rank=1,
            is_primary=True,
            validation_status="valid",
            first_seen_at=now,
            last_seen_at=now,
            contact_metadata={},
        )
        db_session.add_all((entry, contact_point))
        db_session.flush()
        attempt = ProspectingAttempt(
            organization_id=organization_id,
            batch_entry_id=entry.id,
            prospect_id=prospect.id,
            caller_user_id=caller_id,
            script_version_id=script_id,
            call_record_id=None,
            provider=None,
            provider_call_id=None,
            provider_recording_id=None,
            provider_agent_id=None,
            cohort_id=None,
            status="completed",
            outcome="no_answer",
            contact_made=False,
            dialer_mode="one_line_power",
            answer_classification="no_answer",
            party_classification="unknown",
            interest_classification="not_assessed",
            follow_up_permission="not_recorded",
            classification_source="manual_outcome",
            dial_started_at=now,
            answered_at=None,
            right_party_confirmed_at=None,
            interest_confirmed_at=None,
            measurement_metadata={},
            qualification_answers={"motivation": "Testing batched reads"},
            notes=None,
            callback_at=None,
            started_at=now,
            completed_at=now,
            required_answer_count=4,
            answered_required_count=1,
            quality_score_basis_points=2500,
        )
        db_session.add(attempt)
        db_session.flush()
        db_session.add(
            ProspectingQualificationResponse(
                organization_id=organization_id,
                attempt_id=attempt.id,
                script_version_id=script_id,
                question_key="motivation",
                state="answered",
                answer_value="Testing batched reads",
                source="va_entry",
                actor_user_id=caller_id,
                is_required=True,
                captured_at=now,
                transcript_evidence=None,
                response_metadata={"revision": 1},
            )
        )
    db_session.commit()

    principal = Principal(
        user_id=caller_id,
        organization_id=organization_id,
        email=VA_EMAIL,
        permission_keys=frozenset({PermissionKeys.MANAGE_ACQUISITION_OPERATIONS}),
    )
    engine = db_session.get_bind()

    def measure_selects() -> tuple[int, int]:
        count = 0

        def count_selects(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            nonlocal count
            if statement.lstrip().upper().startswith("SELECT"):
                count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            with Session(bind=engine) as measured_db:
                result = list_queue_entries(measured_db, principal, manageable=True)
                return len(result), count
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

    all_entries = db_session.scalars(
        select(ProspectCallingBatchEntry)
        .where(ProspectCallingBatchEntry.prospect_calling_batch_id == batch_id)
        .order_by(ProspectCallingBatchEntry.sequence_number)
    ).all()
    assert len(all_entries) == 25
    for entry in all_entries[1:]:
        entry.status = "completed"
    db_session.commit()
    one_length, one_selects = measure_selects()

    for entry in all_entries:
        entry.status = "ready"
    db_session.commit()
    twenty_five_length, twenty_five_selects = measure_selects()

    assert one_length == 1
    assert twenty_five_length == 25
    assert twenty_five_selects <= one_selects + 1
    assert twenty_five_selects < 20


def test_phase_four_guided_queue_handoff_review_and_scorecards(
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
    va = create_user(client, owner_headers, VA_EMAIL, "VA Caller", "prospecting_caller")
    create_user(
        client,
        owner_headers,
        OTHER_VA_EMAIL,
        "Other VA Caller",
        "prospecting_caller",
    )
    other_va_headers = {"X-Dev-User-Email": OTHER_VA_EMAIL}
    acquisitions = create_user(
        client,
        owner_headers,
        ACQUISITIONS_EMAIL,
        "Lead Manager",
        "acquisition_manager",
    )
    batch = create_prospecting_batch(client, owner_headers, va["id"])

    no_script_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    assert no_script_start.status_code == 422
    assert "approve a caller script" in no_script_start.json()["detail"]
    assert (
        client.post(
            "/api/v1/prospecting/scripts",
            headers=va_headers,
            json={
                "title": "Unauthorized",
                "opening_script": "This caller cannot create an approved company script.",
                "qualification_questions": [
                    {"key": "motivation", "label": "Motivation", "prompt": "Why sell?"}
                ],
            },
        ).status_code
        == 403
    )
    script = create_approved_script(client, owner_headers)
    assert script["version_number"] == 1
    assert script["status"] == "approved"

    workbench_response = client.get("/api/v1/prospecting", headers=va_headers)
    assert workbench_response.status_code == 200, workbench_response.text
    workbench = workbench_response.json()
    assert workbench["can_manage"] is False
    assert workbench["current_entry"]["legal_name"] == "Interested Seller"
    assert workbench["queue"]["ready"] == 3
    assert workbench["scripts"] == []
    assert len(workbench["queue_entries"]) == 3
    assert workbench["queue_entries"][0]["queue_kind"] == "ready"
    assert workbench["queue_entries"][0]["is_actionable"] is True
    assert workbench["queue_entries"][0]["provider_sync_status"] == "stonegate_direct"
    assert workbench["queue_entries"][0]["dialer_mode"] == "one_line_power"
    assert workbench["queue_entries"][0]["assigned_user_name"] == "VA Caller"
    assert workbench["queue_entries"][0]["contact_points"][0]["contact_type"] == "phone"
    assert len(workbench["batch_queues"]) == 1
    assert workbench["batch_queues"][0]["ready"] == 3
    assert (
        client.post(
            f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
            headers=other_va_headers,
        ).status_code
        == 404
    )
    manager_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=owner_headers,
    )
    assert manager_start.status_code == 403
    assert "assigned caller" in manager_start.json()["detail"]
    for restricted_path in (
        "/api/v1/underwriting/calibration",
        "/api/v1/transactions",
        "/api/v1/buyers",
        "/api/v1/finance",
        "/api/v1/email/recipients",
        "/api/v1/email/admin/options",
    ):
        assert client.get(restricted_path, headers=va_headers).status_code == 403

    first_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    assert first_start.status_code == 200, first_start.text
    first_attempt_id = first_start.json()["active_attempt"]["id"]
    concurrent_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][1]['id']}/start",
        headers=va_headers,
    )
    assert concurrent_start.status_code == 422
    assert "Finish the active prospect" in concurrent_start.json()["detail"]

    incomplete_handoff = client.post(
        f"/api/v1/prospecting/attempts/{first_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {"motivation": "Inherited property"},
        },
    )
    assert incomplete_handoff.status_code == 422
    first_completion = client.post(
        f"/api/v1/prospecting/attempts/{first_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "appointment_set",
            "handoff_user_id": acquisitions["id"],
            "appointment_start_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
            "appointment_location_type": "seller_property",
            "qualification_answers": {
                "motivation": "Inherited property",
                "timeline": "Within 30 days",
                "property_condition": "Needs roof and kitchen updates",
                "occupancy": "Vacant",
                "asking_price": "$180,000",
            },
            "notes": "Seller is available after 3 PM.",
        },
    )
    assert first_completion.status_code == 200, first_completion.text
    assert first_completion.json()["status"] == "handoff_pending"
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Contact)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(Appointment)) or 0) == 1

    manager_overview = client.get("/api/v1/prospecting", headers=owner_headers)
    assert manager_overview.status_code == 200, manager_overview.text
    pending = manager_overview.json()["pending_handoffs"]
    assert len(pending) == 1
    assert pending[0]["seller_name"] == "Interested Seller"
    assert (
        client.post(
            f"/api/v1/prospecting/handoffs/{pending[0]['id']}/decision",
            headers=va_headers,
            json={"decision": "accepted"},
        ).status_code
        == 403
    )
    correction = client.post(
        f"/api/v1/prospecting/handoffs/{pending[0]['id']}/decision",
        headers=owner_headers,
        json={"decision": "needs_correction", "reason": "Confirm decision-maker authority."},
    )
    assert correction.status_code == 200, correction.text
    returned = client.get("/api/v1/prospecting", headers=va_headers).json()
    assert returned["current_entry"]["status"] == "needs_correction"
    assert returned["returned_handoffs"][0]["review_reason"] == (
        "Confirm decision-maker authority."
    )

    correction_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    correction_attempt_id = correction_start.json()["active_attempt"]["id"]
    corrected = client.post(
        f"/api/v1/prospecting/attempts/{correction_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "Inherited property; sole owner confirmed",
                "timeline": "Within 30 days",
                "property_condition": "Needs roof and kitchen updates",
                "occupancy": "Vacant",
            },
            "notes": "Seller confirmed they are the sole decision-maker.",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert int(db_session.scalar(select(func.count()).select_from(Lead)) or 0) == 1
    pending_again = client.get("/api/v1/prospecting", headers=owner_headers).json()[
        "pending_handoffs"
    ]
    assert len(pending_again) == 1
    accepted = client.post(
        f"/api/v1/prospecting/handoffs/{pending_again[0]['id']}/decision",
        headers=owner_headers,
        json={"decision": "accepted", "reason": "Qualification is complete."},
    )
    assert accepted.status_code == 200, accepted.text
    lead = db_session.scalar(select(Lead))
    prospect = db_session.scalar(select(Prospect).where(Prospect.legal_name == "Interested Seller"))
    assert lead is not None and lead.stage_key == "appointment_scheduled"
    assert prospect is not None and prospect.status == "converted"
    ai_event = db_session.scalar(
        select(AiOrchestratorEvent).where(
            AiOrchestratorEvent.event_key == f"lead.created:{lead.id}"
        )
    )
    assert ai_event is not None
    assert ai_event.status == "queued"
    assert (ai_event.payload or {}).get("trigger_source") == "prospecting_handoff"

    lead_manager_overview = client.get("/api/v1/lead-manager", headers=owner_headers)
    assert lead_manager_overview.status_code == 200, lead_manager_overview.text
    lead_manager_case = lead_manager_overview.json()["qualification_queue"][0]
    assert lead_manager_case["assigned_user_name"] == "Lead Manager"
    assert lead_manager_case["accepted_at"] is not None

    qualification_script = client.post(
        "/api/v1/lead-manager/scripts",
        headers=owner_headers,
        json={
            "title": "Stonegate Lead Manager Qualification",
            "introduction": "Confirm the seller's needs before recommending the next action.",
            "questions": [
                {
                    "key": "decision_makers",
                    "label": "Decision makers",
                    "prompt": "Who needs to approve a sale?",
                    "required": True,
                },
                {
                    "key": "motivation",
                    "label": "Motivation",
                    "prompt": "What is driving the possible sale?",
                    "required": True,
                },
                {
                    "key": "timeline",
                    "label": "Timeline",
                    "prompt": "When would the seller ideally close?",
                    "required": True,
                },
                {
                    "key": "property_condition",
                    "label": "Condition",
                    "prompt": "What repairs or updates are needed?",
                    "required": True,
                },
                {
                    "key": "occupancy",
                    "label": "Occupancy",
                    "prompt": "Who currently occupies the property?",
                    "required": True,
                },
                {
                    "key": "asking_price",
                    "label": "Price expectation",
                    "prompt": "Does the seller have a price in mind?",
                    "required": False,
                },
            ],
        },
    )
    assert qualification_script.status_code == 201, qualification_script.text
    script_id = qualification_script.json()["id"]
    approved_script = client.post(
        f"/api/v1/lead-manager/scripts/{script_id}/approve",
        headers=owner_headers,
    )
    assert approved_script.status_code == 200, approved_script.text

    missing_qualification = client.post(
        f"/api/v1/lead-manager/cases/{lead_manager_case['id']}/qualification",
        headers=owner_headers,
        json={
            "answers": {"motivation": "Inherited property"},
            "next_action_type": "call",
            "next_action_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert missing_qualification.status_code == 422
    qualification = client.post(
        f"/api/v1/lead-manager/cases/{lead_manager_case['id']}/qualification",
        headers=owner_headers,
        json={
            "answers": {
                "decision_makers": "Seller is the sole owner and decision-maker",
                "motivation": "Inherited property and does not want to renovate",
                "timeline": "Within 30 days",
                "property_condition": "Needs roof and kitchen updates",
                "occupancy": "Vacant",
                "asking_price": "$180,000",
            },
            "next_action_type": "call",
            "next_action_due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert qualification.status_code == 200, qualification.text
    assert qualification.json()["script_version_number"] == 1
    assert qualification.json()["quality_score_basis_points"] == 10000
    assert (
        int(db_session.scalar(select(func.count()).select_from(LeadQualificationSession)) or 0) == 1
    )
    updated_overview = client.get("/api/v1/lead-manager", headers=owner_headers).json()
    assert updated_overview["metrics"]["qualification_due"] == 0
    assert updated_overview["scorecards"][0]["qualifications_completed"] == 1

    case_record = db_session.get(LeadManagementCase, UUID(lead_manager_case["id"]))
    assert case_record is not None
    case_record.status = "awaiting_acceptance"
    case_record.accepted_at = None
    case_record.accepted_by_user_id = None
    case_record.acceptance_due_at = datetime.now(UTC) - timedelta(minutes=1)
    case_record.escalated_at = None
    db_session.commit()
    escalated_id = process_next_escalation(db_session, get_settings())
    assert escalated_id == case_record.id
    db_session.refresh(case_record)
    assert case_record.status == "overdue"
    assert case_record.escalated_at is not None

    second_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][1]['id']}/start",
        headers=va_headers,
    )
    second_attempt_id = second_start.json()["active_attempt"]["id"]
    dnc_completion = client.post(
        f"/api/v1/prospecting/attempts/{second_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "do_not_call",
            "qualification_answers": {},
            "compliance_flags": ["seller_complaint"],
        },
    )
    assert dnc_completion.status_code == 200, dnc_completion.text
    assert dnc_completion.json()["status"] == "completed"
    assert int(db_session.scalar(select(func.count()).select_from(SuppressionRecord)) or 0) == 1
    quality_review = db_session.scalar(
        select(ProspectingCallQualityReview).where(
            ProspectingCallQualityReview.attempt_id == UUID(second_attempt_id)
        )
    )
    assert quality_review is not None
    assert quality_review.status == "escalated"
    assert quality_review.transcript_id is None
    assert quality_review.compliance_flags == [
        "do_not_call_request",
        "seller_complaint",
    ]
    assert quality_review.deterministic_scores["script_adherence_score"] is None
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.notification_type == "prospecting_compliance_escalation")
            )
            or 0
        )
        >= 1
    )

    third_start = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][2]['id']}/start",
        headers=va_headers,
    )
    third_attempt_id = third_start.json()["active_attempt"]["id"]
    callback_at = datetime.now(UTC) + timedelta(days=1)
    callback_completion = client.post(
        f"/api/v1/prospecting/attempts/{third_attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "callback_requested",
            "callback_at": callback_at.isoformat(),
            "qualification_answers": {},
        },
    )
    assert callback_completion.status_code == 200, callback_completion.text
    assert callback_completion.json()["status"] == "queued"
    assert callback_completion.json()["next_attempt_at"] is not None

    final_overview = client.get("/api/v1/prospecting", headers=owner_headers).json()
    va_final_overview = client.get("/api/v1/prospecting", headers=va_headers).json()
    scheduled_callback = next(
        item
        for item in va_final_overview["queue_entries"]
        if item["prospect_id"] == callback_completion.json()["prospect_id"]
    )
    assert scheduled_callback["queue_kind"] == "callback_scheduled"
    assert scheduled_callback["is_actionable"] is False
    assert va_final_overview["queue"]["callbacks_scheduled"] == 1
    scorecard = final_overview["scorecards"][0]
    assert scorecard["attempts"] == 4
    assert scorecard["contacts"] == 4
    assert scorecard["handoffs"] == 2
    assert scorecard["accepted_handoffs"] == 1
    assert scorecard["dnc_requests"] == 1
    assert scorecard["script_completion_rate_basis_points"] == 5000
    assert int(db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(ProspectHandoff)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(ProspectingScriptVersion)) or 0) == 1
    )
    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert {
        "prospecting.script_created",
        "prospecting.script_approved",
        "prospecting.attempt_started",
        "prospecting.attempt_completed",
        "prospecting.handoff_needs_correction",
        "prospecting.handoff_accepted",
    } <= actions


def test_terminal_handoff_rejection_uses_structured_reason_and_does_not_count_as_warm(
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
    va = create_user(client, owner_headers, VA_EMAIL, "VA Caller", "prospecting_caller")
    acquisitions = create_user(
        client,
        owner_headers,
        ACQUISITIONS_EMAIL,
        "Lead Manager",
        "acquisition_manager",
    )
    batch = create_prospecting_batch(client, owner_headers, va["id"])
    create_approved_script(client, owner_headers)
    started = client.post(
        f"/api/v1/prospecting/entries/{batch['entries'][0]['id']}/start",
        headers=va_headers,
    )
    attempt_id = started.json()["active_attempt"]["id"]
    completed = client.post(
        f"/api/v1/prospecting/attempts/{attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "Considering an offer",
                "timeline": "Within 60 days",
                "property_condition": "Needs updates",
                "occupancy": "Vacant",
            },
        },
    )
    assert completed.status_code == 200, completed.text
    handoff = client.get("/api/v1/prospecting", headers=owner_headers).json()["pending_handoffs"][0]
    rejected = client.post(
        f"/api/v1/prospecting/handoffs/{handoff['id']}/decision",
        headers=owner_headers,
        json={
            "decision": "rejected",
            "reason_code": "rejected_wrong_party",
            "reason": "Caller reached a tenant who cannot authorize a sale.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["decision_code"] == "rejected_wrong_party"

    lead = db_session.get(Lead, UUID(handoff["lead_id"]))
    lead_case = db_session.scalar(
        select(LeadManagementCase).where(LeadManagementCase.handoff_id == UUID(handoff["id"]))
    )
    assert lead is not None and lead.stage_key == "disqualified"
    assert lead_case is not None and lead_case.status == "closed"
    quality = client.get("/api/v1/campaign-management", headers=owner_headers).json()["quality"][0]
    assert quality["submitted_handoffs"] == 1
    assert quality["rejected_handoffs"] == 1
    assert quality["accepted_warm_leads"] == 0


def test_prospecting_copilot_is_draft_only_and_call_coaching_requires_review(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
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
    va = create_user(client, owner_headers, VA_EMAIL, "VA Caller", "prospecting_caller")
    acquisitions = create_user(
        client,
        owner_headers,
        ACQUISITIONS_EMAIL,
        "Lead Manager",
        "acquisition_manager",
    )
    batch = create_prospecting_batch(client, owner_headers, va["id"])
    create_approved_script(client, owner_headers)

    initial = client.get("/api/v1/prospecting", headers=va_headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["copilot"]["pilot_mode"] == "draft_only"
    assert initial.json()["copilot"]["external_actions_blocked"] is True
    assert len(initial.json()["copilot"]["work_items"]) == 3
    entry_id = batch["entries"][0]["id"]
    initial_entry = next(
        item for item in initial.json()["copilot"]["work_items"] if item["entry_id"] == entry_id
    )
    assert initial_entry["priority_score"] == 65
    assert "eligible" in " ".join(initial_entry["eligibility_evidence"]).lower()

    assert (
        client.post("/api/v1/ai/orchestrator/portfolio/install", headers=owner_headers).status_code
        == 201
    )
    assert client.post("/api/v1/ai/copilots/install", headers=owner_headers).status_code == 201
    assert (
        client.post(
            "/api/v1/ai/copilots/foundation/decision",
            headers=owner_headers,
            json={"decision": "approve", "notes": "Approved for the AI5 integration test."},
        ).status_code
        == 200
    )
    assert client.post("/api/v1/ai/runtime/install", headers=owner_headers).status_code == 201
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()

    pre_call_output = {
        "pre_call_summary": "First attempt for an eligible Atlanta owner record.",
        "priority_explanation": "The assigned record is due and has no prior attempts.",
        "property_context": ["Atlanta, Georgia", "Address has not been verified"],
        "prior_attempt_context": ["No prior attempts"],
        "opening_guidance": "Use the approved Stonegate opening and ask permission to continue.",
        "required_questions": [
            "Reason for selling",
            "Timeline",
            "Property condition",
            "Occupancy",
        ],
        "disposition_guidance": ["Record only the outcome the caller observes."],
        "data_quality_warnings": ["Phone and address validation remain unverified."],
        "compliance_reminders": [
            "Honor a stop request immediately.",
            "Do not imply an offer has been approved.",
        ],
        "evidence": ["queue.status", "prospect.eligibility", "script.approved_version"],
        "confidence": 84,
    }
    quality_output = {
        "call_summary": "The seller expressed interest and discussed the property.",
        "suggested_disposition": "interested",
        "disposition_reason": "The seller agreed to acquisitions follow-up.",
        "callback_recommendation": "Acquisitions should follow the accepted handoff.",
        "handoff_draft": "Review motivation, timing, condition, and occupancy.",
        "script_adherence_score": 91,
        "qualification_completeness_score": 100,
        "objection_handling_score": 78,
        "data_quality_score": 96,
        "handoff_quality_score": 88,
        "coaching_points": ["Confirm decision-maker authority earlier."],
        "compliance_flags": [],
        "evidence_timestamps": ["00:12-00:24", "01:05-01:20"],
        "confidence": 87,
    }

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_structured_response(
            self, **kwargs: object
        ) -> tuple[dict[str, Any], dict[str, int]]:
            schema = cast(dict[str, Any], kwargs["json_schema"])
            output = (
                quality_output
                if "call_summary" in cast(dict[str, Any], schema["properties"])
                else pre_call_output
            )
            return output, {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

    monkeypatch.setattr(
        "app.services.ai_runtime.OpenAIResponsesClient",
        FakeOpenAIResponsesClient,
    )
    assert (
        client.patch(
            "/api/v1/ai/runtime/policy",
            headers=owner_headers,
            json={"provider_status": "enabled"},
        ).status_code
        == 200
    )
    for capability_key in ("prospecting.prioritize", "call.quality_coach"):
        assert (
            client.patch(
                f"/api/v1/ai/runtime/capabilities/{capability_key}",
                headers=owner_headers,
                json={"status": "enabled", "model_route": "default"},
            ).status_code
            == 200
        )

    analysis = client.post(
        f"/api/v1/prospecting/entries/{entry_id}/copilot/analyze",
        headers=va_headers,
        json={},
    )
    assert analysis.status_code == 200, analysis.text
    recommendation = analysis.json()["recommendation"]
    assert recommendation["status"] == "draft"
    assert recommendation["output_payload"]["confidence"] == 84
    duplicate = client.post(
        f"/api/v1/prospecting/entries/{entry_id}/copilot/analyze",
        headers=va_headers,
        json={},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["recommendation"]["id"] == recommendation["id"]
    accepted = client.post(
        f"/api/v1/prospecting/copilot/recommendations/{recommendation['id']}/review",
        headers=va_headers,
        json={
            "decision": "accepted",
            "estimated_time_saved_seconds": 120,
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decision"] == "accepted"
    queue_entry = next(item for item in batch["entries"] if item["id"] == entry_id)
    prospect = db_session.get(Prospect, UUID(queue_entry["prospect_id"]))
    assert prospect is not None
    assert prospect.call_eligibility == "eligible"
    assert prospect.suppression_status != "suppressed"
    assert (
        db_session.scalar(select(func.count()).select_from(ProspectingCopilotRecommendation)) == 1
    )

    started = client.post(
        f"/api/v1/prospecting/entries/{entry_id}/start",
        headers=va_headers,
    )
    assert started.status_code == 200, started.text
    attempt_id = started.json()["active_attempt"]["id"]
    completed = client.post(
        f"/api/v1/prospecting/attempts/{attempt_id}/complete",
        headers=va_headers,
        json={
            "outcome": "interested",
            "handoff_user_id": acquisitions["id"],
            "qualification_answers": {
                "motivation": "Inherited property",
                "timeline": "Within 30 days",
                "property_condition": "Needs updating",
                "occupancy": "Vacant",
            },
        },
    )
    assert completed.status_code == 200, completed.text
    lead = db_session.scalar(select(Lead))
    conversation = db_session.scalar(select(Conversation))
    attempt = db_session.get(ProspectingAttempt, UUID(attempt_id))
    assert lead is not None and conversation is not None and attempt is not None
    now = datetime.now(UTC)
    call = CallRecord(
        organization_id=lead.organization_id,
        conversation_id=conversation.id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        actor_user_id=UUID(va["id"]),
        communication_record_id=None,
        voice_line_id=None,
        call_intent_id=None,
        provider="twilio",
        provider_call_id="CA-prospecting-ai5-test",
        child_provider_call_id=None,
        direction="outbound",
        status="completed",
        from_number="+14045550100",
        to_number="+14045550101",
        started_at=now,
        answered_at=now,
        ended_at=now,
        duration_seconds=120,
        disposition="interested",
        recording_consent_status="disclosed",
        call_metadata=None,
    )
    db_session.add(call)
    db_session.flush()
    recording = CallRecording(
        organization_id=lead.organization_id,
        call_record_id=call.id,
        provider="twilio",
        provider_recording_id="RE-prospecting-ai5-test",
        status="completed",
        media_reference="twilio://recordings/RE-prospecting-ai5-test",
        duration_seconds=120,
        channel_count=2,
        consent_status="disclosed",
        recorded_at=now,
        retention_expires_at=None,
        deleted_at=None,
        deleted_by_user_id=None,
        deletion_reason=None,
        recording_metadata=None,
    )
    db_session.add(recording)
    db_session.flush()
    transcript = CallTranscript(
        organization_id=lead.organization_id,
        recording_id=recording.id,
        provider="openai",
        model_name="gpt-4o-transcribe-diarize",
        status="approved",
        language="en",
        transcript_text="Caller: What has you considering selling? Seller: I inherited it.",
        speaker_segments=[
            {
                "speaker": "Caller",
                "start": 12.0,
                "end": 24.0,
                "text": "What has you considering selling?",
            },
            {
                "speaker": "Seller",
                "start": 25.0,
                "end": 35.0,
                "text": "I inherited it.",
            },
        ],
        confidence_score=94,
        approved_by_user_id=UUID(va["id"]),
        approved_at=now,
        error_message=None,
        transcript_metadata=None,
    )
    db_session.add(transcript)
    attempt.call_record_id = call.id
    db_session.commit()

    quality = client.post(
        f"/api/v1/prospecting/attempts/{attempt_id}/quality/analyze",
        headers=owner_headers,
    )
    assert quality.status_code == 200, quality.text
    assert quality.json()["quality_review"]["status"] == "needs_review"
    assert quality.json()["quality_review"]["ai_output"]["confidence"] == 87
    corrected_output = {
        **quality_output,
        "call_summary": "Manager-confirmed summary based on the approved transcript.",
        "objection_handling_score": 80,
    }
    approved = client.post(
        f"/api/v1/prospecting/attempts/{attempt_id}/quality/review",
        headers=owner_headers,
        json={
            "decision": "corrected",
            "final_output": corrected_output,
            "notes": "Compared with the approved transcript.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "corrected"
    assert approved.json()["final_output"]["objection_handling_score"] == 80
    db_session.refresh(attempt)
    assert attempt.outcome == "interested"
    assert attempt.notes is None
    get_settings.cache_clear()


def test_correction_reason_is_required(
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
        "/api/v1/prospecting/handoffs/00000000-0000-0000-0000-000000000001/decision",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"decision": "needs_correction"},
    )
    assert response.status_code == 422
