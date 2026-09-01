from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rbac import (
    ALL_PERMISSION_KEYS,
    DISPOSITION_KEYS,
    PERMISSIONS,
    ROLES,
    PermissionKeys,
)
from app.main import app
from app.models.foundation import (
    Organization,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from app.services.bootstrap import bootstrap_foundation


def _headers_for_role(db: Session, *, role_key: str, email: str) -> dict[str, str]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email="outreach-rbac-owner@example.com",
        admin_name="Outreach RBAC Owner",
    )
    organization = db.scalar(select(Organization))
    assert organization is not None
    role = db.scalar(
        select(Role).where(
            Role.organization_id == organization.id,
            Role.key == role_key,
        )
    )
    assert role is not None
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=email,
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db.add(user)
    db.flush()
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.commit()
    return {"X-Dev-User-Email": email}


def _headers_for_permissions(
    db: Session,
    *,
    permission_keys: set[str],
    email: str,
) -> dict[str, str]:
    bootstrap_foundation(
        db,
        organization_name="Stonegate Home Buyers",
        admin_email="outreach-rbac-owner@example.com",
        admin_name="Outreach RBAC Owner",
    )
    organization = db.scalar(select(Organization))
    assert organization is not None
    role = Role(
        organization_id=organization.id,
        key=f"outreach_without_buyers_{uuid4().hex}",
        name="Outreach without buyer visibility",
    )
    user = User(
        organization_id=organization.id,
        email=email,
        display_name=email,
        external_auth_id=None,
        is_active=True,
        calling_enabled=False,
    )
    db.add_all([role, user])
    db.flush()
    permissions = db.scalars(select(Permission).where(Permission.key.in_(permission_keys))).all()
    assert {permission.key for permission in permissions} == permission_keys
    db.add(
        RoleAssignment(
            organization_id=organization.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    db.add_all(
        RolePermission(
            organization_id=organization.id,
            role_id=role.id,
            permission_id=permission.id,
        )
        for permission in permissions
    )
    db.commit()
    return {"X-Dev-User-Email": email}


def test_disposition_outreach_permissions_are_explicitly_scoped_by_role() -> None:
    role_permissions = {role.key: set(role.permission_keys) for role in ROLES}
    manager = role_permissions["disposition_manager"]
    representative = role_permissions["disposition_rep"]

    assert PermissionKeys.MANAGE_DISPOSITION_OUTREACH in representative
    assert PermissionKeys.APPROVE_DISPOSITION_PACKAGES in representative
    assert PermissionKeys.APPROVE_DISPOSITION_OUTREACH in representative
    assert PermissionKeys.APPROVE_DISPOSITION_BUYER_SELECTION in representative
    assert PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH in representative
    assert PermissionKeys.SEND_BULK_COMMUNICATIONS not in representative

    assert PermissionKeys.MANAGE_DISPOSITION_OUTREACH in manager
    assert PermissionKeys.APPROVE_DISPOSITION_OUTREACH in manager
    assert PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH in manager
    assert representative == set(DISPOSITION_KEYS)
    assert len(DISPOSITION_KEYS) == len(set(DISPOSITION_KEYS))
    assert manager == representative | {PermissionKeys.EXPORT_BUYERS}
    assert PermissionKeys.MANAGE_API_CREDENTIALS not in representative


def test_disposition_outreach_permissions_are_bootstrap_discoverable() -> None:
    permission_keys = {permission.key for permission in PERMISSIONS}
    assert PermissionKeys.MANAGE_DISPOSITION_OUTREACH in permission_keys
    assert PermissionKeys.APPROVE_DISPOSITION_OUTREACH in permission_keys
    assert PermissionKeys.MANAGE_DISPOSITION_OUTREACH in ALL_PERMISSION_KEYS
    assert PermissionKeys.APPROVE_DISPOSITION_OUTREACH in ALL_PERMISSION_KEYS
    assert PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH in permission_keys
    assert PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH in ALL_PERMISSION_KEYS


@pytest.mark.parametrize(
    "role_key",
    ["acquisition_rep", "read_only_partner", "restricted_vendor"],
)
def test_non_disposition_roles_cannot_read_outreach_sensitive_details(
    role_key: str,
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_role(
        db_session,
        role_key=role_key,
        email=f"{role_key.replace('_', '-')}@example.com",
    )

    response = client.get(
        f"/api/v1/dispositions/cases/{uuid4()}/outreach",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing permission: buyers:view"
    for sensitive_key in (
        "captured_email",
        "captured_phone",
        "destination",
        "body_hash",
        "provider_message_id",
    ):
        assert sensitive_key not in response.text


def test_buyer_view_alone_does_not_grant_outreach_workspace_access(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_role(
        db_session,
        role_key="operations_assistant",
        email="buyer-view-without-outreach@example.com",
    )

    response = client.get(
        f"/api/v1/dispositions/cases/{uuid4()}/outreach",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Missing one of permissions:")
    assert PermissionKeys.MANAGE_DISPOSITION_OUTREACH in response.json()["detail"]
    assert PermissionKeys.APPROVE_DISPOSITION_OUTREACH in response.json()["detail"]


@pytest.mark.parametrize("role_key", ["owner", "disposition_manager", "disposition_rep"])
def test_owner_and_disposition_roles_pass_outreach_route_authorization(
    role_key: str,
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_role(
        db_session,
        role_key=role_key,
        email=f"authorized-{role_key.replace('_', '-')}@example.com",
    )

    response = client.get(
        f"/api/v1/dispositions/cases/{uuid4()}/outreach",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Disposition case not found."


def test_outreach_mutations_require_buyer_visibility_before_returning_revision_data(
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    headers = _headers_for_permissions(
        db_session,
        email="outreach-authority-without-buyers@example.com",
        permission_keys={
            PermissionKeys.VIEW_DEALS,
            PermissionKeys.MANAGE_DISPOSITION_OUTREACH,
            PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
            PermissionKeys.SEND_BULK_COMMUNICATIONS,
        },
    )
    case_id = uuid4()
    campaign_id = uuid4()
    revision_id = uuid4()
    control_payload = {"expected_lock_version": 1, "reason": "RBAC route test"}
    requests = [
        client.post(
            f"/api/v1/dispositions/cases/{case_id}/outreach/drafts",
            headers=headers,
            json={
                "campaign_id": str(campaign_id),
                "recipients": [
                    {
                        "campaign_recipient_id": str(uuid4()),
                        "channels": ["email"],
                    }
                ],
                "email_sender_alias_id": str(uuid4()),
                "email_subject": "Buyer opportunity",
                "email_body": "Review the approved property package.",
            },
        ),
        client.post(
            (f"/api/v1/dispositions/campaigns/{campaign_id}/outreach/{revision_id}/approve"),
            headers=headers,
            json={
                "expected_lock_version": 1,
                "expected_approval_hash": "a" * 64,
                "attestation": True,
                "reason": "RBAC route test",
            },
        ),
    ]
    requests.extend(
        client.post(
            (f"/api/v1/dispositions/campaigns/{campaign_id}/outreach/{revision_id}/{action}"),
            headers=headers,
            json=control_payload,
        )
        for action in ("release", "pause", "resume", "cancel-unsent", "retry-failed")
    )

    assert len(requests) == 7
    for response in requests:
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Missing permission: buyers:view"
        assert "deliveries" not in response.text


@pytest.mark.parametrize("action", ["release", "resume", "retry-failed"])
def test_bulk_control_routes_accept_narrow_or_legacy_authority_only(
    action: str,
    db_session: Session,
    api_db_override: None,
) -> None:
    client = TestClient(app)
    common = {
        PermissionKeys.VIEW_DEALS,
        PermissionKeys.VIEW_BUYERS,
        PermissionKeys.APPROVE_DISPOSITION_OUTREACH,
    }
    narrow_headers = _headers_for_permissions(
        db_session,
        email=f"narrow-{action}@example.com",
        permission_keys=common | {PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH},
    )
    legacy_headers = _headers_for_permissions(
        db_session,
        email=f"legacy-{action}@example.com",
        permission_keys=common | {PermissionKeys.SEND_BULK_COMMUNICATIONS},
    )
    missing_headers = _headers_for_permissions(
        db_session,
        email=f"missing-{action}@example.com",
        permission_keys=common,
    )
    url = (
        f"/api/v1/dispositions/campaigns/{uuid4()}/outreach/{uuid4()}/{action}"
    )
    payload = {"expected_lock_version": 1, "reason": "RBAC route authority test"}

    narrow = client.post(url, headers=narrow_headers, json=payload)
    legacy = client.post(url, headers=legacy_headers, json=payload)
    missing = client.post(url, headers=missing_headers, json=payload)

    assert narrow.status_code == 404, narrow.text
    assert legacy.status_code == 404, legacy.text
    assert missing.status_code == 403, missing.text
    assert PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH in missing.json()["detail"]
    assert PermissionKeys.SEND_BULK_COMMUNICATIONS in missing.json()["detail"]
