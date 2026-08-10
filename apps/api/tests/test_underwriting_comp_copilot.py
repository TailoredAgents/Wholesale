from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.underwriting_comp_copilot as comp_copilot_service
from app.core.config import get_settings
from app.integrations.openai_client import validate_strict_json_schema
from app.main import app
from app.models.foundation import (
    AuditEvent,
    Lead,
    UnderwritingCompCopilotMessage,
    UnderwritingCompCopilotThread,
    UnderwritingMarketAnalysis,
    User,
)
from app.schemas.underwriting_comp_copilot import CompCopilotDraft
from app.services.bootstrap import bootstrap_foundation
from app.services.underwriting_comp_copilot import (
    COMP_COPILOT_OUTPUT_SCHEMA,
    CompCopilotPolicyError,
    _validate_draft,
)

OWNER_EMAIL = "copilot-owner@example.com"


def seed_analysis(db: Session, client: TestClient) -> UnderwritingMarketAnalysis:
    result = bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Copilot Owner",
    )
    response = client.post(
        "/api/v1/leads",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "contact": {
                "legal_name": "Jordan Seller",
                "preferred_name": "Jordan",
                "contact_type": "seller",
            },
            "property": {
                "street_address": "100 Subject Ave",
                "city": "Atlanta",
                "state": "GA",
                "postal_code": "30303",
                "county": "Fulton",
                "property_type": "single_family",
            },
            "source": "website",
            "stage_key": "underwriting",
        },
    )
    assert response.status_code == 201
    lead = db.get(Lead, UUID(response.json()["id"]))
    owner = db.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert lead is not None and owner is not None

    analysis = UnderwritingMarketAnalysis(
        organization_id=result.organization.id,
        lead_id=lead.id,
        property_id=lead.property_id,
        created_by_user_id=owner.id,
        provider="rentcast+realestateapi",
        valuation_profile="house_v3",
        requested_address="100 Subject Ave, Atlanta, GA 30303",
        estimated_value_cents=30_000_000,
        estimated_value_low_cents=28_000_000,
        estimated_value_high_cents=32_000_000,
        arv_low_cents=31_000_000,
        arv_high_cents=34_000_000,
        repair_low_cents=4_000_000,
        repair_high_cents=5_000_000,
        mao_low_cents=17_000_000,
        mao_high_cents=19_000_000,
        recommended_offer_cents=17_500_000,
        assignment_fee_cents=1_500_000,
        offer_low_percentage=65,
        offer_high_percentage=70,
        confidence_score=62,
        selected_comp_count=2,
        rejected_comp_count=1,
        selected_comps=[
            {
                "provider_id": "selected-1",
                "formatted_address": "110 Subject Ave, Atlanta, GA 30303",
                "property_type": "Single Family",
                "price_cents": 32_000_000,
                "bedrooms": 3,
                "bathrooms": 2,
                "square_footage": 1800,
                "year_built": 1985,
                "distance_miles": 0.2,
                "sale_date": "2026-04-10",
                "condition_classification": "unknown",
                "comp_grade": "A",
                "search_level": "preferred",
                "selection_status": "selected",
                "selection_reason": "Nearby physically similar recorded sale.",
                "source_url": "https://records.example/sale/selected-1",
            },
            {
                "provider_id": "selected-2",
                "formatted_address": "120 Subject Ave, Atlanta, GA 30303",
                "property_type": "Single Family",
                "price_cents": 33_000_000,
                "bedrooms": 3,
                "bathrooms": 2,
                "square_footage": 1850,
                "year_built": 1984,
                "distance_miles": 0.3,
                "sale_date": "2026-03-15",
                "condition_classification": "renovated",
                "comp_grade": "B",
                "search_level": "preferred",
                "selection_status": "selected",
                "selection_reason": "Similar renovated recorded sale.",
            },
        ],
        rejected_comps=[
            {
                "provider_id": "rejected-1",
                "formatted_address": "900 Far Rd, Atlanta, GA 30303",
                "property_type": "Single Family",
                "price_cents": 40_000_000,
                "distance_miles": 2.8,
                "sale_date": "2024-07-01",
                "condition_classification": "unknown",
                "comp_grade": "D",
                "search_level": "extended",
                "selection_status": "rejected",
                "selection_reason": "Older extended-market evidence ranked below stronger sales.",
            }
        ],
        subject_property={
            "formattedAddress": "100 Subject Ave, Atlanta, GA 30303",
            "propertyType": "Single Family",
            "bedrooms": 3,
            "bathrooms": 2,
            "squareFootage": 1825,
            "yearBuilt": 1983,
            "subdivision": "PEACHTREE",
        },
        raw_response={},
        analysis_metadata={
            "methodology_version": "v3",
            "confidence_tier": "moderate",
            "human_review_required": True,
            "report_stage": "preliminary",
            "review_reasons": ["One selected sale has unknown condition."],
            "confidence_factors": [
                {
                    "key": "condition_support",
                    "label": "Condition support",
                    "description": "One selected sale has unknown condition.",
                }
            ],
            "comp_search_summary": {"final_level": "preferred"},
            "market_adjustment": {
                "warnings": ["Condition adjustment was withheld."],
                "withheld_adjustment_keys": ["condition_quality"],
            },
        },
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def test_comp_copilot_schema_is_strict_and_policy_rejects_price_authority() -> None:
    validate_strict_json_schema(COMP_COPILOT_OUTPUT_SCHEMA)
    draft = CompCopilotDraft.model_validate(
        {
            "answer": "You should offer $200,000.",
            "citations": [{"evidence_id": "analysis:summary"}],
            "suggested_actions": [],
            "confidence": "high",
            "limitations": [],
            "human_review_required": True,
            "valuation_authority": "deterministic_v3_only",
        }
    )

    with pytest.raises(CompCopilotPolicyError):
        _validate_draft(
            draft,
            {
                "analysis:summary": {
                    "evidence_id": "analysis:summary",
                    "kind": "analysis",
                }
            },
        )


def test_comp_copilot_persists_evidence_grounded_thread(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNDERWRITING_AI_COMP_ANALYST_MODE", "disabled")
    get_settings.cache_clear()
    client = TestClient(app)
    analysis = seed_analysis(db_session, client)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    endpoint = (
        f"/api/v1/leads/{analysis.lead_id}/underwriting/market-analysis/{analysis.id}/copilot"
    )

    empty = client.get(endpoint, headers=headers)
    assert empty.status_code == 200
    assert empty.json()["thread_id"] is None
    assert empty.json()["messages"] == []
    assert empty.json()["valuation_authority"] == "deterministic_v3_only"

    response = client.post(
        f"{endpoint}/messages",
        headers=headers,
        json={"question": "What is lowering confidence?"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert len(payload["thread"]["messages"]) == 2
    assert payload["answer"]["role"] == "assistant"
    assert payload["answer"]["used_ai"] is False
    assert payload["answer"]["citations"]
    assert "$" not in payload["answer"]["content"]
    assert payload["answer"]["suggested_actions"][0]["action_type"] == "open_comp_review"

    saved = client.get(endpoint, headers=headers)
    assert saved.status_code == 200
    assert len(saved.json()["messages"]) == 2
    assert db_session.scalar(select(UnderwritingCompCopilotThread)) is not None
    assert len(db_session.scalars(select(UnderwritingCompCopilotMessage)).all()) == 2
    audit = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "underwriting.comp_copilot.ask")
    )
    assert audit is not None
    get_settings.cache_clear()


def test_comp_copilot_uses_strict_ai_draft_when_enabled(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeOpenAIClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def create_structured_response(
            self, **_kwargs: Any
        ) -> tuple[dict[str, Any], dict[str, int]]:
            return (
                {
                    "answer": (
                        "Condition support is the main unresolved evidence item. Review the "
                        "unknown-condition comparable before relying on the confidence tier."
                    ),
                    "citations": [
                        {"evidence_id": "analysis:summary"},
                        {"evidence_id": "comp:selected-1"},
                    ],
                    "suggested_actions": [
                        {
                            "action_type": "inspect_condition",
                            "label": "Review condition evidence",
                            "rationale": (
                                "This comparable is still classified as unknown condition."
                            ),
                            "comp_key": "selected-1",
                        }
                    ],
                    "confidence": "high",
                    "limitations": [
                        "The saved evidence does not confirm this comparable's condition."
                    ],
                    "human_review_required": True,
                    "valuation_authority": "deterministic_v3_only",
                },
                {"input_tokens": 250, "output_tokens": 90},
            )

    monkeypatch.setenv("UNDERWRITING_AI_COMP_ANALYST_MODE", "draft")
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        comp_copilot_service,
        "OpenAIResponsesClient",
        FakeOpenAIClient,
    )
    get_settings.cache_clear()
    client = TestClient(app)
    analysis = seed_analysis(db_session, client)
    endpoint = (
        f"/api/v1/leads/{analysis.lead_id}/underwriting/market-analysis/"
        f"{analysis.id}/copilot/messages"
    )

    response = client.post(
        endpoint,
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"question": "What should I verify next?"},
    )

    assert response.status_code == 201
    answer = response.json()["answer"]
    assert answer["used_ai"] is True
    assert answer["model"]
    assert len(answer["citations"]) == 2
    assert answer["suggested_actions"][0]["comp_key"] == "selected-1"
    get_settings.cache_clear()
