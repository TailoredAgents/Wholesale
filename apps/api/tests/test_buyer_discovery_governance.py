from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.config import get_settings
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    BuyerDiscoveryCandidate,
    BuyerDiscoveryRun,
    DispositionCase,
    Lead,
    Property,
    Transaction,
    User,
)
from app.services import buyer_discovery
from tests.test_dispositions import (
    HEADERS,
    approve_disposition_package,
    setup_case_foundation,
)

TIER_POLICY = {
    "best_fit": (10, 30, 25),
    "expanded": (20, 60, 50),
    "regional": (40, 120, 100),
}


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def _property_record(
    index: int,
    *,
    name: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    buyer_name = name or f"Net New Buyer {index:03d} LLC"
    buyer_email = email or f"buyer-{index:03d}@example.com"
    return {
        "dm_property_id": f"tier-property-{index}",
        "address": f"{1000 + index} Tier Street",
        "city": "Atlanta",
        "state": "GA",
        "zip": "30303",
        "owner_1_full_name": buyer_name,
        "last_sale_date": "2026-08-01",
        "last_sale_price": 185000,
        "num_mortgages": 0,
        "property_type": ["Single Family"],
        "contacts": [
            {
                "full_name": buyer_name,
                "phones": [{"number": f"404555{index % 10000:04d}", "do_not_call": False}],
                "emails": [{"address": buyer_email}],
            }
        ],
    }


class TieredDealMachineClient:
    def __init__(self, *, estimated_by_tier: dict[str, int] | None = None) -> None:
        self.estimated_by_tier = {
            tier: values[2] for tier, values in TIER_POLICY.items()
        }
        if estimated_by_tier:
            self.estimated_by_tier.update(estimated_by_tier)
        self.search_calls: list[str] = []
        self.estimate_requests: list[dict[str, Any]] = []

    @staticmethod
    def list_property_filters() -> list[object]:
        return [
            {
                "filter_id": "property_type",
                "options": [{"option_id": 1, "label": "Single Family"}],
            }
        ]

    @staticmethod
    def get_usage() -> dict[str, Any]:
        return {
            "plan": {"name": "Pro", "is_paid": True},
            "billing_cycle": {"end": "2026-09-01T00:00:00.000Z"},
            "credits": {
                "total_cap": 20000,
                "total_available": 19000,
                "used": 1000,
            },
        }

    @staticmethod
    def _tier(request: dict[str, Any]) -> str:
        explicit = request.get("search_tier") or request.get("tier")
        if explicit in TIER_POLICY:
            return str(explicit)
        per_page = int(request.get("per_page") or 0)
        if per_page <= 10:
            return "best_fit"
        if per_page <= 20:
            return "expanded"
        return "regional"

    def estimate_property_search(self, request: dict[str, Any]) -> dict[str, Any]:
        tier = self._tier(request)
        self.estimate_requests.append(request)
        estimated = self.estimated_by_tier[tier]
        return {
            "totals": {"properties": 100, "people": 10},
            "pagination": {"total_results": 100},
            "estimated_credits": {
                "this_page": estimated,
                "total_all_pages": estimated,
                "breakdown": {"properties": max(estimated - 5, 0), "people": min(estimated, 5)},
            },
        }

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        tier = self._tier(request)
        self.search_calls.append(tier)
        stop = {"best_fit": 10, "expanded": 30, "regional": 70}[tier]
        estimated = self.estimated_by_tier[tier]
        owned_duplicate = _property_record(
            9999,
            name="Provider Alias For Owned Buyer",
            email="reliable-atlanta@example.com",
        )
        return {
            "data": [owned_duplicate, *[_property_record(index) for index in range(stop)]],
            "pagination": {"total_results": stop + 1},
            "credits": {
                "used": estimated,
                "properties": max(estimated - 5, 0),
                "people": min(estimated, 5),
                "deduplicated": 0,
            },
        }


class MissingCreditTelemetryClient(TieredDealMachineClient):
    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        response = super().search_properties(request)
        response.pop("credits")
        return response


class MalformedPreviewClient(TieredDealMachineClient):
    def __init__(self, failure: str) -> None:
        super().__init__(estimated_by_tier={"best_fit": 20})
        self.failure = failure

    def get_usage(self) -> dict[str, Any]:
        usage = super().get_usage()
        if self.failure == "balance":
            usage["credits"].pop("total_available")
        elif self.failure == "paid_plan":
            usage["plan"].pop("is_paid")
        return usage

    def estimate_property_search(self, request: dict[str, Any]) -> dict[str, Any]:
        estimate = super().estimate_property_search(request)
        if self.failure == "estimate":
            estimate["estimated_credits"].pop("this_page")
        elif self.failure == "negative_estimate":
            estimate["estimated_credits"]["this_page"] = -1
        return estimate


class PreviewUnderstatesLiveCostClient(TieredDealMachineClient):
    def __init__(self) -> None:
        super().__init__(estimated_by_tier={"best_fit": 20})

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        response = super().search_properties(request)
        response["credits"] = {
            "used": 28,
            "properties": 14,
            "people": 14,
            "deduplicated": 0,
        }
        return response


class LowBalanceClient(TieredDealMachineClient):
    def __init__(self) -> None:
        super().__init__(estimated_by_tier={"best_fit": 20})

    @staticmethod
    def get_usage() -> dict[str, Any]:
        usage = TieredDealMachineClient.get_usage()
        usage["credits"]["total_available"] = 25
        return usage


class CrashAfterProviderAcceptanceClient(TieredDealMachineClient):
    def __init__(self) -> None:
        super().__init__(estimated_by_tier={"best_fit": 20})

    def search_properties(self, request: dict[str, Any]) -> dict[str, Any]:
        self.search_calls.append(self._tier(request))
        raise RuntimeError("simulated process exit after provider acceptance")


def _configure_provider(monkeypatch: Any, provider_client: TieredDealMachineClient) -> None:
    monkeypatch.setenv("BUYER_DATA_PROVIDER", "dealmachine")
    monkeypatch.setenv("DEALMACHINE_API_KEY", "dm_sk_live_test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        buyer_discovery,
        "DealMachineClient",
        lambda settings: provider_client,
    )


def _create_case(
    db: Session,
    client: TestClient,
    *,
    approve: bool,
    coordinates: tuple[float, float] | None = None,
) -> str:
    _, transaction_id, _ = setup_case_foundation(db, client)
    response = client.post(
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
    assert response.status_code == 201, response.text
    case_id = str(response.json()["id"])
    if coordinates is not None:
        case = db.get(DispositionCase, UUID(case_id))
        assert case is not None
        property_record = db.get(Property, case.property_id)
        assert property_record is not None
        property_record.address_validation_metadata = {
            "facts": {
                "latitude": coordinates[0],
                "longitude": coordinates[1],
            }
        }
        db.commit()
    if approve:
        approval = approve_disposition_package(client, case_id)
        assert approval.status_code == 200, approval.text
    return case_id


def _create_additional_case(db: Session, client: TestClient) -> DispositionCase:
    lead_response = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {
                "legal_name": "Historical Monthly Budget Seller",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "901 Monthly Budget Lane",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "qualified",
        },
    )
    assert lead_response.status_code == 201, lead_response.text
    lead_id = UUID(lead_response.json()["id"])
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers=HEADERS,
        json={"purchase_price_cents": 15000000},
    )
    assert transaction_response.status_code == 201, transaction_response.text
    transaction_id = UUID(transaction_response.json()["transactions"][0]["id"])
    transaction = db.get(Transaction, transaction_id)
    lead = db.get(Lead, lead_id)
    assert transaction is not None and lead is not None
    transaction.status = "executed"
    lead.stage_key = "under_contract"
    db.commit()

    case_response = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": str(transaction_id),
            "strategy": "assignment",
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
            "operating_mode_key": "human_led",
        },
    )
    assert case_response.status_code == 201, case_response.text
    case = db.get(DispositionCase, UUID(case_response.json()["id"]))
    assert case is not None
    return case


def _preview(
    client: TestClient,
    case_id: str,
    tier: str,
    target_candidates: int,
) -> Any:
    return client.post(
        "/api/v1/buyers/discovery-runs/estimate",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "search_tier": tier,
            "max_candidates": target_candidates,
        },
    )


def _run(
    client: TestClient,
    case_id: str,
    tier: str,
    target_candidates: int,
    estimated_credits: int,
    request_fingerprint: str,
) -> Any:
    return client.post(
        "/api/v1/buyers/discovery-runs",
        headers=HEADERS,
        json={
            "disposition_case_id": case_id,
            "search_tier": tier,
            "max_candidates": target_candidates,
            "confirmed_estimated_credits": estimated_credits,
            "confirmed_request_fingerprint": request_fingerprint,
        },
    )


def _seed_completed_run(
    db: Session,
    case: DispositionCase,
    *,
    credits: int,
    search_tier: str | None = None,
) -> BuyerDiscoveryRun:
    run = BuyerDiscoveryRun(
        organization_id=case.organization_id,
        disposition_case_id=case.id,
        requested_by_user_id=case.owner_user_id,
        provider="dealmachine",
        status="completed",
        search_tier=search_tier,
        request_fingerprint=f"historical-{uuid4().hex}",
        target_candidate_count=TIER_POLICY[search_tier][0] if search_tier else None,
        estimated_credit_cap=TIER_POLICY[search_tier][1] if search_tier else None,
        estimated_credits=credits,
        actual_credits=credits,
        search_snapshot={"historical": True},
        provider_request={"historical": True},
        result_count=0,
        imported_count=0,
        credit_summary={
            "used": credits,
            "properties": credits,
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


def test_ds11_requires_package_approval_and_returns_governance_summary(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=False)

    blocked = _preview(client, case_id, "best_fit", 10)
    assert blocked.status_code == 422
    assert "approve" in blocked.json()["detail"].lower()
    assert provider_client.search_calls == []

    approval = approve_disposition_package(client, case_id)
    assert approval.status_code == 200, approval.text
    summary = client.get(
        "/api/v1/buyers/discovery-summary",
        headers=HEADERS,
        params={"case_id": case_id},
    )
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["completed_tiers"] == []
    assert payload["unlocked_tiers"] == ["best_fit"]
    assert payload["next_tier"] == "best_fit"
    assert payload["cumulative_case_credits"] == 0
    assert payload["cumulative_case_credit_cap"] == 250
    assert payload["monthly_credits"] == 0
    assert payload["monthly_credit_cap"] == 2000
    assert [
        (
            item["search_tier"],
            item["target_candidates"],
            item["estimated_credit_cap"],
            item["unlocked"],
        )
        for item in payload["tier_statuses"]
    ] == [
        ("best_fit", 10, 30, True),
        ("expanded", 20, 60, False),
        ("regional", 40, 120, False),
    ]


def test_ds11_legacy_request_without_tier_defaults_to_best_fit(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)

    preview = client.post(
        "/api/v1/buyers/discovery-runs/estimate",
        headers=HEADERS,
        json={"disposition_case_id": case_id},
    )

    assert preview.status_code == 200, preview.text
    assert preview.json()["requested_candidates"] == 10
    assert preview.json()["search_tier"] == "best_fit"
    assert preview.json()["target_candidates"] == 10
    assert preview.json()["provider_result_limit"] == 10


def test_ds11_preview_and_spend_require_buyer_and_deal_edit_permissions(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    owner = db_session.scalar(select(User).where(User.email == HEADERS["X-Dev-User-Email"]))
    assert owner is not None
    limited_principal = Principal(
        user_id=owner.id,
        organization_id=owner.organization_id,
        email=owner.email,
        permission_keys=frozenset(
            {
                PermissionKeys.VIEW_BUYERS,
                PermissionKeys.EDIT_BUYERS,
            }
        ),
    )
    app.dependency_overrides[get_current_principal] = lambda: limited_principal
    try:
        preview = _preview(client, case_id, "best_fit", 10)
        run = _run(client, case_id, "best_fit", 10, 0, "0" * 64)
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    assert preview.status_code == 403, preview.text
    assert preview.json()["detail"] == f"Missing permission: {PermissionKeys.EDIT_DEALS}"
    assert run.status_code == 403, run.text
    assert run.json()["detail"] == f"Missing permission: {PermissionKeys.EDIT_DEALS}"


def test_ds11_paid_run_is_bound_to_the_exact_preview_fingerprint(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text

    blocked = _run(
        client,
        case_id,
        "best_fit",
        10,
        preview.json()["estimated_credits"],
        "0" * 64,
    )

    assert blocked.status_code == 422, blocked.text
    assert "request changed" in blocked.json()["detail"].lower()
    assert provider_client.search_calls == []


def test_ds11_tiers_widen_geography_and_price_with_saved_coordinates(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(
        db_session,
        client,
        approve=True,
        coordinates=(33.749, -84.388),
    )
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None

    for tier, (target, _, _) in TIER_POLICY.items():
        preview = _preview(client, case_id, tier, target)
        assert preview.status_code == 200, preview.text
        _seed_completed_run(db_session, case, credits=0, search_tier=tier)

    requests = provider_client.estimate_requests
    assert [request["per_page"] for request in requests] == [10, 20, 40]
    assert requests[0]["locations"] == [{"type": "zip_code", "code": "30303"}]
    assert requests[1]["locations"] == [
        {
            "type": "radius",
            "latitude": 33.749,
            "longitude": -84.388,
            "radius_miles": 15,
        }
    ]
    assert requests[2]["locations"] == [
        {
            "type": "radius",
            "latitude": 33.749,
            "longitude": -84.388,
            "radius_miles": 50,
        }
    ]
    price_ranges = [
        next(
            item["value"]
            for item in request["filters"]
            if item["filter_id"] == "last_sale_price"
        )
        for request in requests
    ]
    assert [item["min"] for item in price_ranges] == [123500, 85500, 47500]
    assert [item["max"] for item in price_ranges] == [256500, 332500, 475000]


def test_ds11_tiers_use_bounded_fallback_when_coordinates_are_unavailable(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None

    for tier, (target, _, _) in TIER_POLICY.items():
        preview = _preview(client, case_id, tier, target)
        assert preview.status_code == 200, preview.text
        _seed_completed_run(db_session, case, credits=0, search_tier=tier)

    requests = provider_client.estimate_requests
    assert requests[0]["locations"] == [{"type": "zip_code", "code": "30303"}]
    assert requests[1]["locations"] == [{"type": "zip_code", "code": "30303"}]
    assert requests[2]["locations"] == [{"type": "state", "code": "GA"}]
    assert requests[0]["filters"] != requests[1]["filters"]
    assert requests[1]["filters"] != requests[2]["filters"]


def test_ds11_tiers_are_net_new_reused_and_reconciled_to_actual_credits(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    candidate_names_by_tier: dict[str, set[str]] = {}

    for index, (tier, (target, credit_cap, estimated)) in enumerate(TIER_POLICY.items()):
        preview = _preview(client, case_id, tier, target)
        assert preview.status_code == 200, preview.text
        estimate = preview.json()
        assert estimate["search_tier"] == tier
        assert estimate["requested_candidates"] == target
        assert estimate["target_candidates"] == target
        assert estimate["estimated_credit_cap"] == credit_cap
        assert estimate["estimated_credits"] == estimated
        assert estimate["estimated_cost_usd"] == pytest.approx(estimated * 0.0075)
        assert estimate["enough_credits"] is True

        response = _run(
            client,
            case_id,
            tier,
            target,
            estimated,
            estimate["request_fingerprint"],
        )
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["search_tier"] == tier
        assert run["target_candidates"] == target
        assert run["estimated_credit_cap"] == credit_cap
        assert run["estimated_credits"] == estimated
        assert run["actual_credits"] == estimated
        assert run["actual_cost_usd"] == pytest.approx(estimated * 0.0075)
        assert run["result_count"] == target
        assert run["reused"] is False
        assert run["reused_run_id"] is None
        names = {candidate["name"] for candidate in run["candidates"]}
        assert "Provider Alias For Owned Buyer" not in names
        assert all(names.isdisjoint(previous) for previous in candidate_names_by_tier.values())
        candidate_names_by_tier[tier] = names

        if index == 0:
            repeated = _run(
                client,
                case_id,
                tier,
                target,
                estimated,
                estimate["request_fingerprint"],
            )
            assert repeated.status_code == 201, repeated.text
            reused = repeated.json()
            assert reused["id"] == run["id"]
            assert reused["reused"] is True
            assert reused["reused_run_id"] == run["id"]
            assert provider_client.search_calls == ["best_fit"]

    assert provider_client.search_calls == ["best_fit", "expanded", "regional"]
    assert int(
        db_session.scalar(select(func.count()).select_from(BuyerDiscoveryRun)) or 0
    ) == 3
    assert int(
        db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate)) or 0
    ) == 70

    summary = client.get(
        "/api/v1/buyers/discovery-summary",
        headers=HEADERS,
        params={"case_id": case_id},
    )
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["completed_tiers"] == ["best_fit", "expanded", "regional"]
    assert payload["unlocked_tiers"] == ["best_fit", "expanded", "regional"]
    assert payload["next_tier"] is None
    assert payload["cumulative_case_credits"] == 175
    assert payload["monthly_credits"] == 175
    assert [item["latest_run"]["actual_credits"] for item in payload["tier_statuses"]] == [
        25,
        50,
        100,
    ]


def test_ds11_legacy_and_out_of_sequence_rows_do_not_unlock_paid_tiers(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = TieredDealMachineClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    _seed_completed_run(db_session, case, credits=0, search_tier=None)
    _seed_completed_run(db_session, case, credits=0, search_tier="expanded")

    summary = client.get(
        "/api/v1/buyers/discovery-summary",
        headers=HEADERS,
        params={"case_id": case_id},
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["completed_tiers"] == ["expanded"]
    assert summary.json()["unlocked_tiers"] == ["best_fit"]
    assert summary.json()["next_tier"] == "best_fit"

    blocked = _preview(client, case_id, "regional", 40)
    assert blocked.status_code == 422
    assert "best fit" in blocked.json()["detail"].lower()
    assert provider_client.estimate_requests == []


@pytest.mark.parametrize(
    ("failure", "message_fragment"),
    [
        ("estimate", "estimated credit"),
        ("negative_estimate", "estimated credit"),
        ("balance", "available-credit balance"),
        ("paid_plan", "paid api plan"),
    ],
)
def test_ds11_fails_closed_on_malformed_preview_or_usage_telemetry(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
    failure: str,
    message_fragment: str,
) -> None:
    provider_client = MalformedPreviewClient(failure)
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)

    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    assert preview.json()["enough_credits"] is False
    assert message_fragment in preview.json()["message"].lower()

    blocked = _run(
        client,
        case_id,
        "best_fit",
        10,
        0,
        preview.json()["request_fingerprint"],
    )
    assert blocked.status_code == 422
    assert message_fragment in blocked.json()["detail"].lower()
    assert provider_client.search_calls == []


def test_ds11_tier_cap_is_binding_when_preview_understates_live_owner_cost(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = PreviewUnderstatesLiveCostClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)

    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    estimate = preview.json()
    assert estimate["estimated_credits"] == 20
    assert estimate["estimated_credit_cap"] == 30
    assert estimate["enough_credits"] is True
    assert "binding authorization" in estimate["message"].lower()

    response = _run(
        client,
        case_id,
        "best_fit",
        10,
        20,
        estimate["request_fingerprint"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["actual_credits"] == 28
    assert response.json()["estimated_credits"] == 20
    assert response.json()["status"] == "completed"


def test_ds11_provider_balance_must_cover_the_full_tier_authorization(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = LowBalanceClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)

    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    assert preview.json()["estimated_credits"] == 20
    assert preview.json()["credits_remaining"] == 25
    assert preview.json()["enough_credits"] is False
    assert "authorized maximum of 30 credits" in preview.json()["message"].lower()
    assert provider_client.search_calls == []


def test_ds11_durable_running_reservation_prevents_crash_window_respend(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = CrashAfterProviderAcceptanceClient()
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    request_fingerprint = preview.json()["request_fingerprint"]

    with pytest.raises(RuntimeError, match="simulated process exit"):
        _run(client, case_id, "best_fit", 10, 20, request_fingerprint)

    db_session.expire_all()
    run = db_session.scalar(select(BuyerDiscoveryRun))
    assert run is not None
    assert run.status == "running"
    assert run.estimated_credits == 20
    assert run.estimated_credit_cap == 30

    replay = _run(client, case_id, "best_fit", 10, 20, request_fingerprint)
    assert replay.status_code == 422, replay.text
    assert "pending credit reconciliation" in replay.json()["detail"].lower()
    assert provider_client.search_calls == ["best_fit"]


@pytest.mark.parametrize(
    ("tier", "expected_target", "credit_cap", "completed_prerequisites"),
    [
        ("best_fit", 10, 30, []),
        ("expanded", 20, 60, ["best_fit"]),
        ("regional", 40, 120, ["best_fit", "expanded"]),
    ],
)
def test_ds11_rejects_estimates_above_each_tier_credit_ceiling(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
    tier: str,
    expected_target: int,
    credit_cap: int,
    completed_prerequisites: list[str],
) -> None:
    provider_client = TieredDealMachineClient(estimated_by_tier={tier: credit_cap + 1})
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    for prerequisite in completed_prerequisites:
        _seed_completed_run(
            db_session,
            case,
            credits=0,
            search_tier=prerequisite,
        )

    preview = _preview(client, case_id, tier, expected_target)
    assert preview.status_code == 200, preview.text
    assert preview.json()["estimated_credit_cap"] == credit_cap
    assert preview.json()["estimated_credits"] == credit_cap + 1
    assert preview.json()["enough_credits"] is False
    assert str(credit_cap) in preview.json()["message"]

    blocked = _run(
        client,
        case_id,
        tier,
        expected_target,
        credit_cap + 1,
        preview.json()["request_fingerprint"],
    )
    assert blocked.status_code == 422
    assert str(credit_cap) in blocked.json()["detail"]
    assert provider_client.search_calls == []


@pytest.mark.parametrize(
    ("scope", "prior_credits", "expected_limit"),
    [
        ("case", 240, "250"),
        ("month", 1990, "2000"),
    ],
)
def test_ds11_enforces_case_and_monthly_credit_caps(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
    scope: str,
    prior_credits: int,
    expected_limit: str,
) -> None:
    provider_client = TieredDealMachineClient(estimated_by_tier={"best_fit": 20})
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)
    case = db_session.get(DispositionCase, UUID(case_id))
    assert case is not None
    usage_case = case if scope == "case" else _create_additional_case(db_session, client)
    _seed_completed_run(
        db_session,
        usage_case,
        credits=prior_credits,
    )

    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    assert preview.json()["enough_credits"] is False
    assert expected_limit in preview.json()["message"]
    if scope == "case":
        assert preview.json()["cumulative_case_credits"] == prior_credits
    else:
        assert preview.json()["cumulative_case_credits"] == 0
    assert preview.json()["monthly_credits"] == prior_credits

    blocked = _run(
        client,
        case_id,
        "best_fit",
        10,
        20,
        preview.json()["request_fingerprint"],
    )
    assert blocked.status_code == 422
    assert expected_limit in blocked.json()["detail"]
    assert provider_client.search_calls == []


def test_ds11_fails_closed_when_paid_response_has_no_actual_credit_telemetry(
    db_session: Session,
    api_db_override: None,
    monkeypatch: Any,
) -> None:
    provider_client = MissingCreditTelemetryClient(estimated_by_tier={"best_fit": 10})
    _configure_provider(monkeypatch, provider_client)
    client = TestClient(app)
    case_id = _create_case(db_session, client, approve=True)

    preview = _preview(client, case_id, "best_fit", 10)
    assert preview.status_code == 200, preview.text
    request_fingerprint = preview.json()["request_fingerprint"]
    blocked = _run(client, case_id, "best_fit", 10, 10, request_fingerprint)
    assert blocked.status_code == 422
    assert "credit" in blocked.json()["detail"].lower()
    assert "telemetry" in blocked.json()["detail"].lower()
    assert provider_client.search_calls == ["best_fit"]

    runs = list(db_session.scalars(select(BuyerDiscoveryRun)).all())
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].actual_credits is None
    assert runs[0].error_message is not None
    assert "telemetry" in runs[0].error_message.lower()
    assert int(
        db_session.scalar(select(func.count()).select_from(BuyerDiscoveryCandidate)) or 0
    ) == 0

    retry = _run(client, case_id, "best_fit", 10, 10, request_fingerprint)
    assert retry.status_code == 422, retry.text
    assert "pending credit reconciliation" in retry.json()["detail"].lower()
    assert provider_client.search_calls == ["best_fit"]
