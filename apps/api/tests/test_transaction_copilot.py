from copy import deepcopy
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models.foundation import (
    Transaction,
    TransactionChecklistItem,
    TransactionCopilotRecommendation,
    TransactionCopilotReview,
    TransactionEvent,
)
from tests.test_transactions import HEADERS, setup_transaction


def test_transaction_copilot_is_evidence_linked_draft_only_and_non_mutating(
    db_session: Session,
    api_db_override: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    _, transaction_id = setup_transaction(db_session, client)
    document = client.post(
        (
            f"/api/v1/transactions/{transaction_id}/documents"
            "?file_name=contract.pdf"
            "&document_type=signed_purchase_agreement"
            "&title=Executed%20purchase%20agreement"
            "&document_status=executed"
        ),
        headers={**HEADERS, "Content-Type": "application/pdf"},
        content=b"%PDF transaction copilot evidence",
    )
    assert document.status_code == 201, document.text
    assert client.post(
        (
            f"/api/v1/transactions/{transaction_id}/documents/"
            f"{document.json()['id']}/facts"
        ),
        headers=HEADERS,
        json={
            "field_key": "purchase_price",
            "value_text": "$170,000",
            "source_page": 2,
            "source_excerpt": "Purchase price is $170,000.",
        },
    ).status_code == 201
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
        json={
            "decision": "approve",
            "notes": "Approved for transaction pilot testing.",
        },
    ).status_code == 200
    assert client.post(
        "/api/v1/ai/runtime/install",
        headers=HEADERS,
    ).status_code == 201

    overview = client.get(
        f"/api/v1/transactions/{transaction_id}/copilot",
        headers=HEADERS,
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["pilot_mode"] == "draft_only"
    assert overview.json()["capability_status"] == "enabled"
    assert overview.json()["confirmed_document_fact_count"] == 1
    assert overview.json()["external_actions_blocked"] is True

    blocked = client.post(
        f"/api/v1/transactions/{transaction_id}/copilot/analyze",
        headers=HEADERS,
        json={"idempotency_key": "transaction:blocked"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["run_status"] == "blocked"
    assert blocked.json()["recommendation"] is None

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()
    output = {
        "status_summary": "Contract evidence is present; closing coordination remains incomplete.",
        "missing_items": ["Assign the closing attorney contact."],
        "deadline_risks": [],
        "document_findings": [
            {
                "finding": "Human-confirmed purchase price is available.",
                "document_id": document.json()["id"],
                "source_page": 2,
                "evidence": "Executed purchase agreement, page 2",
            }
        ],
        "party_gaps": ["Closing attorney contact is missing."],
        "recommended_internal_actions": ["Confirm the closing attorney."],
        "closing_attorney_email_draft": "Please confirm receipt and the closing timeline.",
        "seller_email_draft": "We are coordinating the closing details.",
        "legal_escalations": [],
        "evidence": ["Executed purchase agreement, page 2"],
        "confidence": 88,
    }

    class FakeOpenAIResponsesClient:
        def __init__(self, **_: object) -> None:
            pass

        def create_structured_response(
            self,
            **kwargs: object,
        ) -> tuple[dict[str, object], dict[str, int]]:
            prompt = kwargs["user_prompt"]
            assert isinstance(prompt, str)
            assert "Purchase price is $170,000." in prompt
            assert "%PDF" not in prompt
            schema = kwargs["json_schema"]
            assert isinstance(schema, dict)
            assert "status_summary" in schema["properties"]
            return output, {
                "input_tokens": 180,
                "output_tokens": 120,
                "total_tokens": 300,
            }

    monkeypatch.setattr(
        "app.services.ai_runtime.OpenAIResponsesClient",
        FakeOpenAIResponsesClient,
    )
    assert client.patch(
        "/api/v1/ai/runtime/policy",
        headers=HEADERS,
        json={"provider_status": "enabled"},
    ).status_code == 200
    transaction = db_session.get(Transaction, UUID(transaction_id))
    assert transaction is not None
    transaction_snapshot = {
        "status": transaction.status,
        "closing_date": transaction.closing_date,
        "title_company": transaction.title_company,
    }
    checklist_snapshot = {
        str(item.id): item.status
        for item in db_session.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
    }
    event_count = int(
        db_session.scalar(
            select(func.count(TransactionEvent.id)).where(
                TransactionEvent.transaction_id == transaction.id
            )
        )
        or 0
    )
    request = {"idempotency_key": "transaction:coordination:1"}
    first = client.post(
        f"/api/v1/transactions/{transaction_id}/copilot/analyze",
        headers=HEADERS,
        json=request,
    )
    second = client.post(
        f"/api/v1/transactions/{transaction_id}/copilot/analyze",
        headers=HEADERS,
        json=request,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    recommendation = first.json()["recommendation"]
    assert recommendation["status"] == "draft"
    assert recommendation["output_payload"]["confidence"] == 88
    assert second.json()["recommendation"]["id"] == recommendation["id"]

    corrected = deepcopy(output)
    corrected["status_summary"] = "Human-corrected transaction summary."
    reviewed = client.post(
        (
            "/api/v1/transactions/copilot/recommendations/"
            f"{recommendation['id']}/review"
        ),
        headers=HEADERS,
        json={
            "decision": "edited",
            "final_output": corrected,
            "estimated_time_saved_seconds": 420,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["final_output"]["status_summary"].startswith(
        "Human-corrected"
    )

    db_session.expire_all()
    stored = db_session.get(Transaction, transaction.id)
    assert stored is not None
    assert stored.status == transaction_snapshot["status"]
    assert stored.closing_date == transaction_snapshot["closing_date"]
    assert stored.title_company == transaction_snapshot["title_company"]
    assert {
        str(item.id): item.status
        for item in db_session.scalars(
            select(TransactionChecklistItem).where(
                TransactionChecklistItem.transaction_id == transaction.id
            )
        ).all()
    } == checklist_snapshot
    assert (
        int(
            db_session.scalar(
                select(func.count(TransactionEvent.id)).where(
                    TransactionEvent.transaction_id == transaction.id
                )
            )
            or 0
        )
        == event_count
    )
    assert int(
        db_session.scalar(
            select(func.count()).select_from(TransactionCopilotRecommendation)
        )
        or 0
    ) == 1
    assert int(
        db_session.scalar(
            select(func.count()).select_from(TransactionCopilotReview)
        )
        or 0
    ) == 1
