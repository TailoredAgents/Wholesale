from pytest import MonkeyPatch
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli import bootstrap_from_env
from app.core.config import get_settings
from app.domain.rbac import ALL_PERMISSION_KEYS, ROLES, PermissionKeys
from app.models.foundation import (
    AuditEvent,
    Organization,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from app.services.bootstrap import bootstrap_foundation


def count_rows(db: Session, model: type[object]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_bootstrap_foundation_is_idempotent(db_session: Session) -> None:
    first = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    counts_after_first = {
        "organizations": count_rows(db_session, Organization),
        "users": count_rows(db_session, User),
        "permissions": count_rows(db_session, Permission),
        "roles": count_rows(db_session, Role),
        "role_permissions": count_rows(db_session, RolePermission),
        "role_assignments": count_rows(db_session, RoleAssignment),
        "audit_events": count_rows(db_session, AuditEvent),
    }

    second = bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    counts_after_second = {
        "organizations": count_rows(db_session, Organization),
        "users": count_rows(db_session, User),
        "permissions": count_rows(db_session, Permission),
        "roles": count_rows(db_session, Role),
        "role_permissions": count_rows(db_session, RolePermission),
        "role_assignments": count_rows(db_session, RoleAssignment),
        "audit_events": count_rows(db_session, AuditEvent),
    }

    assert first.organization.id == second.organization.id
    assert first.admin_user is not None
    assert second.admin_user is not None
    assert first.admin_user.id == second.admin_user.id
    assert counts_after_second == counts_after_first
    assert counts_after_second["permissions"] == len(ALL_PERMISSION_KEYS)
    assert counts_after_second["roles"] == len(ROLES)
    assert counts_after_second["audit_events"] == 1


def test_bootstrap_refreshes_roles_for_legacy_organizations(db_session: Session) -> None:
    legacy = bootstrap_foundation(
        db_session,
        organization_name="Oakwell Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    owner_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == legacy.organization.id,
            Role.key == "owner",
        )
    )
    operations_permissions = db_session.scalars(
        select(Permission).where(
            Permission.key.in_(
                (
                    PermissionKeys.VIEW_ACQUISITION_OPERATIONS,
                    PermissionKeys.MANAGE_ACQUISITION_OPERATIONS,
                    PermissionKeys.WORK_ASSIGNED_CALLING_LISTS,
                )
            )
        )
    ).all()
    assert owner_role is not None
    db_session.execute(
        delete(RolePermission).where(
            RolePermission.organization_id == legacy.organization.id,
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id.in_([item.id for item in operations_permissions]),
        )
    )
    db_session.commit()

    bootstrap_foundation(
        db_session,
        organization_name="Stonegate Home Buyers",
        admin_email="owner@example.com",
        admin_name="Owner",
    )

    restored_count = db_session.scalar(
        select(func.count())
        .select_from(RolePermission)
        .where(
            RolePermission.organization_id == legacy.organization.id,
            RolePermission.role_id == owner_role.id,
            RolePermission.permission_id.in_([item.id for item in operations_permissions]),
        )
    )
    assert restored_count == 3


def test_bootstrap_grants_disposition_view_to_custom_human_roles(
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Custom Role Workspace",
        admin_email="owner@example.com",
        admin_name="Owner",
    )
    custom_role = Role(
        organization_id=foundation.organization.id,
        key="legacy_team_member",
        name="Legacy team member",
    )
    db_session.add(custom_role)
    db_session.commit()

    bootstrap_foundation(
        db_session,
        organization_name="Custom Role Workspace",
        admin_email="owner@example.com",
        admin_name="Owner",
    )

    disposition_view = db_session.scalar(
        select(Permission).where(Permission.key == PermissionKeys.VIEW_DISPOSITIONS)
    )
    assert disposition_view is not None
    assert db_session.scalar(
        select(RolePermission).where(
            RolePermission.organization_id == foundation.organization.id,
            RolePermission.role_id == custom_role.id,
            RolePermission.permission_id == disposition_view.id,
        )
    ) is not None
    ai_service_role = db_session.scalar(
        select(Role).where(
            Role.organization_id == foundation.organization.id,
            Role.key == "ai_service",
        )
    )
    assert ai_service_role is not None
    assert db_session.scalar(
        select(RolePermission).where(
            RolePermission.organization_id == foundation.organization.id,
            RolePermission.role_id == ai_service_role.id,
            RolePermission.permission_id == disposition_view.id,
        )
    ) is None


def test_bootstrap_replaces_only_builtin_manager_global_bulk_authority(
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Legacy Dispositions Roles",
        admin_email="legacy-dispositions-owner@example.com",
        admin_name="Legacy Dispositions Owner",
    )
    roles = {
        role.key: role
        for role in db_session.scalars(
            select(Role).where(Role.organization_id == foundation.organization.id)
        ).all()
    }
    permissions = {
        permission.key: permission
        for permission in db_session.scalars(
            select(Permission).where(
                Permission.key.in_(
                    {
                        PermissionKeys.SEND_BULK_COMMUNICATIONS,
                        PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH,
                    }
                )
            )
        ).all()
    }
    manager = roles["disposition_manager"]
    marketing = roles["marketing_manager"]
    global_bulk = permissions[PermissionKeys.SEND_BULK_COMMUNICATIONS]
    narrow_bulk = permissions[PermissionKeys.SEND_DISPOSITION_BULK_OUTREACH]
    custom_role = Role(
        organization_id=foundation.organization.id,
        key="custom_disposition_partner",
        name="Custom disposition partner",
    )
    db_session.add(custom_role)
    db_session.flush()
    db_session.execute(
        delete(RolePermission).where(
            RolePermission.organization_id == foundation.organization.id,
            RolePermission.role_id == manager.id,
            RolePermission.permission_id == narrow_bulk.id,
        )
    )
    db_session.add_all(
        [
            RolePermission(
                organization_id=foundation.organization.id,
                role_id=manager.id,
                permission_id=global_bulk.id,
            ),
            RolePermission(
                organization_id=foundation.organization.id,
                role_id=custom_role.id,
                permission_id=global_bulk.id,
            ),
        ]
    )
    db_session.commit()

    bootstrap_foundation(
        db_session,
        organization_name="Legacy Dispositions Roles",
        admin_email="legacy-dispositions-owner@example.com",
        admin_name="Legacy Dispositions Owner",
    )

    permission_pairs = {
        (role_id, permission_id)
        for role_id, permission_id in db_session.execute(
            select(RolePermission.role_id, RolePermission.permission_id).where(
                RolePermission.organization_id == foundation.organization.id
            )
        ).all()
    }
    assert (manager.id, global_bulk.id) not in permission_pairs
    assert (manager.id, narrow_bulk.id) in permission_pairs
    assert (custom_role.id, global_bulk.id) in permission_pairs
    assert (marketing.id, global_bulk.id) in permission_pairs


def test_executed_contract_catchup_permission_is_narrowly_assigned() -> None:
    role_permissions = {role.key: set(role.permission_keys) for role in ROLES}

    for role_key in ("owner", "founder_operator", "ceo"):
        assert PermissionKeys.RECORD_EXECUTED_CONTRACTS in role_permissions[role_key]
    for role_key in ("acquisition_manager", "acquisition_rep", "transaction_coordinator"):
        assert PermissionKeys.RECORD_EXECUTED_CONTRACTS in role_permissions[role_key]
    for role_key in (
        "administrator",
        "operations_assistant",
        "prospecting_caller",
        "disposition_manager",
        "disposition_rep",
        "marketing_manager",
        "finance_accounting",
        "read_only_partner",
        "restricted_vendor",
    ):
        assert PermissionKeys.RECORD_EXECUTED_CONTRACTS not in role_permissions[role_key]


def test_internal_company_roles_can_view_the_complete_disposition_workspace() -> None:
    role_permissions = {role.key: set(role.permission_keys) for role in ROLES}
    required = {PermissionKeys.VIEW_DISPOSITIONS}

    for role_key in (
        "administrator",
        "operations_assistant",
        "acquisition_manager",
        "acquisition_rep",
        "prospecting_caller",
        "disposition_manager",
        "disposition_rep",
        "transaction_coordinator",
        "marketing_manager",
        "finance_accounting",
    ):
        assert required <= role_permissions[role_key]


def test_bootstrap_from_env_logs_before_session_objects_detach(
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    testing_session = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(bootstrap_from_env, "SessionLocal", testing_session)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_NAME", "Owner")
    get_settings.cache_clear()

    try:
        bootstrap_from_env.main()
    finally:
        get_settings.cache_clear()

    with testing_session() as verification_session:
        user = verification_session.scalar(select(User).where(User.email == "owner@example.com"))
        assert user is not None
