from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import app
from app.models.foundation import AuditEvent, EmailSenderAlias, EmailSenderGrant
from app.services.bootstrap import bootstrap_foundation

OWNER_EMAIL = "owner@example.com"
OWNER_HEADERS = {"X-Dev-User-Email": OWNER_EMAIL}


def test_resend_configuration_is_provider_specific() -> None:
    incomplete = Settings.model_validate(
        {
            "APP_ENV": "local",
            "EMAIL_ENABLED": True,
            "EMAIL_PROVIDER": "resend",
        }
    )
    assert "RESEND_API_KEY" in incomplete.email_configuration_blockers
    assert "GOOGLE_OAUTH_CLIENT_ID" not in incomplete.email_configuration_blockers

    configured = Settings.model_validate(
        {
            "APP_ENV": "local",
            "EMAIL_ENABLED": True,
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_test",
            "RESEND_WEBHOOK_SECRET": "whsec_test",
            "RESEND_SENDING_DOMAIN": "stonegatehb.com",
            "RESEND_RECEIVING_DOMAIN": "stonegatehb.com",
            "RESEND_DEFAULT_FROM_EMAIL": "offers@stonegatehb.com",
            "RESEND_WEBHOOK_BASE_URL": "https://api.stonegate.test",
        }
    )
    assert configured.email_configuration_blockers == ()


def create_user(
    client: TestClient,
    *,
    email: str,
    display_name: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/operations/users",
        headers=OWNER_HEADERS,
        json={
            "email": email,
            "display_name": display_name,
            "role_key": "acquisition_rep",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_owner_manages_provider_neutral_aliases_and_sender_access(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Austin",
    )
    client = TestClient(app)
    devon = create_user(
        client,
        email="devon.login@example.com",
        display_name="Devon",
    )
    create_user(
        client,
        email="other.login@example.com",
        display_name="Other Closer",
    )

    named_response = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "devon@stonegatehb.com",
            "display_name": "Devon | Stonegate Home Buyers",
            "alias_type": "named",
            "purpose_key": "devon",
            "owner_user_id": devon["id"],
            "signature_text": "Devon\nStonegate Home Buyers",
        },
    )
    assert named_response.status_code == 201, named_response.text
    named = named_response.json()
    assert named["owner_user_name"] == "Devon"
    assert named["can_send"] is True

    offers_response = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "offers@stonegatehb.com",
            "display_name": "Stonegate Home Buyers",
            "alias_type": "department",
            "purpose_key": "seller_intake",
            "is_default": True,
            "routing_metadata": {
                "initial_primary": "Devon",
                "owner_watcher": "Austin",
            },
        },
    )
    assert offers_response.status_code == 201, offers_response.text
    offers = offers_response.json()
    assert offers["is_default"] is True

    reserved_response = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "michael@stonegatehb.com",
            "display_name": "Michael | Stonegate Home Buyers",
            "alias_type": "named",
            "purpose_key": "future_lead_manager",
            "status": "reserved",
        },
    )
    assert reserved_response.status_code == 201, reserved_response.text
    assert reserved_response.json()["inbound_enabled"] is False
    assert reserved_response.json()["outbound_enabled"] is False

    grant_response = client.put(
        f"/api/v1/email/aliases/{offers['id']}/grants",
        headers=OWNER_HEADERS,
        json={
            "user_id": devon["id"],
            "access_level": "sender",
            "can_send": True,
            "receives_notifications": True,
        },
    )
    assert grant_response.status_code == 200, grant_response.text
    assert grant_response.json()["grants"][0]["user_name"] == "Devon"

    devon_list = client.get(
        "/api/v1/email/aliases",
        headers={"X-Dev-User-Email": "devon.login@example.com"},
    )
    assert devon_list.status_code == 200, devon_list.text
    assert {item["email_address"] for item in devon_list.json()["items"]} == {
        "devon@stonegatehb.com",
        "offers@stonegatehb.com",
    }
    assert all(item["can_send"] for item in devon_list.json()["items"])

    other_list = client.get(
        "/api/v1/email/aliases",
        headers={"X-Dev-User-Email": "other.login@example.com"},
    )
    assert other_list.status_code == 200, other_list.text
    assert other_list.json()["items"] == []

    forbidden_create = client.post(
        "/api/v1/email/aliases",
        headers={"X-Dev-User-Email": "devon.login@example.com"},
        json={
            "email_address": "unauthorized@stonegatehb.com",
            "display_name": "Unauthorized",
            "alias_type": "department",
            "purpose_key": "unauthorized",
        },
    )
    assert forbidden_create.status_code == 403

    duplicate = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "OFFERS@stonegatehb.com",
            "display_name": "Duplicate",
            "alias_type": "department",
            "purpose_key": "duplicate",
        },
    )
    assert duplicate.status_code == 422

    revoked = client.delete(
        f"/api/v1/email/aliases/{offers['id']}/grants/{devon['id']}",
        headers=OWNER_HEADERS,
    )
    assert revoked.status_code == 200, revoked.text
    devon_after_revoke = client.get(
        "/api/v1/email/aliases",
        headers={"X-Dev-User-Email": "devon.login@example.com"},
    )
    assert {
        item["email_address"] for item in devon_after_revoke.json()["items"]
    } == {"devon@stonegatehb.com"}

    assert (
        db_session.scalar(select(func.count()).select_from(EmailSenderAlias))
        == 3
    )
    assert (
        db_session.scalar(select(func.count()).select_from(EmailSenderGrant))
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "email_sender_alias")
        )
        == 3
    )


def test_alias_requires_approved_domain_and_named_owner(
    db_session: Session,
    api_db_override: None,
) -> None:
    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email=OWNER_EMAIL,
        admin_name="Austin",
    )
    client = TestClient(app)

    wrong_domain = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "offers@example.com",
            "display_name": "Stonegate",
            "alias_type": "department",
            "purpose_key": "seller_intake",
        },
    )
    assert wrong_domain.status_code == 422
    assert "approved Stonegate email domain" in wrong_domain.text

    missing_owner = client.post(
        "/api/v1/email/aliases",
        headers=OWNER_HEADERS,
        json={
            "email_address": "austin@stonegatehb.com",
            "display_name": "Austin",
            "alias_type": "named",
            "purpose_key": "owner",
        },
    )
    assert missing_owner.status_code == 422
    assert "requires an assigned user" in missing_owner.text
