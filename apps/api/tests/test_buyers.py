from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    AuditEvent,
    Buyer,
    BuyerCriteria,
    ConsentRecord,
    Conversation,
    ConversationContextLink,
)
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"


def seed_owner(db_session: Session) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Owner",
    )


def test_create_and_list_buyer_with_criteria(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    create_response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "Acme Cash Buyer",
            "company_name": "Acme Homes",
            "email": "buyer@example.com",
            "phone": "(404) 555-0199",
            "buyer_type": "cash_buyer",
            "status": "active",
            "proof_of_funds_status": "received",
            "max_purchase_price_cents": 35000000,
            "notes": "Prefers light rehab in Atlanta.",
            "phone_contact_permission": True,
            "sms_consent": True,
            "criteria": {
                "markets": "Atlanta, Decatur",
                "property_types": "single_family, duplex",
                "min_price_cents": 10000000,
                "max_price_cents": 35000000,
                "rehab_levels": "light, medium",
                "notes": "Avoid foundation issues.",
            },
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Acme Cash Buyer"
    assert created["criteria"]["markets"] == "Atlanta, Decatur"
    assert created["proof_of_funds_status"] == "received"
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 1
    assert int(db_session.scalar(select(func.count()).select_from(BuyerCriteria)) or 0) == 1
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.conversation_type == "buyer"
    assert conversation.queue_key == "dispositions"
    context_link = db_session.scalar(select(ConversationContextLink))
    assert context_link is not None
    assert str(context_link.buyer_id) == created["id"]
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 2
    assert int(
        db_session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "buyer.create")
        )
        or 0
    ) == 1

    list_response = client.get("/api/v1/buyers", headers={"X-Dev-User-Email": OWNER_EMAIL})

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == created["id"]

    open_response = client.post(
        f"/api/v1/buyers/{created['id']}/conversation",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert open_response.status_code == 200
    assert open_response.json()["conversation_id"] == str(conversation.id)
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 1

    inbox_response = client.get(
        "/api/v1/inbox/conversations",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
    )
    assert inbox_response.status_code == 200
    inbox_item = inbox_response.json()["items"][0]
    assert inbox_item["conversation_type"] == "buyer"
    assert inbox_item["buyer_id"] == created["id"]
    assert inbox_item["property_address"] == "Buyer relationship"


def test_create_buyer_rejects_invalid_type(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    response = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "Unsupported Buyer", "buyer_type": "not_real"},
    )

    assert response.status_code == 422
