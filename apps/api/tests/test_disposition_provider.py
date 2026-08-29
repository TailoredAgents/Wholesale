import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.disposition_provider import (
    ManualInvestorLiftAdapter,
    ProviderTransportUnavailableError,
)
from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerOffer,
    DispositionBuyerSelection,
    DispositionPackageVersion,
    DispositionProviderEvidence,
    DispositionProviderSourceLink,
    DispositionProviderSyncRun,
)
from app.services.bootstrap import bootstrap_foundation
from tests.test_dispositions import (
    HEADERS,
    add_user_with_role,
    approve_disposition_package,
    create_approved_disposition_case,
    setup_case_foundation,
)


def test_investorlift_adapter_is_manual_only_and_refuses_unverified_transport() -> None:
    adapter = ManualInvestorLiftAdapter()
    capabilities = adapter.capabilities

    assert capabilities.provider_key == "investorlift"
    assert capabilities.mode == "manual"
    assert capabilities.api_contract_verified is False
    assert capabilities.live_transport_enabled is False
    assert capabilities.credential_required is False
    assert "approved_package_export" in capabilities.supported_manual_capabilities
    assert "property_publish_api" in capabilities.unverified_capabilities
    assert capabilities.blockers

    payload = adapter.build_public_listing_payload(
        package_version=3,
        package_approved_at="2026-08-28T12:00:00+00:00",
        package_snapshot={"property": {"city": "Atlanta", "state": "GA"}},
    )
    assert payload == adapter.build_public_listing_payload(
        package_version=3,
        package_approved_at="2026-08-28T12:00:00+00:00",
        package_snapshot={"property": {"city": "Atlanta", "state": "GA"}},
    )
    assert payload["handoff_mode"] == "manual"

    with pytest.raises(ProviderTransportUnavailableError, match="direct API contract"):
        adapter.publish(payload)


def _create_disposition_case(client: TestClient, transaction_id: str) -> str:
    response = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19_000_000,
            "minimum_acceptable_cents": 18_000_000,
            "desired_assignment_fee_cents": 4_000_000,
            "operating_mode_key": "human_led",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _prepare_provider_revision(client: TestClient, case_id: str) -> dict[str, Any]:
    workspace = client.get(
        f"/api/v1/dispositions/cases/{case_id}/provider",
        headers=HEADERS,
    )
    assert workspace.status_code == 200, workspace.text
    revisions = workspace.json()["revisions"]
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions",
        headers=HEADERS,
        json={
            "expected_latest_revision": max(
                (item["revision_number"] for item in revisions),
                default=0,
            )
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def _approve_provider_revision(
    client: TestClient,
    case_id: str,
    workspace: dict[str, Any],
) -> dict[str, Any]:
    revision = workspace["revisions"][0]
    response = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{revision['id']}/approve"
        ),
        headers=HEADERS,
        json={
            "expected_lock_version": revision["lock_version"],
            "attestation": True,
            "reason": "Reviewed the exact public-only provider handoff for manual publication.",
        },
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _record_provider_link(
    client: TestClient,
    case_id: str,
    workspace: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    listing = workspace["listing"]
    revision = workspace["revisions"][0]
    payload: dict[str, Any] = {
        "revision_id": revision["id"],
        "expected_listing_version": listing["lock_version"],
        "external_property_id": "IL-DS8-ATL-900",
        "external_url": "https://admin.investorlift.com/properties/IL-DS8-ATL-900",
        "provider_status": "active",
        "note": "Manually published from the exact approved Stonegate bundle.",
    }
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-link",
        headers=HEADERS,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()), payload


def _ready_manual_provider_case(
    db: Session,
    client: TestClient,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    _, transaction_id, _ = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    prepared = _prepare_provider_revision(client, case_id)
    approved = _approve_provider_revision(client, case_id, prepared)
    linked, link_payload = _record_provider_link(client, case_id, approved)
    return case_id, linked, link_payload


def _record_offer_evidence(
    client: TestClient,
    case_id: str,
    *,
    amount_cents: int = 20_500_000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload: dict[str, Any] = {
        "event_type": "offer",
        "external_event_id": "investorlift-offer-DS8-001",
        "occurred_at": "2026-08-28T15:45:00-04:00",
        "buyer_name": "Staged Provider Buyer",
        "buyer_email": "staged-provider-buyer@example.com",
        "buyer_phone": "+14045550188",
        "offer_amount_cents": amount_cents,
        "message": "Manual evidence only; no buyer decision was made.",
        "metadata": {"capture_method": "manual_review", "buyer_score": 81},
    }
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-events",
        headers=HEADERS,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json()), payload


def test_provider_release_requires_current_approved_package_and_is_public_only(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    case_id = _create_disposition_case(client, transaction_id)

    initial = client.get(
        f"/api/v1/dispositions/cases/{case_id}/provider",
        headers=HEADERS,
    )
    assert initial.status_code == 200, initial.text
    assert initial.headers["cache-control"] == "private, no-store"
    assert initial.json()["eligible"] is True
    assert initial.json()["verification_gate"] == {
        "provider_key": "investorlift",
        "mode": "manual",
        "api_contract_verified": False,
        "live_transport_enabled": False,
        "credential_required": False,
        "house_only": True,
        "blockers": initial.json()["verification_gate"]["blockers"],
        "supported_manual_capabilities": initial.json()["verification_gate"][
            "supported_manual_capabilities"
        ],
        "unverified_capabilities": initial.json()["verification_gate"][
            "unverified_capabilities"
        ],
    }
    assert initial.json()["account"] is None
    blocked = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions",
        headers=HEADERS,
        json={"expected_latest_revision": 0},
    )
    assert blocked.status_code == 422
    assert "approved" in blocked.json()["detail"].lower()

    approved_package = approve_disposition_package(client, case_id)
    assert approved_package.status_code == 200, approved_package.text
    package = db_session.get(
        DispositionPackageVersion,
        UUID(approved_package.json()["id"]),
    )
    assert package is not None
    private_values = {
        "seller": "PRIVATE-SELLER-DS8",
        "floor": "PRIVATE-FLOOR-DS8",
        "basis": "PRIVATE-PURCHASE-BASIS-DS8",
        "fee": "PRIVATE-ASSIGNMENT-FEE-DS8",
    }
    package.public_snapshot = {
        **package.public_snapshot,
        "seller_name": private_values["seller"],
        "property": {
            **package.public_snapshot["property"],
            "seller_phone": private_values["seller"],
            "mortgage_balance": private_values["basis"],
        },
        "pricing": {
            **package.public_snapshot["pricing"],
            "minimum_acceptable_cents": private_values["floor"],
            "purchase_price_cents": private_values["basis"],
            "desired_assignment_fee_cents": private_values["fee"],
        },
    }
    db_session.commit()

    first = _prepare_provider_revision(client, case_id)
    first_revision = first["revisions"][0]
    serialized = json.dumps(first_revision["public_payload"], sort_keys=True)
    for forbidden in private_values.values():
        assert forbidden not in serialized
    for forbidden_key in (
        "seller_name",
        "seller_phone",
        "mortgage_balance",
        "minimum_acceptable_cents",
        "purchase_price_cents",
        "desired_assignment_fee_cents",
    ):
        assert forbidden_key not in serialized

    second = _prepare_provider_revision(client, case_id)
    second_revision = second["revisions"][0]
    assert second_revision["revision_number"] == 2
    assert second_revision["public_payload"] == first_revision["public_payload"]
    assert second_revision["public_payload_sha256"] == first_revision["public_payload_sha256"]
    assert second["revisions"][1]["status"] == "superseded"

    draft_bundle = client.get(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{second_revision['id']}/bundle"
        ),
        headers=HEADERS,
    )
    assert draft_bundle.status_code == 422
    released = _approve_provider_revision(client, case_id, second)
    released_revision = released["revisions"][0]
    bundle = client.get(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{released_revision['id']}/bundle"
        ),
        headers=HEADERS,
    )
    assert bundle.status_code == 200, bundle.text
    assert bundle.headers["cache-control"] == "private, no-store"
    assert bundle.headers["content-type"].startswith("application/json")
    bundle_payload = bundle.json()
    assert bundle_payload["manifest"]["public_payload_sha256"] == released_revision[
        "public_payload_sha256"
    ]
    assert bundle_payload["public_payload"] == released_revision["public_payload"]
    assert all(value not in bundle.text for value in private_values.values())


def test_manual_link_and_external_event_replays_are_idempotent_and_conflicts_are_rejected(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, linked, link_payload = _ready_manual_provider_case(db_session, client)
    listing_id = UUID(linked["listing"]["id"])
    initial_listing_version = linked["listing"]["lock_version"]

    # Retry the exact request as a client would after losing the first response.
    replay = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-link",
        headers=HEADERS,
        json=link_payload,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["listing"]["lock_version"] == initial_listing_version
    assert (
        db_session.scalar(
            select(func.count(DispositionProviderSourceLink.id)).where(
                DispositionProviderSourceLink.listing_id == listing_id
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(DispositionProviderSyncRun.id)).where(
                DispositionProviderSyncRun.listing_id == listing_id,
                DispositionProviderSyncRun.operation == "manual_link",
            )
        )
        == 1
    )

    event_workspace, event_payload = _record_offer_evidence(client, case_id)
    evidence = event_workspace["staged_events"][0]
    assert evidence["review_status"] == "staged"
    assert evidence["selection_eligible"] is False
    event_replay = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-events",
        headers=HEADERS,
        json=event_payload,
    )
    assert event_replay.status_code == 201, event_replay.text
    assert len(event_replay.json()["staged_events"]) == 1
    assert event_replay.json()["staged_events"][0]["id"] == evidence["id"]
    assert (
        db_session.scalar(
            select(func.count(DispositionProviderEvidence.id)).where(
                DispositionProviderEvidence.listing_id == listing_id
            )
        )
        == 1
    )

    conflict_payload = {**event_payload, "offer_amount_cents": 20_600_000}
    conflict = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-events",
        headers=HEADERS,
        json=conflict_payload,
    )
    assert conflict.status_code == 422
    assert "different evidence" in conflict.json()["detail"].lower()

    private_metadata = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-events",
        headers=HEADERS,
        json={
            "event_type": "inquiry",
            "external_event_id": "investorlift-inquiry-private-DS8",
            "occurred_at": "2026-08-28T16:00:00-04:00",
            "message": "Public inquiry evidence.",
            "metadata": {"minimum_acceptable_cents": 18_000_000},
        },
    )
    assert private_metadata.status_code == 422
    assert "private field" in private_metadata.json()["detail"].lower()


def test_new_provider_revision_supersedes_every_prior_release_and_blocks_stale_actions(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    case_id = create_approved_disposition_case(client, transaction_id)

    first_draft = _prepare_provider_revision(client, case_id)
    first_approved = _approve_provider_revision(client, case_id, first_draft)
    first_revision = first_approved["revisions"][0]
    first_bundle = client.get(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{first_revision['id']}/bundle"
        ),
        headers=HEADERS,
    )
    assert first_bundle.status_code == 200, first_bundle.text

    second_draft = _prepare_provider_revision(client, case_id)
    latest_revision, prior_revision = second_draft["revisions"][:2]
    assert latest_revision["revision_number"] == 2
    assert latest_revision["status"] == "draft"
    assert prior_revision["id"] == first_revision["id"]
    assert prior_revision["status"] == "superseded"
    assert second_draft["listing"]["approved_revision_id"] is None

    stale_approval = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{first_revision['id']}/approve"
        ),
        headers=HEADERS,
        json={
            "expected_lock_version": prior_revision["lock_version"],
            "attestation": True,
            "reason": "A superseded release must never become current again.",
        },
    )
    assert stale_approval.status_code == 422
    assert "latest" in stale_approval.json()["detail"].lower()

    stale_bundle = client.get(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{first_revision['id']}/bundle"
        ),
        headers=HEADERS,
    )
    assert stale_bundle.status_code == 422
    assert "approval" in stale_bundle.json()["detail"].lower()

    stale_link = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-link",
        headers=HEADERS,
        json={
            "revision_id": first_revision["id"],
            "expected_listing_version": second_draft["listing"]["lock_version"],
            "external_property_id": "IL-STALE-DS8",
            "external_url": "https://admin.investorlift.com/properties/IL-STALE-DS8",
            "provider_status": "active",
            "note": "A superseded release must not be linked.",
        },
    )
    assert stale_link.status_code == 422
    assert "approved" in stale_link.json()["detail"].lower()

    second_approved = _approve_provider_revision(client, case_id, second_draft)
    current_revision = second_approved["revisions"][0]
    assert current_revision["id"] == latest_revision["id"]
    assert current_revision["status"] == "approved"
    assert second_approved["revisions"][1]["status"] == "superseded"
    current_bundle = client.get(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{current_revision['id']}/bundle"
        ),
        headers=HEADERS,
    )
    assert current_bundle.status_code == 200, current_bundle.text


def test_staged_provider_offer_review_never_creates_or_selects_a_buyer(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _ready_manual_provider_case(db_session, client)
    before = {
        "buyers": db_session.scalar(select(func.count(Buyer.id))),
        "offers": db_session.scalar(select(func.count(BuyerOffer.id))),
        "selections": db_session.scalar(select(func.count(DispositionBuyerSelection.id))),
    }
    event_workspace, _ = _record_offer_evidence(client, case_id)
    evidence = event_workspace["staged_events"][0]

    reviewed = client.patch(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-events/{evidence['id']}",
        headers=HEADERS,
        json={
            "expected_lock_version": evidence["lock_version"],
            "review_status": "reviewed",
            "review_note": "Reviewed as provider evidence only; no buyer decision authorized.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    reviewed_evidence = reviewed.json()["staged_events"][0]
    assert reviewed_evidence["review_status"] == "reviewed"
    assert reviewed_evidence["selection_eligible"] is False
    assert {
        "buyers": db_session.scalar(select(func.count(Buyer.id))),
        "offers": db_session.scalar(select(func.count(BuyerOffer.id))),
        "selections": db_session.scalar(select(func.count(DispositionBuyerSelection.id))),
    } == before


def test_provider_routes_enforce_scoped_rbac_and_tenant_isolation(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, linked, _ = _ready_manual_provider_case(db_session, client)
    event_workspace, _ = _record_offer_evidence(client, case_id)
    evidence = event_workspace["staged_events"][0]
    revision = linked["revisions"][0]

    viewer = add_user_with_role(
        db_session,
        email="ds8-viewer@example.com",
        display_name="DS8 Viewer",
        role_key="read_only_partner",
    )
    viewer_headers = {"X-Dev-User-Email": viewer.email}
    assert (
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/provider",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/provider/export?format=json",
            headers=viewer_headers,
        ).status_code
        == 200
    )
    forbidden_prepare = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions",
        headers=viewer_headers,
        json={"expected_latest_revision": 1},
    )
    assert forbidden_prepare.status_code == 403

    representative = add_user_with_role(
        db_session,
        email="ds8-representative@example.com",
        display_name="DS8 Representative",
        role_key="disposition_rep",
    )
    rep_headers = {"X-Dev-User-Email": representative.email}
    representative_prepare = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions",
        headers=rep_headers,
        json={"expected_latest_revision": 1},
    )
    assert representative_prepare.status_code == 201, representative_prepare.text
    rep_revision = representative_prepare.json()["revisions"][0]
    representative_approval = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
            f"{rep_revision['id']}/approve"
        ),
        headers=rep_headers,
        json={
            "expected_lock_version": rep_revision["lock_version"],
            "attestation": True,
            "reason": "A representative cannot approve the exact release.",
        },
    )
    assert representative_approval.status_code == 403

    other = bootstrap_foundation(
        db_session,
        organization_name="Other DS8 Organization",
        admin_email="other-ds8-owner@example.com",
        admin_name="Other DS8 Owner",
    )
    assert other.admin_user is not None
    other_headers = {"X-Dev-User-Email": other.admin_user.email}
    requests = [
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/provider",
            headers=other_headers,
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions",
            headers=other_headers,
            json={"expected_latest_revision": 0},
        ),
        client.post(
            (
                f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
                f"{revision['id']}/approve"
            ),
            headers=other_headers,
            json={
                "expected_lock_version": revision["lock_version"],
                "attestation": True,
                "reason": "Cross-tenant approval must not reveal provider records.",
            },
        ),
        client.get(
            (
                f"/api/v1/dispositions/cases/{case_id}/provider/listing-revisions/"
                f"{revision['id']}/bundle"
            ),
            headers=other_headers,
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/provider/manual-events",
            headers=other_headers,
            json={
                "event_type": "inquiry",
                "external_event_id": "cross-tenant-event",
                "occurred_at": datetime.now(UTC).isoformat(),
                "message": "Must remain hidden.",
            },
        ),
        client.patch(
            f"/api/v1/dispositions/cases/{case_id}/provider/manual-events/{evidence['id']}",
            headers=other_headers,
            json={
                "expected_lock_version": evidence["lock_version"],
                "review_status": "dismissed",
                "review_note": "Cross-tenant review must not reveal provider records.",
            },
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/provider/manual-refresh",
            headers=other_headers,
            json={"provider_status": "active"},
        ),
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/provider/disconnect",
            headers=other_headers,
            json={
                "attestation": True,
                "reason": "Cross-tenant disconnect must not reveal provider records.",
            },
        ),
        client.get(
            f"/api/v1/dispositions/cases/{case_id}/provider/export?format=json",
            headers=other_headers,
        ),
    ]
    assert all(response.status_code == 404 for response in requests), [
        (response.status_code, response.text) for response in requests
    ]


def test_disconnect_preserves_provider_history_and_exports_without_private_economics(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, linked, _ = _ready_manual_provider_case(db_session, client)
    event_workspace, _ = _record_offer_evidence(client, case_id)
    listing_id = UUID(linked["listing"]["id"])
    refreshed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-refresh",
        headers=HEADERS,
        json={
            "provider_status": "paused",
            "note": "Manually observed paused status before disconnect.",
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["listing"]["provider_status"] == "paused"
    counts_before_disconnect = {
        "links": db_session.scalar(
            select(func.count(DispositionProviderSourceLink.id)).where(
                DispositionProviderSourceLink.listing_id == listing_id
            )
        ),
        "events": db_session.scalar(
            select(func.count(DispositionProviderEvidence.id)).where(
                DispositionProviderEvidence.listing_id == listing_id
            )
        ),
    }

    disconnected = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/disconnect",
        headers=HEADERS,
        json={
            "attestation": True,
            "reason": "Provider access cancelled; preserve the complete Stonegate record.",
        },
    )
    assert disconnected.status_code == 200, disconnected.text
    body = disconnected.json()
    assert body["listing"]["status"] == "disconnected"
    assert body["listing"]["disconnect_reason"]
    assert body["revisions"]
    assert body["source_links"]
    assert body["staged_events"]

    assert {
        "links": db_session.scalar(
            select(func.count(DispositionProviderSourceLink.id)).where(
                DispositionProviderSourceLink.listing_id == listing_id
            )
        ),
        "events": db_session.scalar(
            select(func.count(DispositionProviderEvidence.id)).where(
                DispositionProviderEvidence.listing_id == listing_id
            )
        ),
    } == counts_before_disconnect

    blocked_refresh = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-refresh",
        headers=HEADERS,
        json={"provider_status": "active"},
    )
    assert blocked_refresh.status_code == 422
    assert "disconnected" in blocked_refresh.json()["detail"].lower()

    stale_link_payload = {
        "revision_id": body["listing"]["approved_revision_id"],
        "expected_listing_version": body["listing"]["lock_version"],
        "external_property_id": "IL-DS8-ATL-900",
        "external_url": "https://admin.investorlift.com/properties/IL-DS8-ATL-900",
        "provider_status": "active",
        "note": "A disconnected handoff cannot be silently reactivated.",
    }
    blocked_link = client.post(
        f"/api/v1/dispositions/cases/{case_id}/provider/manual-link",
        headers=HEADERS,
        json=stale_link_payload,
    )
    assert blocked_link.status_code == 422
    assert "disconnected" in blocked_link.json()["detail"].lower()

    json_export = client.get(
        f"/api/v1/dispositions/cases/{case_id}/provider/export?format=json",
        headers=HEADERS,
    )
    assert json_export.status_code == 200, json_export.text
    exported = json_export.json()
    assert exported["history_preserved"] is True
    assert exported["contains_private_stonegate_economics"] is False
    assert exported["listing"]["status"] == "disconnected"
    assert exported["source_links"]
    assert exported["evidence"]
    for forbidden in (
        "minimum_acceptable_cents",
        "purchase_price_cents",
        "desired_assignment_fee_cents",
    ):
        assert forbidden not in json_export.text

    csv_export = client.get(
        f"/api/v1/dispositions/cases/{case_id}/provider/export?format=csv",
        headers=HEADERS,
    )
    assert csv_export.status_code == 200, csv_export.text
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "listing_revision" in csv_export.text
    assert "source_link" in csv_export.text
    assert "evidence_offer" in csv_export.text
    assert event_workspace["staged_events"][0]["evidence_sha256"] in csv_export.text
