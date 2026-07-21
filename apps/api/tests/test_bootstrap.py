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
