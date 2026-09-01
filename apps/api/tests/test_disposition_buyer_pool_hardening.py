from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    BuyerProofDocument,
    BuyerSourceLink,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionCampaign,
    DispositionCampaignRecipient,
    DispositionMatch,
    User,
)
from tests.test_dispositions import (
    HEADERS,
    OWNER_EMAIL,
    create_approved_disposition_case,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)


def _ready_case(
    db: Session,
    client: TestClient,
) -> tuple[str, str, dict[str, Any]]:
    _, transaction_id, buyer_id = setup_case_foundation(db, client)
    case_id = create_approved_disposition_case(client, transaction_id)
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    return case_id, buyer_id, proof


def _create_ready_buyer(
    client: TestClient,
    *,
    name: str,
    email: str,
) -> str:
    created = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": name,
            "email": email,
            "buyer_type": "cash_buyer",
            "status": "active",
            "max_purchase_price_cents": 30000000,
            "criteria": {
                "markets": "Atlanta, GA",
                "property_types": "single_family",
                "max_price_cents": 30000000,
            },
        },
    )
    assert created.status_code == 201, created.text
    buyer_id = created.json()["id"]
    activated = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=HEADERS,
        json={"status": "active"},
    )
    assert activated.status_code == 200, activated.text
    put_verified_buy_box(client, buyer_id)
    proof = upload_received_proof(client, buyer_id)
    verify_proof(client, proof["id"])
    return buyer_id


def _add_external_candidate(
    db: Session,
    *,
    case_id: str,
    external_key: str,
    name: str = "External Candidate",
    email: str = "external-candidate@example.com",
    phone: str = "404-555-0199",
    created_at: datetime | None = None,
) -> BuyerDiscoveryCandidate:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    discovery_run = BuyerDiscoveryRun(
        organization_id=owner.organization_id,
        disposition_case_id=UUID(case_id),
        requested_by_user_id=owner.id,
        provider="dealmachine",
        status="completed",
        search_snapshot={"state": "GA", "asset_class": "house"},
        provider_request={"hardening_test": True},
        result_count=1,
        imported_count=0,
        credit_summary={"properties": 1, "people": 0},
        completed_at=datetime.now(UTC),
    )
    db.add(discovery_run)
    db.flush()
    candidate = BuyerDiscoveryCandidate(
        organization_id=owner.organization_id,
        discovery_run_id=discovery_run.id,
        buyer_id=None,
        provider="dealmachine",
        external_key=external_key,
        name=name,
        company_name=f"{name} LLC",
        email=email,
        phone=phone,
        market="Atlanta, GA",
        state="GA",
        property_types=["single_family"],
        observed_purchase_count=8,
        no_mortgage_count=6,
        last_purchase_date=date.today() - timedelta(days=30),
        min_purchase_price_cents=10000000,
        max_purchase_price_cents=30000000,
        score_basis_points=7200,
        score_components={"observed_activity": 7200},
        evidence_snapshot={"source": "recorded_purchase_activity"},
        provider_snapshot={"provider_id": external_key},
        status="review",
        **({"created_at": created_at} if created_at is not None else {}),
    )
    db.add(candidate)
    db.commit()
    return candidate


def _refresh(client: TestClient, case_id: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-pool/runs",
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _decide(
    client: TestClient,
    *,
    case_id: str,
    candidate_id: str,
    expected_version: int,
    decision_status: str,
    lifecycle_stage: str | None = None,
    reason: str | None = None,
):
    payload: dict[str, object] = {
        "expected_version": expected_version,
        "decision_status": decision_status,
    }
    if lifecycle_stage is not None:
        payload["lifecycle_stage"] = lifecycle_stage
    if reason is not None:
        payload["reason"] = reason
    return client.patch(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{candidate_id}"
        ),
        headers=HEADERS,
        json=payload,
    )


def test_durable_deal_pass_excludes_campaign_until_explicit_clear(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, first_buyer_id, _ = _ready_case(db_session, client)
    second_buyer_id = _create_ready_buyer(
        client,
        name="Second Current Buyer",
        email="second-current-buyer@example.com",
    )

    first_run = _refresh(client, case_id)
    first_entry = next(
        item for item in first_run["entries"] if item["buyer_id"] == first_buyer_id
    )
    historical_pass = _decide(
        client,
        case_id=case_id,
        candidate_id=first_entry["candidate_id"],
        expected_version=first_entry["lock_version"],
        decision_status="passed",
        reason="Persistent deal Pass used to verify ranking-independent exclusion.",
    )
    assert historical_pass.status_code == 200, historical_pass.text

    latest = _refresh(client, case_id)
    latest_run_id = UUID(latest["run"]["id"])
    stale_entry = next(
        item for item in latest["entries"] if item["buyer_id"] == first_buyer_id
    )
    current_entry = next(
        item for item in latest["entries"] if item["buyer_id"] == second_buyer_id
    )
    db_session.execute(
        delete(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == latest_run_id,
            DispositionBuyerPoolEntry.buyer_pool_candidate_id
            == UUID(stale_entry["candidate_id"]),
        )
    )
    db_session.commit()
    released_with_durable_pass = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released_with_durable_pass.status_code == 200, released_with_durable_pass.text
    first_campaign = db_session.scalar(
        select(DispositionCampaign)
        .where(DispositionCampaign.disposition_case_id == UUID(case_id))
        .order_by(DispositionCampaign.created_at.desc(), DispositionCampaign.id.desc())
    )
    assert first_campaign is not None
    assert set(
        db_session.scalars(
            select(DispositionCampaignRecipient.buyer_id).where(
                DispositionCampaignRecipient.disposition_campaign_id == first_campaign.id
            )
        ).all()
    ) == {UUID(second_buyer_id)}

    passed = _decide(
        client,
        case_id=case_id,
        candidate_id=current_entry["candidate_id"],
        expected_version=current_entry["lock_version"],
        decision_status="passed",
        reason="The current run explicitly excludes this buyer.",
    )
    assert passed.status_code == 200, passed.text

    released_with_every_buyer_passed = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released_with_every_buyer_passed.status_code == 422
    assert "non-suppressed buyers" in released_with_every_buyer_passed.json()["detail"]

    passed_entry = next(
        item
        for item in passed.json()["entries"]
        if item["candidate_id"] == current_entry["candidate_id"]
    )
    cleared = _decide(
        client,
        case_id=case_id,
        candidate_id=current_entry["candidate_id"],
        expected_version=passed_entry["lock_version"],
        decision_status="undecided",
        reason="The rep cleared the prior pass after the buyer re-engaged.",
    )
    assert cleared.status_code == 200, cleared.text
    restored = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert restored.status_code == 200, restored.text
    campaign_ids = list(
        db_session.scalars(
            select(DispositionCampaign.id).where(
                DispositionCampaign.disposition_case_id == UUID(case_id)
            )
        ).all()
    )
    recipient_sets = {
        frozenset(
            db_session.scalars(
                select(DispositionCampaignRecipient.buyer_id).where(
                    DispositionCampaignRecipient.disposition_campaign_id == campaign_id
                )
            ).all()
        )
        for campaign_id in campaign_ids
    }
    # The first buyer remains durably passed even though its latest-run entry was removed.
    assert frozenset({UUID(second_buyer_id)}) in recipient_sets

    cleared_historical = _decide(
        client,
        case_id=case_id,
        candidate_id=stale_entry["candidate_id"],
        expected_version=stale_entry["lock_version"],
        decision_status="undecided",
        reason="The rep explicitly cleared the durable Pass outside rank membership.",
    )
    assert cleared_historical.status_code == 200, cleared_historical.text
    fully_restored = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert fully_restored.status_code == 200, fully_restored.text
    all_campaign_ids = db_session.scalars(
        select(DispositionCampaign.id).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    ).all()
    all_recipient_sets = {
        frozenset(
            db_session.scalars(
                select(DispositionCampaignRecipient.buyer_id).where(
                    DispositionCampaignRecipient.disposition_campaign_id == campaign_id
                )
            ).all()
        )
        for campaign_id in all_campaign_ids
    }
    assert frozenset({UUID(first_buyer_id), UUID(second_buyer_id)}) in all_recipient_sets


def test_canonical_latest_pool_buyer_can_enter_campaign_without_legacy_match(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    latest = _refresh(client, case_id)
    assert any(item["buyer_id"] == buyer_id for item in latest["entries"])
    db_session.execute(
        delete(DispositionMatch).where(
            DispositionMatch.disposition_case_id == UUID(case_id)
        )
    )
    db_session.commit()

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    campaign = db_session.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign is not None
    assert list(
        db_session.scalars(
            select(DispositionCampaignRecipient.buyer_id).where(
                DispositionCampaignRecipient.disposition_campaign_id == campaign.id
            )
        ).all()
    ) == [UUID(buyer_id)]

def test_decision_on_candidate_absent_from_latest_run_is_rejected(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    pool = _refresh(client, case_id)
    entry = next(item for item in pool["entries"] if item["buyer_id"] == buyer_id)
    db_session.execute(
        delete(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == UUID(pool["run"]["id"]),
            DispositionBuyerPoolEntry.buyer_pool_candidate_id == UUID(entry["candidate_id"]),
        )
    )
    db_session.commit()

    response = _decide(
        client,
        case_id=case_id,
        candidate_id=entry["candidate_id"],
        expected_version=entry["lock_version"],
        decision_status="shortlisted",
    )

    assert response.status_code == 422, response.text
    assert "latest" in response.json()["detail"].lower()
    db_session.expire_all()
    candidate = db_session.get(
        DispositionBuyerPoolCandidate,
        UUID(entry["candidate_id"]),
    )
    assert candidate is not None
    assert candidate.decision_status == "undecided"


def test_contradictory_decision_and_lifecycle_are_rejected(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    pool = _refresh(client, case_id)
    entry = next(item for item in pool["entries"] if item["buyer_id"] == buyer_id)

    response = _decide(
        client,
        case_id=case_id,
        candidate_id=entry["candidate_id"],
        expected_version=entry["lock_version"],
        decision_status="shortlisted",
        lifecycle_stage="pass",
        reason="This contradictory state must be rejected.",
    )

    assert response.status_code == 422, response.text
    db_session.expire_all()
    candidate = db_session.get(
        DispositionBuyerPoolCandidate,
        UUID(entry["candidate_id"]),
    )
    assert candidate is not None
    assert candidate.decision_status == "undecided"
    assert candidate.lifecycle_stage == "discovered"


def test_stale_conversion_creates_no_buyer_or_source_link(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="stale-conversion",
    )
    pool = _refresh(client, case_id)
    entry = next(item for item in pool["entries"] if item["source_type"] == "external")
    buyer_count = int(db_session.scalar(select(func.count(Buyer.id))) or 0)
    link_count = int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0)
    updated = _decide(
        client,
        case_id=case_id,
        candidate_id=entry["candidate_id"],
        expected_version=entry["lock_version"],
        decision_status="shortlisted",
    )
    assert updated.status_code == 200, updated.text

    stale = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{entry['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": entry["lock_version"],
            "decision": "create_new",
            "reason": "A stale conversion must not create partial records.",
        },
    )

    assert stale.status_code == 422, stale.text
    assert "another session" in stale.json()["detail"]
    assert int(db_session.scalar(select(func.count(Buyer.id))) or 0) == buyer_count
    assert int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0) == link_count


def test_link_existing_keeps_one_canonical_candidate_and_rerun_succeeds(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="link-existing-canonical",
        name="Different Provider Identity",
        email="different-provider-identity@example.com",
        phone="470-555-0111",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")

    linked = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": external["lock_version"],
            "decision": "link_existing",
            "existing_buyer_id": buyer_id,
            "reason": "Human review confirmed this is the existing buyer.",
        },
    )
    assert linked.status_code == 200, linked.text
    assert (
        db_session.scalar(
            select(func.count(DispositionBuyerPoolCandidate.id)).where(
                DispositionBuyerPoolCandidate.disposition_case_id == UUID(case_id),
                DispositionBuyerPoolCandidate.buyer_id == UUID(buyer_id),
            )
        )
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count(BuyerSourceLink.id)).where(
                BuyerSourceLink.buyer_id == UUID(buyer_id),
                BuyerSourceLink.provider == "dealmachine",
                BuyerSourceLink.external_key == "link-existing-canonical",
            )
        )
        == 1
    )

    rerun = _refresh(client, case_id)
    assert len(
        [item for item in rerun["entries"] if item["buyer_id"] == buyer_id]
    ) == 1


def test_source_link_resolves_rediscovered_provider_key_after_contact_changes(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="stable-provider-key",
        name="Original Provider Name",
        email="original-provider@example.com",
        phone="470-555-0122",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")
    linked = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": external["lock_version"],
            "decision": "link_existing",
            "existing_buyer_id": buyer_id,
            "reason": "Provider identity belongs to the existing buyer.",
        },
    )
    assert linked.status_code == 200, linked.text
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="stable-provider-key",
        name="Completely Changed Provider Name",
        email="changed-provider@example.net",
        phone="678-555-0198",
        created_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    rediscovered = _refresh(client, case_id)
    same_buyer_entries = [
        item for item in rediscovered["entries"] if item["buyer_id"] == buyer_id
    ]

    assert len(same_buyer_entries) == 1
    assert not any(
        item["source_type"] == "external"
        and item["provider"] == "dealmachine"
        and item["external_key"] == "stable-provider-key"
        for item in rediscovered["entries"]
    )
    assert any(
        evidence.get("type") == "provider_purchase_evidence"
        and evidence.get("external_key") == "stable-provider-key"
        for evidence in same_buyer_entries[0]["supporting_evidence"]
    )


def test_proof_snapshot_remains_self_contained_after_proof_is_changed_and_deleted(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, proof_payload = _ready_case(db_session, client)
    pool = _refresh(client, case_id)
    run_id = UUID(pool["run"]["id"])
    entry = db_session.scalar(
        select(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == run_id,
            DispositionBuyerPoolEntry.buyer_id == UUID(buyer_id),
        )
    )
    proof = db_session.get(BuyerProofDocument, UUID(proof_payload["id"]))
    assert entry is not None and proof is not None
    proof_snapshot = deepcopy(entry.evidence_snapshot["proof"])
    assert proof_snapshot["id"] == str(proof.id)
    assert proof_snapshot["status"] == "verified"
    assert proof_snapshot["verified_amount_cents"] == 40000000
    assert proof_snapshot["verified_by_user_id"] == str(proof.verified_by_user_id)
    assert proof_snapshot["verified_at"] == proof.verified_at.isoformat()
    assert proof_snapshot["expires_at"] == proof.expires_at.isoformat()
    assert proof_snapshot["verification_source"] == proof.verification_source
    assert proof_snapshot["malware_scan_status"] == proof.malware_scan_status
    assert proof_snapshot["sha256"] == proof.sha256

    proof.status = "rejected"
    proof.verified_amount_cents = 1
    proof.verified_by_user_id = None
    proof.verified_at = None
    proof.deleted_at = datetime.now(UTC)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(DispositionBuyerPoolEntry, entry.id)

    assert stored is not None
    assert stored.evidence_snapshot["proof"] == proof_snapshot


def test_evidence_refresh_bumps_lock_version_and_rejects_stale_decision(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _ready_case(db_session, client)
    discovery = _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="evidence-version",
        email="evidence-v1@example.com",
    )
    first = _refresh(client, case_id)
    before = next(item for item in first["entries"] if item["source_type"] == "external")

    discovery.email = "evidence-v2@example.com"
    discovery.observed_purchase_count = 14
    discovery.evidence_snapshot = {
        "source": "recorded_purchase_activity",
        "revision": 2,
    }
    db_session.commit()
    second = _refresh(client, case_id)
    after = next(
        item
        for item in second["entries"]
        if item["candidate_id"] == before["candidate_id"]
    )

    assert after["lock_version"] > before["lock_version"]
    stale = _decide(
        client,
        case_id=case_id,
        candidate_id=before["candidate_id"],
        expected_version=before["lock_version"],
        decision_status="shortlisted",
    )
    assert stale.status_code == 422, stale.text
    assert "another session" in stale.json()["detail"]


def test_converting_shortlisted_external_candidate_does_not_gate_other_pool_buyers(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, existing_buyer_id, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="shortlist-conversion-boundary",
        email="shortlist-conversion-boundary@example.com",
        phone="470-555-0137",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")
    shortlisted = _decide(
        client,
        case_id=case_id,
        candidate_id=external["candidate_id"],
        expected_version=external["lock_version"],
        decision_status="shortlisted",
    )
    assert shortlisted.status_code == 200, shortlisted.text
    reviewed = next(
        item
        for item in shortlisted.json()["entries"]
        if item["candidate_id"] == external["candidate_id"]
    )

    converted = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": reviewed["lock_version"],
            "decision": "create_new",
            "reason": "Human review approved this shortlisted provider identity.",
        },
    )
    assert converted.status_code == 200, converted.text
    converted_entry = next(
        item
        for item in converted.json()["entries"]
        if item["candidate_id"] == external["candidate_id"]
    )
    assert converted_entry["decision_status"] == "shortlisted"
    assert converted_entry["lifecycle_stage"] == "shortlisted"
    assert converted_entry["eligibility_status"] == "review_required"

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    assert existing_buyer_id != converted_entry["buyer_id"]
    campaign = db_session.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign is not None
    assert set(
        db_session.scalars(
            select(DispositionCampaignRecipient.buyer_id).where(
                DispositionCampaignRecipient.disposition_campaign_id == campaign.id
            )
        ).all()
    ) == {UUID(existing_buyer_id), UUID(converted_entry["buyer_id"])}


def test_conversion_without_shortlist_can_still_enter_campaign(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, existing_buyer_id, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="approval-conversion-boundary",
        email="approval-conversion-boundary@example.com",
        phone="470-555-0138",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")

    converted = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": external["lock_version"],
            "decision": "create_new",
            "reason": "Approve the identity, but do not shortlist it for release yet.",
        },
    )
    assert converted.status_code == 200, converted.text
    converted_entry = next(
        item
        for item in converted.json()["entries"]
        if item["candidate_id"] == external["candidate_id"]
    )

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    campaign = db_session.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign is not None
    assert set(
        db_session.scalars(
            select(DispositionCampaignRecipient.buyer_id).where(
                DispositionCampaignRecipient.disposition_campaign_id == campaign.id
            )
        ).all()
    ) == {UUID(existing_buyer_id), UUID(converted_entry["buyer_id"])}


def test_run_snapshot_preserves_raw_capacity_activity_and_reliability_inputs(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.max_purchase_price_cents = 28765432
    buyer.last_verified_at = datetime(2026, 8, 1, 12, 30, tzinfo=UTC)
    buyer.reliability_score_basis_points = 4321
    db_session.commit()
    db_session.refresh(buyer)
    expected_last_verified_at = buyer.last_verified_at.isoformat()

    pool = _refresh(client, case_id)
    entry = db_session.scalar(
        select(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == UUID(pool["run"]["id"]),
            DispositionBuyerPoolEntry.buyer_id == UUID(buyer_id),
        )
    )
    assert entry is not None
    score_inputs = deepcopy(entry.evidence_snapshot["score_inputs"])
    assert score_inputs == {
        "buyer_max_purchase_price_cents": 28765432,
        "buy_box_available_capital_cents": None,
        "effective_capacity_limit_cents": 28765432,
        "last_verified_at": expected_last_verified_at,
        "activity_window_days": 180,
        "reliability_score_basis_points": 4321,
    }

    buyer.max_purchase_price_cents = 1
    buyer.last_verified_at = None
    buyer.reliability_score_basis_points = 0
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(DispositionBuyerPoolEntry, entry.id)
    assert stored is not None
    assert stored.evidence_snapshot["score_inputs"] == score_inputs


def test_conversion_integrity_race_rolls_back_without_partial_records(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="provider-link-race",
        email="provider-link-race@example.com",
        phone="470-555-0139",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")
    buyer_count = int(db_session.scalar(select(func.count(Buyer.id))) or 0)
    link_count = int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0)

    def fail_commit() -> None:
        raise IntegrityError(
            "INSERT INTO buyer_source_links",
            {},
            Exception("unique provider identity"),
        )

    monkeypatch.setattr(db_session, "commit", fail_commit)
    response = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": external["lock_version"],
            "decision": "create_new",
            "reason": "Exercise the provider-identity uniqueness race boundary.",
        },
    )

    assert response.status_code == 422, response.text
    assert "linked by another request" in response.json()["detail"]
    assert int(db_session.scalar(select(func.count(Buyer.id))) or 0) == buyer_count
    assert int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0) == link_count


def test_source_link_flush_race_rolls_back_before_later_queries(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    case_id, _, _ = _ready_case(db_session, client)
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="provider-link-flush-race",
        email="provider-link-flush-race@example.com",
        phone="470-555-0140",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")
    buyer_count = int(db_session.scalar(select(func.count(Buyer.id))) or 0)
    link_count = int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0)
    original_flush = db_session.flush

    def fail_source_link_flush(objects: Any | None = None) -> None:
        if any(isinstance(item, BuyerSourceLink) for item in db_session.new):
            raise IntegrityError(
                "INSERT INTO buyer_source_links",
                {},
                Exception("unique provider identity"),
            )
        original_flush(objects)

    monkeypatch.setattr(db_session, "flush", fail_source_link_flush)
    response = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": external["lock_version"],
            "decision": "create_new",
            "reason": "Exercise the source-link flush uniqueness boundary.",
        },
    )

    assert response.status_code == 422, response.text
    assert "linked by another request" in response.json()["detail"]
    assert int(db_session.scalar(select(func.count(Buyer.id))) or 0) == buyer_count
    assert int(db_session.scalar(select(func.count(BuyerSourceLink.id))) or 0) == link_count


def test_zero_available_capital_does_not_fall_back_to_buyer_capacity(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, buyer_id, _ = _ready_case(db_session, client)
    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    assert buyer.max_purchase_price_cents is not None
    assert buyer.max_purchase_price_cents > 0
    zero_capacity = client.put(
        f"/api/v1/buyers/{buyer_id}/buy-boxes/house",
        headers=HEADERS,
        json={
            "expected_version": 1,
            "source": "buyer_interview",
            "change_reason": "Buyer reported no currently available acquisition capital.",
            "verification_status": "verified",
            "criteria": {
                "asset_class": "house",
                "geographies": [
                    {"jurisdiction": "city", "value": "Atlanta", "state": "GA"}
                ],
                "strategies": ["wholesale_assignment"],
                "min_price_cents": 10000000,
                "max_price_cents": 30000000,
                "funding_methods": ["cash"],
                "capacity": {"available_capital_cents": 0},
                "property_types": ["single_family"],
            },
        },
    )
    assert zero_capacity.status_code == 200, zero_capacity.text

    pool = _refresh(client, case_id)
    entry = db_session.scalar(
        select(DispositionBuyerPoolEntry).where(
            DispositionBuyerPoolEntry.buyer_pool_run_id == UUID(pool["run"]["id"]),
            DispositionBuyerPoolEntry.buyer_id == UUID(buyer_id),
        )
    )
    assert entry is not None
    assert entry.score_components["capacity"] == 0
    assert entry.evidence_snapshot["score_inputs"]["buy_box_available_capital_cents"] == 0
    assert entry.evidence_snapshot["score_inputs"]["effective_capacity_limit_cents"] == 0


def test_shortlisted_link_existing_dedupes_identity_without_gating_other_buyers(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id, canonical_buyer_id, _ = _ready_case(db_session, client)
    other_buyer_id = _create_ready_buyer(
        client,
        name="Other Qualified Recipient",
        email="other-qualified-recipient@example.com",
    )
    _add_external_candidate(
        db_session,
        case_id=case_id,
        external_key="shortlisted-link-recipient",
        name="Provider Identity For Canonical Buyer",
        email="provider-link-recipient@example.com",
        phone="470-555-0141",
    )
    pool = _refresh(client, case_id)
    external = next(item for item in pool["entries"] if item["source_type"] == "external")
    shortlisted = _decide(
        client,
        case_id=case_id,
        candidate_id=external["candidate_id"],
        expected_version=external["lock_version"],
        decision_status="shortlisted",
    )
    assert shortlisted.status_code == 200, shortlisted.text
    reviewed = next(
        item
        for item in shortlisted.json()["entries"]
        if item["candidate_id"] == external["candidate_id"]
    )
    linked = client.post(
        (
            f"/api/v1/dispositions/cases/{case_id}/buyer-pool/candidates/"
            f"{external['candidate_id']}/conversion"
        ),
        headers=HEADERS,
        json={
            "expected_version": reviewed["lock_version"],
            "decision": "link_existing",
            "existing_buyer_id": canonical_buyer_id,
            "reason": "Human review confirmed the canonical Buyer Network identity.",
        },
    )
    assert linked.status_code == 200, linked.text
    canonical_entry = next(
        item
        for item in linked.json()["entries"]
        if item["buyer_id"] == canonical_buyer_id
    )
    assert canonical_entry["decision_status"] == "shortlisted"

    released = client.post(
        f"/api/v1/dispositions/cases/{case_id}/campaigns/release",
        headers=HEADERS,
    )
    assert released.status_code == 200, released.text
    campaign = db_session.scalar(
        select(DispositionCampaign).where(
            DispositionCampaign.disposition_case_id == UUID(case_id)
        )
    )
    assert campaign is not None
    assert campaign.recipient_count == 2
    recipient_states = {
        str(match.buyer_id): match.recipient_status
        for match in db_session.scalars(
            select(DispositionMatch).where(
                DispositionMatch.disposition_case_id == UUID(case_id)
            )
        ).all()
    }
    assert recipient_states[canonical_buyer_id] == "prepared_not_sent"
    assert recipient_states[other_buyer_id] == "prepared_not_sent"
