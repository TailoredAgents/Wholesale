from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import Buyer, BuyerDiscoveryCandidate, BuyerDiscoveryRun
from app.services import buyer_discovery
from tests.test_dispositions import HEADERS, approve_disposition_package, setup_case_foundation


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


class FakeDealMachineClient:
    def list_property_filters(self) -> list[object]:
        return [
            {
                "filter_id": "property_type",
                "options": [
                    {"option_id": 1, "label": "Single Family"},
                    {"option_id": 2, "label": "Multi-Family"},
                ],
            }
        ]

    def get_usage(self) -> dict[str, Any]:
        return {
            "plan": {"name": "Pro", "is_paid": True},
            "billing_cycle": {"end": "2026-09-01T00:00:00.000Z"},
            "credits": {
                "total_cap": 20000,
                "total_available": 19477,
                "used": 523,
            },
        }

    def estimate_property_search(self, request: dict[str, Any]) -> dict[str, Any]:
        assert request["anchor"] == "properties"
        assert request["contact_audience"] == "owners"
        assert request["filters"][-1] == {
            "filter_id": "property_type",
            "operator": "contains_any",
            "value": [1],
        }
        return {
            "totals": {"properties": 3, "people": 1},
            "pagination": {"total_results": 3},
            "estimated_credits": {
                "this_page": 4,
                "total_all_pages": 4,
                "breakdown": {"properties": 3, "people": 1},
            },
        }

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        assert request["locations"] == [{"type": "zip_code", "code": "30303"}]
        assert request["anchor"] == "properties"
        assert request["contact_audience"] == "owners"
        assert request["filters"][-1]["value"] == [1]
        assert request["filters"][0] == {
            "filter_id": "is_recently_sold",
            "value": True,
        }
        return {
            "data": [
                {
                    "dm_property_id": "prop_1",
                    "address": "101 First St",
                    "city": "Atlanta",
                    "state": "GA",
                    "zip": "30303",
                    "owner_1_full_name": "Peachtree Capital LLC",
                    "last_sale_date": "2026-07-01",
                    "last_sale_price": 185000,
                    "num_mortgages": 0,
                    "property_type": ["Single Family"],
                    "contacts": [
                        {
                            "full_name": "Peachtree Capital LLC",
                            "phones": [
                                {"number": "4045550199", "do_not_call": True},
                                {"number": "4045550101", "do_not_call": False},
                            ],
                            "emails": [{"address": "buyer@peachtree.example"}],
                        }
                    ],
                },
                {
                    "dm_property_id": "prop_2",
                    "address": "202 Second St",
                    "city": "Atlanta",
                    "state": "GA",
                    "zip": "30303",
                    "owner_1_full_name": "Peachtree Capital, LLC",
                    "last_sale_date": "2026-06-15",
                    "last_sale_price": 205000,
                    "num_mortgages": 1,
                    "property_type": ["Single Family"],
                    "contacts": [],
                },
                {
                    "dm_property_id": "prop_3",
                    "address": "303 Third St",
                    "city": "Atlanta",
                    "state": "GA",
                    "zip": "30303",
                    "owner_1_full_name": "Taylor Investor",
                    "last_sale_date": "2026-04-01",
                    "last_sale_price": 165000,
                    "num_mortgages": 1,
                    "property_type": ["Single Family"],
                    "contacts": [],
                },
            ],
            "pagination": {"total_results": 3},
            "credits": {
                "used": 4,
                "properties": 3,
                "people": 1,
                "deduplicated": 0,
            },
        }


def _synthetic_import_run(
    db: Session,
    source: BuyerDiscoveryRun,
) -> BuyerDiscoveryRun:
    run = BuyerDiscoveryRun(
        organization_id=source.organization_id,
        disposition_case_id=source.disposition_case_id,
        requested_by_user_id=source.requested_by_user_id,
        provider=source.provider,
        status="completed",
        search_tier=source.search_tier,
        request_fingerprint="synthetic-import-review-fixtures",
        target_candidate_count=source.target_candidate_count,
        estimated_credit_cap=source.estimated_credit_cap,
        estimated_credits=0,
        actual_credits=0,
        search_snapshot={"test_fixture": "import review scenarios"},
        provider_request={"test_fixture": True},
        result_count=0,
        imported_count=0,
        credit_summary={
            "used": 0,
            "properties": 0,
            "people": 0,
            "deduplicated": 0,
        },
        error_message=None,
        completed_at=datetime.now(UTC),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _clone_discovery_candidate(
    db: Session,
    source: BuyerDiscoveryCandidate,
    run: BuyerDiscoveryRun,
    **changes: object,
) -> BuyerDiscoveryCandidate:
    values: dict[str, object] = {
        "organization_id": source.organization_id,
        "discovery_run_id": run.id,
        "buyer_id": None,
        "provider": source.provider,
        "external_key": source.external_key,
        "name": source.name,
        "company_name": source.company_name,
        "email": source.email,
        "phone": source.phone,
        "market": source.market,
        "state": source.state,
        "property_types": deepcopy(source.property_types),
        "observed_purchase_count": source.observed_purchase_count,
        "no_mortgage_count": source.no_mortgage_count,
        "last_purchase_date": source.last_purchase_date,
        "min_purchase_price_cents": source.min_purchase_price_cents,
        "max_purchase_price_cents": source.max_purchase_price_cents,
        "score_basis_points": source.score_basis_points,
        "score_components": deepcopy(source.score_components),
        "evidence_snapshot": deepcopy(source.evidence_snapshot),
        "provider_snapshot": deepcopy(source.provider_snapshot),
        "status": "review",
        "imported_at": None,
    }
    values.update(changes)
    candidate = BuyerDiscoveryCandidate(**values)
    db.add(candidate)
    run.result_count += 1
    db.commit()
    db.refresh(candidate)
    return candidate


def test_dealmachine_discovery_imports_selected_candidate_and_deduplicates(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("BUYER_DATA_PROVIDER", "dealmachine")
    monkeypatch.setenv("DEALMACHINE_API_KEY", "dm_sk_live_test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        buyer_discovery,
        "DealMachineClient",
        lambda settings: FakeDealMachineClient(),
    )
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    case_response = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert case_response.status_code == 201, case_response.text
    case_id = case_response.json()["id"]

    provider = client.get("/api/v1/buyers/provider", headers=HEADERS)
    assert provider.status_code == 200
    assert provider.json()["configured"] is True

    readiness = client.get("/api/v1/buyers/provider/readiness", headers=HEADERS)
    assert readiness.status_code == 200
    assert readiness.json()["connected"] is True
    assert readiness.json()["plan_name"] == "Pro"
    assert readiness.json()["credits_remaining"] == 19477
    assert approve_disposition_package(client, case_id).status_code == 200

    estimate = client.post(
        "/api/v1/buyers/discovery-runs/estimate",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "search_tier": "best_fit",
            "max_candidates": 10,
        },
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["estimated_credits"] == 4
    assert estimate.json()["enough_credits"] is True
    request_fingerprint = estimate.json()["request_fingerprint"]

    stale_confirmation = client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "search_tier": "best_fit",
            "max_candidates": 10,
            "confirmed_estimated_credits": 3,
            "confirmed_request_fingerprint": request_fingerprint,
        },
    )
    assert stale_confirmation.status_code == 422
    assert "Preview the search again" in stale_confirmation.json()["detail"]

    discovery = client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "search_tier": "best_fit",
            "max_candidates": 10,
            "confirmed_estimated_credits": 4,
            "confirmed_request_fingerprint": request_fingerprint,
        },
    )
    assert discovery.status_code == 201, discovery.text
    payload = discovery.json()
    assert payload["result_count"] == 2
    assert payload["actual_credits"] == 4
    assert payload["credit_summary"]["used"] == 4
    assert payload["credit_summary"]["properties"] == 3
    assert payload["credit_summary"]["people"] == 1
    top = payload["candidates"][0]
    assert top["name"] == "Peachtree Capital LLC"
    assert top["observed_purchase_count"] == 2
    assert top["no_mortgage_count"] == 1
    assert top["email"] == "buyer@peachtree.example"
    assert top["phone"] == "4045550101"

    imported = client.post(
        f"/api/v1/buyers/discovery-runs/{payload['id']}/import",
        headers=HEADERS,
        json={"candidate_ids": [top["id"]]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported_count"] == 1
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 2
    imported_buyer_id = imported.json()["candidates"][0]["buyer_id"]
    imported_buyer = client.get(f"/api/v1/buyers/{imported_buyer_id}", headers=HEADERS)
    assert imported_buyer.status_code == 200
    assert imported_buyer.json()["status"] == "needs_review"
    assert imported_buyer.json()["source_key"] == "dealmachine"
    assert imported_buyer.json()["phone"] == "4045550101"
    assert imported_buyer.json()["normalized_phone"] == "+14045550101"
    activated = client.patch(
        f"/api/v1/buyers/{imported_buyer_id}",
        headers=HEADERS,
        json={"status": "active"},
    )
    assert activated.status_code == 200
    matches = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    ).json()["matches"]
    imported_match = next(item for item in matches if item["buyer_id"] == imported_buyer_id)
    assert imported_match["score_components"]["property_type"] == 0
    assert imported_match["qualification_status"] == "review_required"
    assert imported_match["recipient_status"] == "excluded"

    source_run = db_session.get(BuyerDiscoveryRun, UUID(payload["id"]))
    peachtree_source = db_session.get(BuyerDiscoveryCandidate, UUID(top["id"]))
    taylor_payload = next(
        candidate for candidate in payload["candidates"] if candidate["name"] == "Taylor Investor"
    )
    taylor_source = db_session.get(
        BuyerDiscoveryCandidate,
        UUID(taylor_payload["id"]),
    )
    assert source_run is not None
    assert peachtree_source is not None
    assert taylor_source is not None
    review_run = _synthetic_import_run(db_session, source_run)

    contact_duplicate_candidate = _clone_discovery_candidate(
        db_session,
        peachtree_source,
        review_run,
        provider="alternate_provider",
        external_key="alternate-contact-key",
        name="Different Buyer Name",
        company_name="Different Capital Group",
    )
    duplicate = client.post(
        f"/api/v1/buyers/discovery-runs/{review_run.id}/import",
        headers=HEADERS,
        json={"candidate_ids": [str(contact_duplicate_candidate.id)]},
    )
    assert duplicate.status_code == 200
    contact_duplicate_result = next(
        candidate
        for candidate in duplicate.json()["candidates"]
        if candidate["id"] == str(contact_duplicate_candidate.id)
    )
    assert contact_duplicate_result["status"] == "duplicate"
    assert contact_duplicate_result["buyer_id"] == imported_buyer_id

    canonical_buyer = db_session.get(Buyer, UUID(imported_buyer_id))
    assert canonical_buyer is not None
    source_duplicate_row = _clone_discovery_candidate(
        db_session,
        taylor_source,
        review_run,
        external_key=str(canonical_buyer.source_external_key),
    )
    source_duplicate = client.post(
        f"/api/v1/buyers/discovery-runs/{review_run.id}/import",
        headers=HEADERS,
        json={"candidate_ids": [str(source_duplicate_row.id)]},
    )
    assert source_duplicate.status_code == 200
    source_duplicate_result = next(
        candidate
        for candidate in source_duplicate.json()["candidates"]
        if candidate["id"] == str(source_duplicate_row.id)
    )
    assert source_duplicate_result["status"] == "duplicate"
    assert source_duplicate_result["buyer_id"] == imported_buyer_id

    no_contact_candidate = _clone_discovery_candidate(
        db_session,
        taylor_source,
        review_run,
    )
    quarantined = client.post(
        f"/api/v1/buyers/discovery-runs/{review_run.id}/import",
        headers=HEADERS,
        json={"candidate_ids": [str(no_contact_candidate.id)]},
    )
    assert quarantined.status_code == 200
    quarantined_candidate = next(
        candidate
        for candidate in quarantined.json()["candidates"]
        if candidate["id"] == str(no_contact_candidate.id)
    )
    assert quarantined_candidate["status"] == "needs_contact_review"
    assert quarantined_candidate["buyer_id"] is None
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryRun)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate)) or 0) == 5
    )

    name_only_candidate = _clone_discovery_candidate(
        db_session,
        peachtree_source,
        review_run,
        provider="different_provider",
        external_key="different-provider-contact",
        email="distinct-buyer@example.com",
        phone="6785550137",
    )
    assert name_only_candidate.name == "Peachtree Capital LLC"
    name_review = client.post(
        f"/api/v1/buyers/discovery-runs/{review_run.id}/import",
        headers=HEADERS,
        json={"candidate_ids": [str(name_only_candidate.id)]},
    )
    assert name_review.status_code == 200
    reviewed_candidate = next(
        candidate
        for candidate in name_review.json()["candidates"]
        if candidate["id"] == str(name_only_candidate.id)
    )
    assert reviewed_candidate["status"] == "needs_duplicate_review"
    assert reviewed_candidate["buyer_id"] is None
    assert reviewed_candidate["evidence_snapshot"]["duplicate_review"]["reason"] == (
        "name_or_company_match_only"
    )
    assert (
        imported_buyer_id
        in reviewed_candidate["evidence_snapshot"]["duplicate_review"]["possible_buyer_ids"]
    )
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 2
    assert int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryRun)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate)) or 0) == 6
    )

    shared_email = "shared-legacy-identity@example.com"
    first_legacy = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": "Legacy Identity One",
            "email": shared_email,
            "phone": "4045550141",
        },
    )
    assert first_legacy.status_code == 201, first_legacy.text
    second_legacy = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": "Legacy Identity Two",
            "email": shared_email,
            "phone": "4045550142",
            "allow_separate_record": True,
            "separate_record_reason": (
                "Legacy records intentionally share a company mailbox pending review."
            ),
        },
    )
    assert second_legacy.status_code == 201, second_legacy.text

    ambiguous_candidate = _clone_discovery_candidate(
        db_session,
        peachtree_source,
        review_run,
        provider="ambiguous_provider",
        external_key="ambiguous-strong-identity",
        name="Distinct Discovery Candidate",
        company_name="Distinct Discovery Company",
        email=shared_email,
        phone="6785550197",
    )

    ambiguous_review = client.post(
        f"/api/v1/buyers/discovery-runs/{review_run.id}/import",
        headers=HEADERS,
        json={"candidate_ids": [str(ambiguous_candidate.id)]},
    )
    assert ambiguous_review.status_code == 200, ambiguous_review.text
    ambiguous_result = next(
        candidate
        for candidate in ambiguous_review.json()["candidates"]
        if candidate["id"] == str(ambiguous_candidate.id)
    )
    assert ambiguous_result["status"] == "needs_duplicate_review"
    assert ambiguous_result["buyer_id"] is None
    assert ambiguous_result["evidence_snapshot"]["duplicate_review"]["reason"] == (
        "ambiguous_strong_identity"
    )
    assert set(ambiguous_result["evidence_snapshot"]["duplicate_review"]["possible_buyer_ids"]) == {
        first_legacy.json()["id"],
        second_legacy.json()["id"],
    }
    db_session.refresh(ambiguous_candidate)
    assert ambiguous_candidate.imported_at is None
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 4
    assert int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryRun)) or 0) == 2
    assert (
        int(db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate)) or 0) == 7
    )
    get_settings.cache_clear()
