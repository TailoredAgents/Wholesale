from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models.foundation import (
    ActivityEvent,
    AuditEvent,
    Buyer,
    BuyerCriteria,
    ConsentRecord,
    Contact,
    ContactMethod,
    Conversation,
    ConversationAssignmentEvent,
    ConversationContextLink,
    SuppressionRecord,
    User,
)
from app.services.bootstrap import bootstrap_foundation
from app.services.communication_compliance import (
    evaluate_sms_eligibility,
    evaluate_voice_eligibility,
)

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
    assert created["status"] == "needs_review"
    assert created["criteria"]["markets"] == "Atlanta, Decatur"
    assert created["proof_of_funds_status"] == "unknown"
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
    sms_consent = db_session.scalar(select(ConsentRecord).where(ConsentRecord.channel == "sms"))
    assert sms_consent is not None
    assert sms_consent.normalized_address == "+14045550199"
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "buyer.create")
            )
            or 0
        )
        == 1
    )

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


def test_create_buyer_rejects_sms_consent_for_an_invalid_phone(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)

    response = TestClient(app).post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "Invalid SMS Buyer", "phone": "bad-number", "sms_consent": True},
    )

    assert response.status_code == 422
    assert "valid phone number" in response.text


def test_create_buyer_defaults_to_review_and_normalizes_identity(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)

    response = TestClient(app).post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={
            "name": "  Alex   Investor  ",
            "company_name": "  Peach   State Homes  ",
            "email": "BUYER@Example.COM",
            "phone": "404.555.0144",
            "source_key": "Personal List",
            "source_detail": "Alex's original relationships",
            "source_external_key": "alex-row-1",
            "phone_contact_permission": True,
            "permission_evidence_source": "documented_phone_call",
        },
    )

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "Alex Investor"
    assert result["company_name"] == "Peach State Homes"
    assert result["email"] == "BUYER@Example.COM"
    assert result["phone"] == "404.555.0144"
    assert result["normalized_email"] == "buyer@example.com"
    assert result["normalized_phone"] == "+14045550144"
    assert result["status"] == "needs_review"
    assert result["source_key"] == "personal_list"
    assert result["source_external_key"] == "alex-row-1"
    assert result["created_by_user_id"] is not None
    assert result["created_by_name"] == "Owner"
    assert result["phone_permission"]["status"] == "granted"
    assert result["phone_permission"]["source"] == "documented_phone_call"
    assert result["sms_permission"]["status"] == "missing"


def test_create_buyer_requires_a_usable_contact_channel(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)

    missing = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "No Contact"},
    )
    invalid = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "Invalid Contact", "phone": "123"},
    )

    assert missing.status_code == 422
    assert invalid.status_code == 422
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 0


def test_permission_grants_require_a_valid_buyer_phone(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    rejected = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Email Only Permission",
            "email": "email-only@example.com",
            "sms_consent": True,
        },
    )
    assert rejected.status_code == 422
    assert "valid buyer phone number" in rejected.text

    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={"name": "Email Only Buyer", "email": "only@example.com"},
    )
    assert created.status_code == 201
    update = client.patch(
        f"/api/v1/buyers/{created.json()['id']}",
        headers=headers,
        json={"phone_contact_permission": True},
    )
    assert update.status_code == 422
    assert "valid buyer phone number" in update.text
    assert int(db_session.scalar(select(func.count()).select_from(ConsentRecord)) or 0) == 0


def test_duplicate_preflight_blocks_create_without_audited_override(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    first = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "First Buyer",
            "company_name": "Shared Capital LLC",
            "email": "shared@example.com",
            "phone": "404-555-0101",
        },
    )
    assert first.status_code == 201

    preflight = client.post(
        "/api/v1/buyers/duplicates/preflight",
        headers=headers,
        json={
            "company_name": " shared   capital llc ",
            "email": "SHARED@example.com",
            "phone": "+1 (404) 555-0101",
        },
    )
    assert preflight.status_code == 200
    duplicate_data = preflight.json()
    assert duplicate_data["has_matches"] is True
    assert set(duplicate_data["matches"][0]["matched_fields"]) == {
        "company_name",
        "email",
        "phone",
    }

    blocked = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={"name": "Second Buyer", "email": "shared@example.com"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "buyer_duplicate_match"
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 1

    override = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Legitimate Separate Entity",
            "email": "shared@example.com",
            "allow_separate_record": True,
            "separate_record_reason": "Separate legal entity sharing an office inbox.",
        },
    )
    assert override.status_code == 201
    assert int(db_session.scalar(select(func.count()).select_from(Buyer)) or 0) == 2
    override_audit = db_session.scalar(
        select(AuditEvent).where(AuditEvent.action == "buyer.duplicate_override")
    )
    assert override_audit is not None
    assert "Separate legal entity" in str(override_audit.reason)


def test_update_versions_changed_criteria_and_syncs_canonical_contact(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Original Buyer",
            "email": "original@example.com",
            "phone": "4045550111",
            "phone_contact_permission": True,
            "sms_consent": True,
            "criteria": {"markets": "Atlanta", "max_price_cents": 20000000},
        },
    ).json()
    buyer_id = created["id"]

    unrelated = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=headers,
        json={"notes": "Relationship note only."},
    )
    assert unrelated.status_code == 200
    assert unrelated.json()["email"] == "original@example.com"
    assert unrelated.json()["phone"] == "4045550111"
    assert int(db_session.scalar(select(func.count()).select_from(BuyerCriteria)) or 0) == 1

    updated = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=headers,
        json={
            "name": "Updated Buyer",
            "email": "updated@example.com",
            "phone": "4705550199",
            "criteria": {"markets": "Atlanta, Marietta", "max_price_cents": 25000000},
        },
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["criteria"]["version_number"] == 2
    assert data["phone_permission"]["status"] == "missing"
    assert data["sms_permission"]["status"] == "missing"
    assert {
        (item["channel"], item["status"], item["normalized_address"])
        for item in data["permission_history"]
    } == {
        ("phone", "granted", "+14045550111"),
        ("sms", "granted", "+14045550111"),
        ("phone", "missing", "+14705550199"),
        ("sms", "missing", "+14705550199"),
    }
    permission_audit = db_session.scalar(
        select(AuditEvent)
        .where(AuditEvent.action == "buyer.permission_update")
        .order_by(AuditEvent.created_at.desc())
    )
    assert permission_audit is not None
    assert {
        (item["channel"], item["status"]) for item in permission_audit.new_value["changes"]
    } == {("phone", "missing"), ("sms", "missing")}
    criteria = db_session.scalars(
        select(BuyerCriteria).order_by(BuyerCriteria.version_number)
    ).all()
    assert [(item.version_number, item.is_current) for item in criteria] == [
        (1, False),
        (2, True),
    ]
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    contact = db_session.get(Contact, conversation.contact_id)
    assert contact is not None
    assert contact.legal_name == "Updated Buyer"
    methods = db_session.scalars(
        select(ContactMethod)
        .where(ContactMethod.contact_id == contact.id)
        .order_by(ContactMethod.method_type)
    ).all()
    assert {(item.method_type, item.normalized_value) for item in methods} == {
        ("email", "original@example.com"),
        ("email", "updated@example.com"),
        ("phone", "+14045550111"),
        ("phone", "+14705550199"),
    }
    assert {(item.method_type, item.normalized_value) for item in methods if item.is_primary} == {
        ("email", "updated@example.com"),
        ("phone", "+14705550199"),
    }
    default_email = db_session.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.contact_id == contact.id,
            ContactMethod.method_type == "email",
        )
        .order_by(ContactMethod.is_primary.desc(), ContactMethod.created_at.asc())
    )
    assert default_email is not None
    assert default_email.normalized_value == "updated@example.com"

    cleared_email = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=headers,
        json={"email": None},
    )
    assert cleared_email.status_code == 200
    assert cleared_email.json()["email"] is None
    assert (
        db_session.scalar(
            select(ContactMethod).where(
                ContactMethod.contact_id == contact.id,
                ContactMethod.method_type == "email",
            )
        )
        is None
    )
    assert int(db_session.scalar(select(func.count()).select_from(Conversation)) or 0) == 1
    assert (
        int(db_session.scalar(select(func.count()).select_from(ConversationContextLink)) or 0) == 1
    )


def test_archive_restore_and_legacy_inactive_read_compatibility(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={"name": "Lifecycle Buyer", "email": "life@example.com"},
    ).json()
    buyer_id = created["id"]

    invalid_archive = client.post(
        f"/api/v1/buyers/{buyer_id}/archive",
        headers=headers,
        json={"reason": "   "},
    )
    assert invalid_archive.status_code == 422
    assert client.get(f"/api/v1/buyers/{buyer_id}", headers=headers).json()["status"] == (
        "needs_review"
    )

    archived = client.post(
        f"/api/v1/buyers/{buyer_id}/archive",
        headers=headers,
        json={"reason": "Relationship intentionally retired."},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archive_reason"] == "Relationship intentionally retired."
    assert client.get("/api/v1/buyers", headers=headers).json()["total"] == 0
    archived_list = client.get("/api/v1/buyers?status=archived", headers=headers).json()
    assert archived_list["total"] == 1
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.status == "closed"

    restored = client.post(f"/api/v1/buyers/{buyer_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "needs_review"
    assert conversation.status == "open"

    buyer = db_session.get(Buyer, UUID(buyer_id))
    assert buyer is not None
    buyer.status = "inactive"
    db_session.commit()
    legacy = client.get(f"/api/v1/buyers/{buyer_id}", headers=headers)
    assert legacy.status_code == 200
    assert legacy.json()["status"] == "paused"
    assert client.get("/api/v1/buyers?status=paused", headers=headers).json()["total"] == 1


def test_unrelated_edit_preserves_legacy_scalar_but_does_not_report_it_as_evidence(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    buyer = Buyer(
        organization_id=owner.organization_id,
        name="Legacy Verified Buyer",
        company_name=None,
        email="legacy-verified@example.com",
        phone=None,
        normalized_email="legacy-verified@example.com",
        normalized_phone=None,
        normalized_company_name=None,
        buyer_type="cash_buyer",
        status="active",
        source_key="legacy",
        source_detail=None,
        source_external_key=None,
        created_by_user_id=owner.id,
        relationship_owner_user_id=owner.id,
        proof_of_funds_status="verified",
    )
    db_session.add(buyer)
    db_session.commit()

    response = TestClient(app).patch(
        f"/api/v1/buyers/{buyer.id}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"notes": "Relationship details refreshed."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["notes"] == "Relationship details refreshed."
    assert response.json()["proof_of_funds_status"] == "unknown"
    db_session.refresh(buyer)
    assert buyer.proof_of_funds_status == "verified"


def test_buyer_editor_cannot_manually_claim_proof_status(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    created = client.post(
        "/api/v1/buyers",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"name": "Evidence Guard Buyer", "email": "evidence-guard@example.com"},
    )
    assert created.status_code == 201, created.text

    changed = client.patch(
        f"/api/v1/buyers/{created.json()['id']}",
        headers={"X-Dev-User-Email": OWNER_EMAIL},
        json={"proof_of_funds_status": "verified"},
    )
    assert changed.status_code == 422
    assert "derived from reviewed evidence" in changed.json()["detail"]


def test_list_buyers_paginates_past_one_hundred_with_stable_filters(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    for index in range(125):
        db_session.add(
            Buyer(
                organization_id=owner.organization_id,
                name=f"Investor {index:03d}",
                company_name=f"Group {index % 3}",
                email=f"buyer{index}@example.com",
                phone=None,
                normalized_email=f"buyer{index}@example.com",
                normalized_phone=None,
                normalized_company_name=f"group {index % 3}",
                buyer_type="cash_buyer",
                status="active" if index % 2 == 0 else "needs_review",
                source_key="alex_list" if index < 110 else "manual",
                source_detail=None,
                source_external_key=f"row-{index}",
                created_by_user_id=owner.id,
                relationship_owner_user_id=owner.id,
                proof_of_funds_status="unknown",
            )
        )
    db_session.commit()
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}

    first = client.get("/api/v1/buyers?limit=100", headers=headers).json()
    second = client.get("/api/v1/buyers?limit=100&offset=100", headers=headers).json()
    assert first["total"] == 125
    assert len(first["items"]) == 100
    assert first["has_more"] is True
    assert len(second["items"]) == 25
    assert second["has_more"] is False
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
    filtered = client.get(
        f"/api/v1/buyers?status=active&source_key=alex_list&owner_id={owner.id}",
        headers=headers,
    ).json()
    assert filtered["total"] == 55
    assert filtered["owner_options"][0]["user_id"] == str(owner.id)
    assert "alex_list" in filtered["source_options"]


def test_buyer_owner_and_records_are_isolated_by_organization(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    other = bootstrap_foundation(
        db_session,
        organization_name="Other Buyer Workspace",
        admin_email="other-owner@example.com",
        admin_name="Other Owner",
    )
    assert other.admin_user is not None
    client = TestClient(app)
    first_headers = {"X-Dev-User-Email": OWNER_EMAIL}
    other_headers = {"X-Dev-User-Email": "other-owner@example.com"}

    invalid_owner = client.post(
        "/api/v1/buyers",
        headers=first_headers,
        json={
            "name": "Cross Org Owner",
            "email": "cross@example.com",
            "relationship_owner_user_id": str(other.admin_user.id),
        },
    )
    assert invalid_owner.status_code == 404
    other_buyer = client.post(
        "/api/v1/buyers",
        headers=other_headers,
        json={"name": "Other Buyer", "email": "other-buyer@example.com"},
    )
    assert other_buyer.status_code == 201
    buyer_id = other_buyer.json()["id"]
    assert client.get(f"/api/v1/buyers/{buyer_id}", headers=first_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/buyers/{buyer_id}",
            headers=first_headers,
            json={"notes": "Should not write"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/buyers/{buyer_id}/archive",
            headers=first_headers,
            json={"reason": "Should not write"},
        ).status_code
        == 404
    )
    assert (
        int(
            db_session.scalar(
                select(func.count())
                .select_from(ActivityEvent)
                .where(ActivityEvent.organization_id == other.organization.id)
            )
            or 0
        )
        == 1
    )


def test_criteria_patch_merges_omitted_fields_and_null_is_noop(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Criteria Buyer",
            "email": "criteria@example.com",
            "criteria": {
                "markets": "Atlanta",
                "property_types": "single_family",
                "min_price_cents": 10000000,
                "max_price_cents": 30000000,
            },
        },
    ).json()

    merged = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"criteria": {"notes": "Verified directly."}},
    )
    assert merged.status_code == 200
    criteria = merged.json()["criteria"]
    assert criteria["version_number"] == 2
    assert criteria["markets"] == "Atlanta"
    assert criteria["property_types"] == "single_family"
    assert criteria["min_price_cents"] == 10000000
    assert criteria["max_price_cents"] == 30000000
    assert criteria["notes"] == "Verified directly."

    noop = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"criteria": None},
    )
    assert noop.status_code == 200
    assert noop.json()["criteria"]["version_number"] == 2
    rows = db_session.scalars(select(BuyerCriteria)).all()
    assert len(rows) == 2
    assert sum(1 for row in rows if row.is_current) == 1


def test_archive_restore_does_not_reopen_a_manually_closed_conversation(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={"name": "Closed Buyer", "email": "closed@example.com"},
    ).json()
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    conversation.status = "closed"
    conversation.queue_key = "closed"
    conversation.closed_at = conversation.created_at
    conversation.conversation_metadata = {
        **(conversation.conversation_metadata or {}),
        "closed_manually": True,
    }
    db_session.commit()

    archived = client.post(
        f"/api/v1/buyers/{created['id']}/archive",
        headers=headers,
        json={"reason": "Temporary cleanup."},
    )
    assert archived.status_code == 200
    restored = client.post(f"/api/v1/buyers/{created['id']}/restore", headers=headers)
    assert restored.status_code == 200
    db_session.refresh(conversation)
    assert conversation.status == "closed"
    assert conversation.queue_key == "closed"
    assert conversation.conversation_metadata["closed_manually"] is True


def test_owner_reassignment_is_audited_without_default_line_rerouting(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    owner = db_session.scalar(select(User).where(User.email == OWNER_EMAIL))
    assert owner is not None
    second_owner = User(
        organization_id=owner.organization_id,
        email="dispo@example.com",
        display_name="Disposition Owner",
        external_auth_id=None,
        is_active=True,
    )
    db_session.add(second_owner)
    db_session.commit()
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={"name": "Assigned Buyer", "email": "assigned@example.com"},
    ).json()
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    original_assignment = conversation.assigned_user_id

    note_only = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"notes": "Do not reroute this conversation."},
    )
    assert note_only.status_code == 200
    db_session.refresh(conversation)
    assert conversation.assigned_user_id == original_assignment

    reassigned = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"relationship_owner_user_id": str(second_owner.id)},
    )
    assert reassigned.status_code == 200
    db_session.refresh(conversation)
    assert conversation.assigned_user_id == second_owner.id
    event = db_session.scalar(
        select(ConversationAssignmentEvent)
        .where(
            ConversationAssignmentEvent.conversation_id == conversation.id,
            ConversationAssignmentEvent.assigned_user_id == second_owner.id,
        )
        .order_by(ConversationAssignmentEvent.created_at.desc())
    )
    assert event is not None
    assert event.actor_user_id == owner.id

    cleared = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"relationship_owner_user_id": None},
    )
    assert cleared.status_code == 200
    db_session.refresh(conversation)
    assert conversation.assigned_user_id is None
    cleared_event = db_session.scalar(
        select(ConversationAssignmentEvent)
        .where(
            ConversationAssignmentEvent.conversation_id == conversation.id,
            ConversationAssignmentEvent.previous_assigned_user_id == second_owner.id,
            ConversationAssignmentEvent.assigned_user_id.is_(None),
        )
        .order_by(ConversationAssignmentEvent.created_at.desc())
    )
    assert cleared_event is not None
    assert cleared_event.actor_user_id == owner.id


def test_do_not_contact_suppression_overrides_existing_granted_permissions(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Suppressed Buyer",
            "phone": "404-555-0188",
            "phone_contact_permission": True,
            "sms_consent": True,
        },
    ).json()
    response = client.patch(
        f"/api/v1/buyers/{created['id']}",
        headers=headers,
        json={"status": "do_not_contact"},
    )
    assert response.status_code == 200
    suppressions = db_session.scalars(
        select(SuppressionRecord).order_by(SuppressionRecord.channel)
    ).all()
    assert [(row.channel, row.status, row.source) for row in suppressions] == [
        ("phone", "active", "buyer_lifecycle"),
        ("sms", "active", "buyer_lifecycle"),
    ]
    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    contact = db_session.get(Contact, conversation.contact_id)
    assert contact is not None
    sms = evaluate_sms_eligibility(db_session, contact)
    voice = evaluate_voice_eligibility(db_session, contact)
    assert sms.consent_status == "granted"
    assert voice.consent_status == "granted"
    assert sms.is_suppressed is True and sms.can_send is False
    assert voice.is_suppressed is True and voice.can_call is False


def test_relationship_do_not_contact_suppresses_and_can_be_released(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Relationship DNC Buyer",
            "phone": "404-555-0166",
            "relationship_status": "do_not_contact",
            "phone_contact_permission": True,
            "sms_consent": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["relationship_status"] == "do_not_contact"

    def suppression_states() -> set[tuple[str, str]]:
        return {
            (row.channel, row.status)
            for row in db_session.scalars(
                select(SuppressionRecord).where(
                    SuppressionRecord.normalized_address == "+14045550166"
                )
            ).all()
        }

    assert suppression_states() == {("phone", "active"), ("sms", "active")}

    released = client.patch(
        f"/api/v1/buyers/{created.json()['id']}",
        headers=headers,
        json={"relationship_status": "active"},
    )
    assert released.status_code == 200, released.text
    assert suppression_states() == {("phone", "lifted"), ("sms", "lifted")}


def test_archiving_and_restoring_dnc_buyer_preserves_contact_suppression(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    created = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Archived DNC Buyer",
            "phone": "404-555-0177",
            "phone_contact_permission": True,
            "sms_consent": True,
        },
    ).json()
    buyer_id = created["id"]
    marked_dnc = client.patch(
        f"/api/v1/buyers/{buyer_id}",
        headers=headers,
        json={"status": "do_not_contact"},
    )
    assert marked_dnc.status_code == 200

    archived = client.post(
        f"/api/v1/buyers/{buyer_id}/archive",
        headers=headers,
        json={"reason": "Keep this retired relationship on file."},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = client.post(f"/api/v1/buyers/{buyer_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["status"] == "do_not_contact"

    suppressions = db_session.scalars(
        select(SuppressionRecord)
        .where(
            SuppressionRecord.normalized_address == "+14045550177",
            SuppressionRecord.source == "buyer_lifecycle",
        )
        .order_by(SuppressionRecord.channel)
    ).all()
    assert [(row.channel, row.status) for row in suppressions] == [
        ("phone", "active"),
        ("sms", "active"),
    ]

    conversation = db_session.scalar(select(Conversation))
    assert conversation is not None
    contact = db_session.get(Contact, conversation.contact_id)
    assert contact is not None
    sms = evaluate_sms_eligibility(db_session, contact)
    voice = evaluate_voice_eligibility(db_session, contact)
    assert sms.consent_status == "granted"
    assert voice.consent_status == "granted"
    assert sms.is_suppressed is True and sms.can_send is False
    assert voice.is_suppressed is True and voice.can_call is False


def test_shared_phone_suppression_remains_until_every_dnc_buyer_releases_it(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    shared_phone = "404-555-0128"
    dnc_buyer = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Shared Phone DNC",
            "email": "dnc-shared@example.com",
            "phone": shared_phone,
            "status": "do_not_contact",
        },
    )
    assert dnc_buyer.status_code == 201
    duplicate = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Legitimate Shared Phone Buyer",
            "email": "other-shared@example.com",
            "phone": shared_phone,
            "status": "paused",
            "allow_separate_record": True,
            "separate_record_reason": "Two distinct buyers use a shared office line.",
        },
    )
    assert duplicate.status_code == 201

    def suppression_states() -> set[tuple[str, str]]:
        return {
            (row.channel, row.status)
            for row in db_session.scalars(
                select(SuppressionRecord).where(
                    SuppressionRecord.normalized_address == "+14045550128"
                )
            ).all()
        }

    assert suppression_states() == {("phone", "active"), ("sms", "active")}

    duplicate_id = duplicate.json()["id"]
    activated = client.patch(
        f"/api/v1/buyers/{duplicate_id}",
        headers=headers,
        json={"status": "active"},
    )
    assert activated.status_code == 200
    assert suppression_states() == {("phone", "active"), ("sms", "active")}

    archived = client.post(
        f"/api/v1/buyers/{duplicate_id}/archive",
        headers=headers,
        json={"reason": "Temporary relationship cleanup."},
    )
    assert archived.status_code == 200
    restored = client.post(f"/api/v1/buyers/{duplicate_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert suppression_states() == {("phone", "active"), ("sms", "active")}

    changed_phone = client.patch(
        f"/api/v1/buyers/{duplicate_id}",
        headers=headers,
        json={"phone": "470-555-0198"},
    )
    assert changed_phone.status_code == 200
    assert suppression_states() == {("phone", "active"), ("sms", "active")}

    released = client.patch(
        f"/api/v1/buyers/{dnc_buyer.json()['id']}",
        headers=headers,
        json={"status": "active"},
    )
    assert released.status_code == 200
    assert suppression_states() == {("phone", "lifted"), ("sms", "lifted")}


def test_source_external_key_conflict_returns_clean_409(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    first = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "First External Buyer",
            "email": "first-external@example.com",
            "source_key": "investor_lift",
            "source_external_key": "buyer-42",
        },
    )
    assert first.status_code == 201
    conflict = client.post(
        "/api/v1/buyers",
        headers=headers,
        json={
            "name": "Second External Buyer",
            "email": "second-external@example.com",
            "source_key": "Investor Lift",
            "source_external_key": "buyer-42",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "buyer_source_conflict"


def test_search_treats_like_metacharacters_as_literal_text(
    db_session: Session,
    api_db_override: None,
) -> None:
    seed_owner(db_session)
    client = TestClient(app)
    headers = {"X-Dev-User-Email": OWNER_EMAIL}
    for name, email in (
        ("100% Capital", "percent@example.com"),
        ("100X Capital", "plain@example.com"),
        ("Buyer_A", "underscore@example.com"),
        ("BuyerXA", "other@example.com"),
    ):
        response = client.post(
            "/api/v1/buyers",
            headers=headers,
            json={"name": name, "email": email},
        )
        assert response.status_code == 201

    percent = client.get("/api/v1/buyers", headers=headers, params={"q": "100%"}).json()
    underscore = client.get("/api/v1/buyers", headers=headers, params={"q": "Buyer_A"}).json()
    assert [row["name"] for row in percent["items"]] == ["100% Capital"]
    assert [row["name"] for row in underscore["items"]] == ["Buyer_A"]
