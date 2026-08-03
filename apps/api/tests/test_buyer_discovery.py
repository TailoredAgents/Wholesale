from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import Buyer, BuyerDiscoveryCandidate, BuyerDiscoveryRun
from app.services import buyer_discovery
from tests.test_dispositions import HEADERS, setup_case_foundation


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
            "credits": {"properties": 3, "people": 1},
        }


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

    estimate = client.post(
        "/api/v1/buyers/discovery-runs/estimate",
        headers=HEADERS,
        json={"disposition_case_id": case_id, "max_candidates": 25},
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["estimated_credits"] == 4
    assert estimate.json()["enough_credits"] is True

    stale_confirmation = client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "max_candidates": 25,
            "confirmed_estimated_credits": 3,
        },
    )
    assert stale_confirmation.status_code == 422
    assert "Preview the search again" in stale_confirmation.json()["detail"]

    discovery = client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "max_candidates": 25,
            "confirmed_estimated_credits": 4,
        },
    )
    assert discovery.status_code == 201, discovery.text
    payload = discovery.json()
    assert payload["result_count"] == 2
    assert payload["credit_summary"] == {"properties": 3, "people": 1}
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
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve",
            headers=HEADERS,
        ).status_code
        == 200
    )
    matches = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    ).json()["matches"]
    imported_match = next(
        item for item in matches if item["buyer_id"] == imported_buyer_id
    )
    assert imported_match["score_components"]["property_type"] == 1000
    assert imported_match["qualification_status"] == "review_required"

    second_run = client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "max_candidates": 25,
            "confirmed_estimated_credits": 4,
        },
    ).json()
    duplicate = client.post(
        f"/api/v1/buyers/discovery-runs/{second_run['id']}/import",
        headers=HEADERS,
        json={"candidate_ids": [second_run["candidates"][0]["id"]]},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["candidates"][0]["status"] == "duplicate"
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 2
    assert int(
        db_session.scalar(select(func.count()).select_from(BuyerDiscoveryRun)) or 0
    ) == 2
    assert int(
        db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate))
        or 0
    ) == 4
    get_settings.cache_clear()
