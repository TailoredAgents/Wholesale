from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    CompensationPlanRole,
    CompensationPlanVersion,
    DealDeduction,
    DispositionCampaign,
    DispositionCopilotRecommendation,
    DispositionCopilotReview,
    DispositionOperatingMode,
    Lead,
    RevenueRecord,
    RoleCredit,
    Transaction,
    User,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def setup_case_foundation(db: Session, client: TestClient) -> tuple[str, str, str]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    lead_response = client.post(
        "/api/v1/leads",
        headers=HEADERS,
        json={
            "contact": {"legal_name": "Disposition Seller", "contact_type": "seller"},
            "property": {
                "street_address": "900 Buyer Lane",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "property_type": "single_family",
            },
            "source": "referral",
            "stage_key": "offer_ready",
        },
    )
    lead_id = lead_response.json()["id"]
    transaction_response = client.post(
        f"/api/v1/leads/{lead_id}/transactions",
        headers=HEADERS,
        json={"purchase_price_cents": 15000000},
    )
    transaction_id = transaction_response.json()["transactions"][0]["id"]
    transaction = db.get(Transaction, UUID(transaction_id))
    lead = db.get(Lead, UUID(lead_id))
    assert transaction is not None and lead is not None
    transaction.status = "executed"
    lead.stage_key = "under_contract"

    plan = CompensationPlanVersion(
        organization_id=owner.organization_id,
        name="Stonegate Standard",
        version_number=1,
        status="active",
        acquisition_reserve_cents=250000,
        target_company_margin_basis_points=3000,
        effective_start_at=datetime.now(UTC),
        effective_end_at=None,
        created_by_user_id=owner.id,
        approved_by_user_id=owner.id,
        approved_at=datetime.now(UTC),
        notes=None,
    )
    db.add(plan)
    db.flush()
    role_specs = {
        "lead_manager": (1000, None),
        "acquisitions_closer": (1000, None),
        "ceo_management": (1000, None),
        "dispositions": (1500, None),
        "transaction_coordinator": (500, 100000),
    }
    for role_key, (basis_points, cap_cents) in role_specs.items():
        db.add(
            CompensationPlanRole(
                organization_id=owner.organization_id,
                compensation_plan_version_id=plan.id,
                role_key=role_key,
                basis_points=basis_points,
                cap_cents=cap_cents,
                notes=None,
            )
        )
        db.add(
            RoleCredit(
                organization_id=owner.organization_id,
                compensation_plan_version_id=plan.id,
                lead_id=lead.id,
                user_id=owner.id,
                role_key=role_key,
                credit_basis_points=10000,
                status="approved",
                assigned_by_user_id=owner.id,
                approved_by_user_id=owner.id,
                approved_at=datetime.now(UTC),
                notes="Test contribution evidence.",
            )
        )
    db.add(
        DispositionOperatingMode(
            organization_id=owner.organization_id,
            compensation_plan_version_id=plan.id,
            key="human_led",
            name="Human-led",
            status="available",
            human_share_min_basis_points=1500,
            human_share_max_basis_points=1500,
            expected_company_share_min_basis_points=5000,
            expected_company_share_max_basis_points=5000,
            ai_authority_level="human_execution",
            activation_requirements={},
        )
    )
    db.commit()

    buyer_response = client.post(
        "/api/v1/buyers",
        headers=HEADERS,
        json={
            "name": "Reliable Atlanta Buyer",
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
    return lead_id, transaction_id, buyer_response.json()["id"]


def test_disposition_buyer_selection_and_reconciliation(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, buyer_id = setup_case_foundation(db_session, client)
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
    assert created.json()["compensation_plan_label"] == "Stonegate Standard v1"

    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/package/approve", headers=HEADERS
        ).status_code
        == 200
    )
    unmatched = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert unmatched.status_code == 200
    assert unmatched.json()["matches"][0]["qualification_status"] == "review_required"
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/campaigns/release", headers=HEADERS
        ).status_code
        == 422
    )

    expires_at = (datetime.now(UTC) + timedelta(days=90)).isoformat()
    proof = client.post(
        f"/api/v1/dispositions/buyers/{buyer_id}/proof",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "proof.pdf",
            "content_type": "application/pdf",
            "institution_name": "Example Bank",
            "verified_amount_cents": 40000000,
            "expires_at": expires_at,
        },
        content=b"%PDF verified proof of funds",
    )
    assert proof.status_code == 201, proof.text
    matched = client.post(f"/api/v1/dispositions/cases/{case_id}/matches", headers=HEADERS)
    assert matched.json()["matches"][0]["qualification_status"] == "qualified"
    assert matched.json()["matches"][0]["score_basis_points"] == 9250
    assert (
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/campaigns/release", headers=HEADERS
        ).status_code
        == 200
    )

    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "earnest_money_cents": 500000,
            "financing_type": "cash",
            "proof_document_id": proof.json()["id"],
        },
    )
    assert offer.status_code == 200, offer.text
    offer_id = offer.json()["offers"][0]["id"]
    selection = client.post(
        f"/api/v1/dispositions/cases/{case_id}/buyer-selection",
        headers=HEADERS,
        json={
            "primary_offer_id": offer_id,
            "reason": "Verified funds, acceptable price, and local closing history.",
        },
    )
    assert selection.status_code == 200, selection.text
    assert selection.json()["selected_buyer_id"] == buyer_id

    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction.status = "funded"
    db_session.add(
        RevenueRecord(
            organization_id=transaction.organization_id,
            lead_id=UUID(lead_id),
            deal_id=transaction.deal_id,
            transaction_id=transaction.id,
            source="assignment_fee",
            status="collected",
            amount_cents=4000000,
            received_at=datetime.now(UTC),
            notes=None,
        )
    )
    db_session.add(
        DealDeduction(
            organization_id=transaction.organization_id,
            lead_id=UUID(lead_id),
            deal_id=transaction.deal_id,
            transaction_id=transaction.id,
            category="closing_cost",
            amount_cents=250000,
            incurred_at=datetime.now(UTC),
            notes=None,
        )
    )
    db_session.commit()

    reconciliation = client.post(
        f"/api/v1/dispositions/cases/{case_id}/reconciliation", headers=HEADERS
    )
    assert reconciliation.status_code == 200, reconciliation.text
    statement = reconciliation.json()["reconciliation"]
    assert statement["adjusted_deal_margin_cents"] == 3500000
    assert statement["total_compensation_cents"] == 1675000
    assert statement["company_profit_cents"] == 1825000
    assert statement["company_margin_basis_points"] == 5214
    approval = client.post(
        f"/api/v1/dispositions/cases/{case_id}/reconciliation/decision",
        headers=HEADERS,
        json={"decision": "approved", "notes": "Closing statement verified."},
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["reconciliation"]["status"] == "approved"
    export = client.get(f"/api/v1/dispositions/cases/{case_id}/accounting.csv", headers=HEADERS)
    assert export.status_code == 200
    assert "company_profit,company,,1825000,approved" in export.text


def test_buyer_selection_requires_current_proof_of_funds(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    _, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    ).json()
    offer = client.post(
        f"/api/v1/dispositions/cases/{case['id']}/offers",
        headers=HEADERS,
        json={"buyer_id": buyer_id, "amount_cents": 19000000},
    )
    response = client.post(
        f"/api/v1/dispositions/cases/{case['id']}/buyer-selection",
        headers=HEADERS,
        json={
            "primary_offer_id": offer.json()["offers"][0]["id"],
            "reason": "Attempt without verified evidence.",
        },
    )
    assert response.status_code == 422
    assert "proof-of-funds" in response.json()["detail"]


def test_disposition_copilot_generates_reviewed_draft_without_taking_action(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    lead_id, transaction_id, buyer_id = setup_case_foundation(db_session, client)
    case = client.post(
        "/api/v1/dispositions/cases",
        headers=HEADERS,
        json={
            "transaction_id": transaction_id,
            "asking_price_cents": 19000000,
            "minimum_acceptable_cents": 18000000,
        },
    ).json()
    case_id = case["id"]
    assert client.post(
        f"/api/v1/dispositions/cases/{case_id}/package/approve",
        headers=HEADERS,
    ).status_code == 200
    proof = client.post(
        f"/api/v1/dispositions/buyers/{buyer_id}/proof",
        headers={**HEADERS, "Content-Type": "application/pdf"},
        params={
            "file_name": "proof.pdf",
            "content_type": "application/pdf",
            "institution_name": "Example Bank",
            "verified_amount_cents": 40000000,
            "expires_at": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        },
        content=b"%PDF verified proof of funds",
    )
    assert proof.status_code == 201
    matched = client.post(
        f"/api/v1/dispositions/cases/{case_id}/matches",
        headers=HEADERS,
    )
    assert matched.status_code == 200
    offer = client.post(
        f"/api/v1/dispositions/cases/{case_id}/offers",
        headers=HEADERS,
        json={
            "buyer_id": buyer_id,
            "amount_cents": 19000000,
            "earnest_money_cents": 500000,
            "financing_type": "cash",
            "proof_document_id": proof.json()["id"],
        },
    )
    assert offer.status_code == 200
    offer_id = offer.json()["offers"][0]["id"]

    with monkeypatch.context() as configured_environment:
        configured_environment.setenv("AI_ENABLED", "true")
        configured_environment.setenv("OPENAI_API_KEY", "test-openai-key")
        get_settings.cache_clear()
        assert client.post(
            "/api/v1/ai/orchestrator/portfolio/install",
            headers=HEADERS,
        ).status_code == 201
        assert client.post(
            "/api/v1/ai/copilots/install",
            headers=HEADERS,
        ).status_code == 201
        assert client.post(
            "/api/v1/ai/copilots/foundation/decision",
            headers=HEADERS,
            json={"decision": "approve", "notes": "Approved for AI8 test."},
        ).status_code == 200
        installed = client.post("/api/v1/ai/runtime/install", headers=HEADERS)
        assert installed.status_code == 201
        capability = next(
            item
            for item in installed.json()["runtime"]["capabilities"]
            if item["capability_key"] == "disposition.match"
        )
        assert capability["status"] == "enabled"
        assert capability["requires_human_review"] is True

        class FakeOpenAIResponsesClient:
            def __init__(self, **_: object) -> None:
                pass

            def create_structured_response(self, **kwargs: object):
                prompt = kwargs["user_prompt"]
                assert isinstance(prompt, str)
                assert "Disposition Seller" not in prompt
                assert "purchase_price_cents" not in prompt
                assert "minimum_acceptable_cents" not in prompt
                assert "15000000" not in prompt
                assert "18000000" not in prompt
                assert '"meets_internal_floor": true' in prompt
                schema = kwargs["json_schema"]
                assert isinstance(schema, dict)
                assert schema["additionalProperties"] is False
                return (
                    {
                        "status_summary": (
                            "One verified local buyer has submitted an acceptable offer."
                        ),
                        "package_gaps": [],
                        "package_highlights": [
                            "Atlanta single-family opportunity",
                            "Human-approved asking price is $190,000",
                        ],
                        "recommended_buyers": [
                            {
                                "buyer_id": buyer_id,
                                "buyer_name": "Reliable Atlanta Buyer",
                                "recommendation": "priority",
                                "rationale": [
                                    "Verified funds cover the asking price.",
                                    "The buyer matches the market and property type.",
                                ],
                                "risks": ["No Stonegate closing history is recorded."],
                                "evidence": [
                                    "Deterministic buyer rank 1",
                                    "Current proof-of-funds record",
                                ],
                            }
                        ],
                        "offer_comparison": [
                            {
                                "offer_id": offer_id,
                                "buyer_name": "Reliable Atlanta Buyer",
                                "strength": "strong",
                                "rationale": [
                                    "Offer meets the approved economics.",
                                    "Earnest money is recorded.",
                                ],
                                "risks": ["Deposit receipt has not been recorded."],
                            }
                        ],
                        "buyer_outreach_subject": (
                            "Atlanta single-family investment opportunity"
                        ),
                        "buyer_outreach_body": (
                            "Stonegate has an Atlanta single-family opportunity "
                            "available at $190,000. Reply for the approved package."
                        ),
                        "recommended_internal_actions": [
                            "Confirm the deposit deadline before buyer selection."
                        ],
                        "relationship_update_proposals": [
                            "Confirm the buyer's preferred Atlanta ZIP codes."
                        ],
                        "risk_alerts": [
                            "Maintain a backup buyer before final placement."
                        ],
                        "uncertainties": [
                            "Stonegate closing performance is not yet recorded."
                        ],
                        "evidence": [
                            "Approved disposition package",
                            "Buyer match and offer records",
                        ],
                        "confidence": 88,
                    },
                    {"input_tokens": 180, "output_tokens": 220, "total_tokens": 400},
                )

        monkeypatch.setattr(
            "app.services.ai_runtime.OpenAIResponsesClient",
            FakeOpenAIResponsesClient,
        )
        analyzed = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:1"},
        )
        assert analyzed.status_code == 200, analyzed.text
        result = analyzed.json()
        assert result["run_status"] == "needs_review"
        assert result["recommendation"]["status"] == "draft"
        recommendation_id = result["recommendation"]["id"]

        repeated = client.post(
            f"/api/v1/dispositions/cases/{case_id}/copilot/analyze",
            headers=HEADERS,
            json={"idempotency_key": "disposition-copilot:test:1"},
        )
        assert repeated.json()["recommendation"]["id"] == recommendation_id
        review = client.post(
            f"/api/v1/dispositions/copilot/recommendations/{recommendation_id}/review",
            headers=HEADERS,
            json={
                "decision": "accepted",
                "notes": "Disposition specialist reviewed the evidence.",
                "estimated_time_saved_seconds": 600,
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["decision"] == "accepted"
        overview = client.get(
            f"/api/v1/dispositions/cases/{case_id}/copilot",
            headers=HEADERS,
        )
        assert overview.status_code == 200
        assert overview.json()["recommendations"][0]["status"] == "accepted"
        assert overview.json()["external_actions_blocked"] is True
        assert overview.json()["metrics"]["reviewed"] == 1

    get_settings.cache_clear()
    db_session.expire_all()
    refreshed_case = client.get(
        f"/api/v1/dispositions/cases/{case_id}",
        headers=HEADERS,
    ).json()
    assert refreshed_case["selected_buyer_id"] is None
    assert (
        db_session.scalar(
            select(func.count(DispositionCampaign.id)).where(
                DispositionCampaign.disposition_case_id == UUID(case_id)
            )
        )
        == 0
    )
    assert db_session.scalar(
        select(func.count(DispositionCopilotRecommendation.id))
    ) == 1
    assert db_session.scalar(select(func.count(DispositionCopilotReview.id))) == 1
