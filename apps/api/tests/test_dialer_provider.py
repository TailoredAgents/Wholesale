import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    ProspectingAttempt,
    ProspectingProviderContact,
    ProspectingProviderEvent,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
VA_EMAIL = "dialer-va@example.com"


def create_multi_line_batch(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    user_response = client.post(
        "/api/v1/operations/users",
        headers=headers,
        json={
            "email": VA_EMAIL,
            "display_name": "Dialer VA",
            "role_key": "prospecting_caller",
        },
    )
    assert user_response.status_code == 201, user_response.text
    user = cast(dict[str, Any], user_response.json())
    market_response = client.post(
        "/api/v1/operations/markets",
        headers=headers,
        json={
            "name": "Atlanta Dialer Market",
            "code": "atlanta-dialer-market",
            "state_code": "GA",
            "timezone": "America/New_York",
            "is_primary": True,
        },
    )
    assert market_response.status_code == 201, market_response.text
    campaign_response = client.post(
        "/api/v1/operations/campaigns",
        headers=headers,
        json={
            "market_id": market_response.json()["id"],
            "name": "Dialer Pilot",
            "code": "dialer-pilot",
            "channel": "cold_call",
        },
    )
    assert campaign_response.status_code == 201, campaign_response.text
    campaign = campaign_response.json()
    cohort_response = client.post(
        "/api/v1/campaign-management/cohorts",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "name": "Dialer Simulation Cohort",
            "code": "dialer-simulation-cohort",
            "source_name": "PropStream",
            "list_type": "absentee_high_equity",
            "market_label": "Atlanta Metro",
            "dialer_mode": "multi_line_parallel",
            "call_window_start_hour": 9,
            "call_window_end_hour": 17,
            "timezone": "America/New_York",
            "starts_on": "2026-07-30",
        },
    )
    assert cohort_response.status_code == 201, cohort_response.text
    cohort = cohort_response.json()
    mapping_response = client.post(
        "/api/v1/campaign-management/import-mappings",
        headers=headers,
        json={
            "name": "Dialer Simulation Import",
            "source_name": "PropStream",
            "field_mapping": {
                "source_record_key": "ID",
                "legal_name": "Owner",
                "phone": "Phone",
                "street_address": "Address",
                "city": "City",
                "state_code": "State",
                "postal_code": "ZIP",
            },
        },
    )
    assert mapping_response.status_code == 201, mapping_response.text
    import_response = client.post(
        "/api/v1/campaign-management/imports",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "mapping_id": mapping_response.json()["id"],
            "cohort_id": cohort["id"],
            "default_assignee_user_id": user["id"],
            "file_name": "dialer-simulation.csv",
            "csv_content": (
                "ID,Owner,Phone,Address,City,State,ZIP\n"
                "1,First Seller,4045550101,101 Main St,Atlanta,GA,30303\n"
                "2,Second Seller,4045550102,102 Main St,Atlanta,GA,30303\n"
                "3,Third Seller,4045550103,103 Main St,Atlanta,GA,30303\n"
            ),
        },
    )
    assert import_response.status_code == 201, import_response.text
    batch_response = client.post(
        "/api/v1/campaign-management/calling-batches",
        headers=headers,
        json={
            "campaign_id": campaign["id"],
            "import_batch_id": import_response.json()["id"],
            "cohort_id": cohort["id"],
            "dialer_mode": "multi_line_parallel",
            "assigned_user_id": user["id"],
            "name": "Simulated Multi-Line Batch",
            "maximum_records": 100,
        },
    )
    assert batch_response.status_code == 201, batch_response.text
    return cast(dict[str, Any], batch_response.json()), user


def approve_script(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/prospecting/scripts",
        headers=headers,
        json={
            "title": "Provider Pilot Script",
            "opening_script": "Hi, this is Stonegate Home Buyers calling about your property.",
            "qualification_questions": [
                {
                    "key": "motivation",
                    "label": "Motivation",
                    "prompt": "What has you considering selling?",
                    "required_for_handoff": True,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    approval = client.post(
        f"/api/v1/prospecting/scripts/{response.json()['id']}/approve",
        headers=headers,
    )
    assert approval.status_code == 200, approval.text


def test_simulated_provider_campaign_is_idempotent_and_reconciled(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("DIALER_PROVIDER", "batchdialer")
    monkeypatch.setenv("DIALER_PROVIDER_MODE", "simulate")
    get_settings.cache_clear()
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    owner_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    va_headers = {"X-Dev-User-Email": VA_EMAIL}
    batch, _ = create_multi_line_batch(client, owner_headers)
    approve_script(client, owner_headers)

    restricted = client.post(
        f"/api/v1/campaign-management/calling-batches/{batch['id']}/provider-sync",
        headers=va_headers,
    )
    assert restricted.status_code == 403
    sync_response = client.post(
        f"/api/v1/campaign-management/calling-batches/{batch['id']}/provider-sync",
        headers=owner_headers,
    )
    assert sync_response.status_code == 200, sync_response.text
    sync = sync_response.json()
    assert sync["status"] == "ready"
    assert sync["eligible_contact_count"] == 3
    assert sync["synced_contact_count"] == 3
    assert sync["provider_campaign_id"].startswith("sim-campaign-")
    assert (
        db_session.scalar(select(func.count()).select_from(ProspectingProviderContact)) == 3
    )

    simulation = client.post(
        f"/api/v1/campaign-management/provider-syncs/{sync['id']}/simulate",
        headers=owner_headers,
    )
    assert simulation.status_code == 200, simulation.text
    assert simulation.json()["status"] == "reconciled"
    assert db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) == 3
    assert db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) == 6

    replay = client.post(
        f"/api/v1/campaign-management/provider-syncs/{sync['id']}/simulate",
        headers=owner_headers,
    )
    assert replay.status_code == 200, replay.text
    assert db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) == 3
    assert db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) == 6
    overview = client.get("/api/v1/campaign-management", headers=owner_headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["dialer_provider"]["live_mapping_status"] == "simulation_ready"
    assert overview.json()["dialer_syncs"][0]["status"] == "reconciled"
    get_settings.cache_clear()


def test_live_webhook_requires_signature_and_deduplicates(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    secret = "test-webhook-secret"
    monkeypatch.setenv("DIALER_PROVIDER", "batchdialer")
    monkeypatch.setenv("DIALER_PROVIDER_MODE", "simulate")
    get_settings.cache_clear()
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    batch, _ = create_multi_line_batch(client, headers)
    approve_script(client, headers)
    sync_response = client.post(
        f"/api/v1/campaign-management/calling-batches/{batch['id']}/provider-sync",
        headers=headers,
    )
    sync = sync_response.json()
    contact = db_session.scalar(select(ProspectingProviderContact))
    assert contact is not None

    monkeypatch.setenv("DIALER_PROVIDER_MODE", "live")
    monkeypatch.setenv("BATCHDIALER_WEBHOOK_SECRET", secret)
    get_settings.cache_clear()
    payload = {
        "external_event_id": "live-event-1",
        "event_type": "call.completed",
        "provider_campaign_id": sync["provider_campaign_id"],
        "provider_contact_id": contact.provider_contact_id,
        "provider_call_id": "live-call-1",
        "provider_agent_id": VA_EMAIL,
        "occurred_at": datetime.now(UTC).isoformat(),
        "outcome": "not_interested",
        "duration_seconds": 42,
        "metadata": {"fixture": True},
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    url = f"/api/v1/webhooks/dialer/{foundation.organization.id}"
    invalid = client.post(url, content=raw, headers={"Content-Type": "application/json"})
    assert invalid.status_code == 401
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    accepted = client.post(
        url,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Stonegate-Dialer-Signature": f"sha256={signature}",
        },
    )
    assert accepted.status_code == 200, accepted.text
    duplicate = client.post(
        url,
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Stonegate-Dialer-Signature": f"sha256={signature}",
        },
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["id"] == accepted.json()["id"]
    assert db_session.scalar(select(func.count()).select_from(ProspectingAttempt)) == 1
    assert db_session.scalar(select(func.count()).select_from(ProspectingProviderEvent)) == 1

    failed_payload = {
        **payload,
        "external_event_id": "live-event-unsupported",
        "provider_call_id": "live-call-unsupported",
        "outcome": "provider_custom_outcome",
    }
    failed_raw = json.dumps(failed_payload, separators=(",", ":")).encode()
    failed_signature = hmac.new(secret.encode(), failed_raw, hashlib.sha256).hexdigest()
    failed = client.post(
        url,
        content=failed_raw,
        headers={
            "Content-Type": "application/json",
            "X-Stonegate-Dialer-Signature": f"sha256={failed_signature}",
        },
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["processing_status"] == "failed"
    assert "Unsupported provider disposition" in failed.json()["error_message"]
    retry = client.post(
        f"/api/v1/campaign-management/provider-events/{failed.json()['id']}/retry",
        headers=headers,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["processing_status"] == "failed"
    assert retry.json()["retry_count"] == 1
    overview = client.get("/api/v1/campaign-management", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["dialer_syncs"][0]["failed_event_count"] == 1
    get_settings.cache_clear()
