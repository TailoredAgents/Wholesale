from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.domain.rbac import PermissionKeys
from app.main import app
from app.models.foundation import (
    Buyer,
    BuyerOffer,
    BuyerProofDocument,
    Conversation,
    ConversationContextLink,
    Role,
    RoleAssignment,
    Task,
    Team,
    TeamMembership,
    Transaction,
    TransactionChecklistItem,
    User,
)
from app.schemas.buyers import BuyerDataProviderRead
from app.schemas.deals import DealOverviewRead
from app.services import buyer_discovery
from app.services import disposition_desk as disposition_desk_service
from app.services.bootstrap import bootstrap_foundation
from app.services.disposition_desk import read_desk
from tests.test_dispositions import (
    HEADERS,
    OWNER_EMAIL,
    approve_disposition_package,
    put_verified_buy_box,
    setup_case_foundation,
    upload_received_proof,
    verify_proof,
)


def _add_user(db: Session, *, email: str, name: str, role_key: str) -> User:
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    role = db.scalar(
        select(Role).where(
            Role.organization_id == owner.organization_id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=owner.organization_id,
        email=email,
        display_name=name,
        is_active=True,
        calling_enabled=False,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=owner.organization_id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return user


def _add_buyer(db: Session, *, owner: User, name: str) -> Buyer:
    buyer = Buyer(
        organization_id=owner.organization_id,
        name=name,
        company_name=None,
        email=f"{name.lower().replace(' ', '-')}@example.com",
        phone=None,
        normalized_email=f"{name.lower().replace(' ', '-')}@example.com",
        normalized_phone=None,
        normalized_company_name=None,
        buyer_type="cash_buyer",
        status="active",
        source_key="manual",
        source_detail="Disposition Desk test",
        source_external_key=None,
        created_by_user_id=owner.id,
        relationship_owner_user_id=owner.id,
        last_verified_at=None,
        archived_at=None,
        archived_by_user_id=None,
        archive_reason=None,
        proof_of_funds_status="unknown",
        max_purchase_price_cents=None,
        reliability_score_basis_points=5000,
        completed_deals=0,
        failed_deals=0,
        proof_of_funds_expires_at=None,
        notes=None,
    )
    db.add(buyer)
    db.commit()
    return buyer


def test_disposition_desk_empty_read_model(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )

    response = TestClient(app).get("/api/v1/dispositions/desk", headers=HEADERS)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["requested_scope"] == "mine"
    assert payload["effective_scope"] == "mine"
    assert payload["metrics"] == {
        "today": 0,
        "active_deals": 0,
        "buyer_follow_ups": 0,
        "replies": 0,
        "offers": 0,
        "deadlines": 0,
        "weak_coverage": 0,
    }
    for section in (
        "today",
        "active_deals",
        "buyer_follow_ups",
        "replies",
        "offers",
        "deadlines",
        "coverage_warnings",
        "deal_records",
    ):
        assert payload[section] == []
        assert payload["sections"][section] == {
            "total": 0,
            "returned": 0,
            "has_more": False,
            "offset": 0,
        }
    assert payload["source_health"]["canonical_data_status"] == "current"
    assert payload["source_health"]["external_provider_status"] == "not_configured"


def test_disposition_desk_scopes_buyers_and_authorizes_team_view(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    rep_one = _add_user(
        db_session,
        email="rep-one@example.com",
        name="Rep One",
        role_key="disposition_rep",
    )
    rep_two = _add_user(
        db_session,
        email="rep-two@example.com",
        name="Rep Two",
        role_key="disposition_rep",
    )
    manager = _add_user(
        db_session,
        email="manager@example.com",
        name="Disposition Manager",
        role_key="disposition_manager",
    )
    _add_buyer(db_session, owner=rep_one, name="Rep One Buyer")
    _add_buyer(db_session, owner=rep_two, name="Rep Two Buyer")
    unassigned = _add_buyer(db_session, owner=manager, name="Unassigned Buyer")
    unassigned.relationship_owner_user_id = None
    db_session.commit()
    team = Team(
        organization_id=manager.organization_id,
        name="Disposition Team",
        team_type="dispositions",
        manager_user_id=manager.id,
        is_active=True,
    )
    db_session.add(team)
    db_session.flush()
    for rep in (rep_one, rep_two):
        db_session.add(
            TeamMembership(
                organization_id=manager.organization_id,
                team_id=team.id,
                user_id=rep.id,
                membership_role="member",
            )
        )
    db_session.commit()
    client = TestClient(app)

    rep_headers = {"X-Dev-User-Email": rep_one.email}
    mine = client.get("/api/v1/dispositions/desk?scope=mine", headers=rep_headers)
    forbidden = client.get("/api/v1/dispositions/desk?scope=team", headers=rep_headers)
    team_view = client.get(
        "/api/v1/dispositions/desk?scope=team",
        headers={"X-Dev-User-Email": manager.email},
    )

    assert mine.status_code == 200, mine.text
    assert mine.json()["buyer_network"]["total"] == 1
    assert mine.json()["scope_member_count"] == 1
    assert forbidden.status_code == 403
    assert "manager access" in forbidden.json()["detail"]
    assert team_view.status_code == 200, team_view.text
    assert team_view.json()["effective_scope"] == "team"
    assert team_view.json()["scope_member_count"] == 3
    assert team_view.json()["buyer_network"]["total"] == 2
    assert team_view.json()["buyer_network"]["unassigned"] == 0
    assert "Unassigned records are excluded" in team_view.json()["scope_notice"]


def test_disposition_desk_aggregates_owned_work_with_canonical_links(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    created = client.post(
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
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    approved = approve_disposition_package(client, case_id)
    assert approved.status_code == 200, approved.text

    now = datetime.now(UTC)
    put_verified_buy_box(client, buyer_id)
    received_proof = upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=5),
    )
    verify_proof(
        client,
        received_proof["id"],
        expires_at=now + timedelta(days=5),
    )
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200, matched.text
    followup = client.post(
        f"/api/v1/dispositions/cases/{case_id}/engagements",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "engagement_type": "follow_up",
            "status": "scheduled",
            "scheduled_at": (now - timedelta(minutes=30)).isoformat(),
            "notes": "Confirm inspection availability.",
        },
    )
    assert followup.status_code == 200, followup.text
    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offer-room/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "earnest_money_cents": 500000,
            "deposit_due_at": (now - timedelta(minutes=15)).isoformat(),
            "due_diligence_days": 7,
            "contingencies": [],
            "contingencies_confirmed": True,
            "proposed_closing_at": (now + timedelta(days=14)).isoformat(),
            "funding_method": "cash",
            "funding_confidence_basis_points": 9000,
            "proof_document_id": received_proof["id"],
            "change_reason": "Normalized offer for disposition desk aggregation coverage.",
            "idempotency_key": "desk-canonical-offer-01",
        },
    )
    assert offer.status_code == 201, offer.text
    offer_id = offer.json()["offers"][0]["id"]

    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    buyer = db_session.get(Buyer, UUID(buyer_id))
    conversation = db_session.scalar(
        select(Conversation)
        .join(
            ConversationContextLink,
            ConversationContextLink.conversation_id == Conversation.id,
        )
        .where(ConversationContextLink.buyer_id == UUID(buyer_id))
    )
    assert owner is not None and transaction is not None
    assert buyer is not None and conversation is not None
    buyer.relationship_owner_user_id = owner.id
    conversation.assigned_user_id = owner.id
    conversation.unread_count = 1
    conversation.last_inbound_at = now
    conversation.last_outbound_at = now - timedelta(hours=1)
    db_session.commit()
    relationship_followup = client.post(
        f"/api/v1/buyers/{buyer_id}/relationship-activities",
        headers=HEADERS,
        json={
            "engagement_type": "follow_up",
            "scheduled_at": (now - timedelta(minutes=10)).isoformat(),
            "notes": "Confirm the buyer's current acquisition capacity.",
        },
    )
    assert relationship_followup.status_code == 201, relationship_followup.text
    transaction.earnest_money_due_at = now - timedelta(hours=1)
    transaction.earnest_money_paid_at = None
    transaction.due_diligence_deadline = now + timedelta(days=2)
    transaction.assignment_deadline = now + timedelta(days=5)
    transaction.closing_date = now + timedelta(days=10)
    db_session.add(
        TransactionChecklistItem(
            organization_id=owner.organization_id,
            transaction_id=transaction.id,
            responsible_user_id=owner.id,
            item_key="title_open",
            category="closing",
            title="Open title",
            description="Send the executed agreement to title.",
            is_required=True,
            dependency_item_id=None,
            evidence_document_id=None,
            evidence_notes=None,
            escalated_at=None,
            status="open",
            due_at=now - timedelta(minutes=45),
            completed_at=None,
            sort_order=1,
        )
    )
    db_session.add(
        Task(
            organization_id=owner.organization_id,
            lead_id=None,
            deal_id=transaction.deal_id,
            responsible_user_id=owner.id,
            task_type="buyer_follow_up",
            work_kind="supporting",
            title="Review buyer response",
            status="open",
            priority="high",
            due_at=now - timedelta(minutes=20),
            completed_at=None,
            completed_by_user_id=None,
            outcome=None,
            completion_notes=None,
            successor_task_id=None,
        )
    )
    db_session.commit()

    response = client.get("/api/v1/dispositions/desk?scope=mine", headers=HEADERS)

    assert response.status_code == 200, response.text
    payload = response.json()
    deal_id = str(transaction.deal_id)
    assert payload["metrics"]["active_deals"] == 1
    assert payload["metrics"]["buyer_follow_ups"] == 2
    assert payload["metrics"]["replies"] == 1
    assert payload["metrics"]["offers"] == 1
    assert payload["metrics"]["deadlines"] == 4
    assert payload["active_deals"][0]["primary_action"]["href"] == (
        f"/os/deals?view=all&display=queue&deal={deal_id}&tab=disposition&dispositionTab=package"
    )
    assert payload["buyer_follow_ups"][0]["primary_action"]["href"] == (
        f"/os/buyers?buyer={buyer_id}&tab=summary"
    )
    relationship_item = next(
        item for item in payload["buyer_follow_ups"] if item["disposition_case_id"] is None
    )
    assert relationship_item["deal_id"] is None
    assert relationship_item["secondary_action"] is None
    assert relationship_item["context"] == "Buyer relationship"
    assert payload["replies"][0]["primary_action"]["href"] == (
        f"/os/inbox?conversation={conversation.id}"
    )
    assert payload["offers"][0]["offer_id"] == offer_id
    assert payload["offers"][0]["due_at"] is None
    assert payload["offers"][0]["primary_action"]["href"].endswith(
        "&tab=disposition&dispositionTab=offers"
    )
    deadlines = {item["key"]: item for item in payload["deadlines"]}
    assert f"deadline:earnest_money:{transaction.id}" in deadlines
    assert f"deadline:offer_deposit:{offer_id}" not in deadlines
    assert f"deadline:due_diligence:{transaction.id}" not in deadlines
    assert f"deadline:assignment:{transaction.id}" not in deadlines
    assert f"deadline:buyer_pof:{buyer_id}" in deadlines
    proof_deadline = deadlines[f"deadline:buyer_pof:{buyer_id}"]
    assert proof_deadline["deal_id"] is None
    assert proof_deadline["disposition_case_id"] is None
    assert proof_deadline["secondary_action"] is None
    checklist = next(
        item for key, item in deadlines.items() if key.startswith("deadline:checklist:")
    )
    assert checklist["owner_name"] == "Owner"
    assert checklist["primary_action"]["href"].endswith(f"deal={deal_id}&tab=closing")
    assert any(item["key"].startswith("task:") for item in payload["today"])
    assert any(item["key"] == f"reply:{conversation.id}" for item in payload["today"])

    selected_offer = db_session.get(BuyerOffer, UUID(offer_id))
    assert selected_offer is not None
    selected_offer.status = "selected"
    selected_offer.selected_at = now
    db_session.commit()
    selected_response = client.get("/api/v1/dispositions/desk?scope=mine", headers=HEADERS)
    assert selected_response.status_code == 200, selected_response.text
    selected_deadlines = {item["key"]: item for item in selected_response.json()["deadlines"]}
    assert f"deadline:offer_deposit:{offer_id}" in selected_deadlines

    restricted = Principal(
        user_id=owner.id,
        organization_id=owner.organization_id,
        email=owner.email,
        permission_keys=frozenset(
            {
                PermissionKeys.VIEW_DEALS,
                PermissionKeys.VIEW_BUYERS,
            }
        ),
    )
    restricted_payload = read_desk(db_session, restricted, requested_scope="mine")
    assert restricted_payload.metrics.replies == 0
    assert restricted_payload.replies == []

    team_response = client.get("/api/v1/dispositions/desk?scope=team", headers=HEADERS)
    assert team_response.status_code == 200, team_response.text
    team_task = next(
        item for item in team_response.json()["today"] if item["key"].startswith("task:")
    )
    assert team_task["primary_action"]["href"].startswith("/os/tasks?view=team&")


def test_disposition_desk_prefers_current_proof_over_stale_renewal_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, _, buyer_id = setup_case_foundation(db_session, client)
    now = datetime.now(UTC)
    current = upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=90),
    )
    verify_proof(
        client,
        current["id"],
        expires_at=now + timedelta(days=90),
    )
    stale = upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=180),
    )
    verify_proof(
        client,
        stale["id"],
        expires_at=now + timedelta(days=180),
    )
    stale_row = db_session.get(BuyerProofDocument, UUID(stale["id"]))
    assert stale_row is not None
    stale_row.expires_at = now - timedelta(days=1)
    stale_row.verified_at = now + timedelta(minutes=1)
    db_session.commit()
    upload_received_proof(
        client,
        buyer_id,
        expires_at=now + timedelta(days=365),
    )

    response = client.get("/api/v1/dispositions/desk?scope=mine", headers=HEADERS)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["buyer_network"]["missing_proof"] == 0
    assert payload["buyer_network"]["expiring_proof"] == 0
    assert f"deadline:buyer_pof:{buyer_id}" not in {item["key"] for item in payload["deadlines"]}


def test_disposition_desk_reports_raw_totals_before_section_caps(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, _ = setup_case_foundation(db_session, client)
    created = client.post(
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
    assert created.status_code == 201, created.text
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert owner is not None and transaction is not None
    due_at = datetime.now(UTC) - timedelta(minutes=1)
    for index in range(105):
        db_session.add(
            Task(
                organization_id=owner.organization_id,
                lead_id=None,
                deal_id=transaction.deal_id,
                responsible_user_id=owner.id,
                task_type="buyer_follow_up",
                work_kind="supporting",
                title=f"Disposition task {index:03d}",
                status="open",
                priority="high",
                due_at=due_at,
                completed_at=None,
                completed_by_user_id=None,
                outcome=None,
                completion_notes=None,
                successor_task_id=None,
            )
        )
    db_session.commit()

    response = client.get("/api/v1/dispositions/desk?scope=mine", headers=HEADERS)

    assert response.status_code == 200, response.text
    payload = response.json()
    today_status = payload["sections"]["today"]
    assert payload["metrics"]["today"] == today_status["total"]
    assert today_status["total"] > 100
    assert today_status["returned"] == 100
    assert today_status["has_more"] is True
    assert today_status["offset"] == 0
    assert len(payload["today"]) == 100

    next_response = client.get(
        "/api/v1/dispositions/desk?scope=mine&section=today&offset=100",
        headers=HEADERS,
    )

    assert next_response.status_code == 200, next_response.text
    next_payload = next_response.json()
    next_status = next_payload["sections"]["today"]
    assert next_payload["metrics"]["today"] == payload["metrics"]["today"]
    assert next_status["total"] == today_status["total"]
    assert next_status["offset"] == 100
    assert next_status["returned"] == next_status["total"] - 100
    assert next_status["has_more"] is False
    assert len(next_payload["today"]) == next_status["returned"]
    assert {item["key"] for item in payload["today"]}.isdisjoint(
        {item["key"] for item in next_payload["today"]}
    )
    assert next_payload["sections"]["active_deals"]["offset"] == 0


@pytest.mark.parametrize(
    "query",
    (
        "offset=1",
        "section=not_a_section",
        "section=today&offset=-1",
    ),
)
def test_disposition_desk_rejects_invalid_pagination_query(
    db_session: Session,
    api_db_override: None,
    query: str,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )

    response = TestClient(app).get(
        f"/api/v1/dispositions/desk?{query}",
        headers=HEADERS,
    )

    assert response.status_code == 422


def test_disposition_desk_omits_case_less_ready_deals(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    setup_case_foundation(db_session, client)
    requested_deal_ids: list[set[UUID] | None] = []
    original_overview = disposition_desk_service.deals.overview

    def capture_overview(
        db: Session,
        principal: Principal,
        *,
        deal_ids: set[UUID] | None = None,
    ) -> DealOverviewRead:
        requested_deal_ids.append(deal_ids)
        return original_overview(db, principal, deal_ids=deal_ids)

    monkeypatch.setattr(disposition_desk_service.deals, "overview", capture_overview)

    response = client.get("/api/v1/dispositions/desk?scope=team", headers=HEADERS)

    assert response.status_code == 200, response.text
    assert requested_deal_ids == [set()]
    assert response.json()["metrics"]["active_deals"] == 0
    assert response.json()["deal_records"] == []


def test_disposition_desk_marks_configured_provider_unverified_without_live_check(
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
    monkeypatch.setattr(
        buyer_discovery,
        "provider_status",
        lambda: BuyerDataProviderRead(
            provider="dealmachine",
            configured=True,
            live_search_enabled=True,
            message="Configured.",
        ),
    )

    response = TestClient(app).get("/api/v1/dispositions/desk", headers=HEADERS)

    assert response.status_code == 200, response.text
    assert response.json()["source_health"]["external_provider_status"] == ("configured_unverified")
