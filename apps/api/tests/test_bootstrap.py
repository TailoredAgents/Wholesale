from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.rbac import ALL_PERMISSION_KEYS, ROLES
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
        organization_name="Oakwell Home Buyers",
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
        organization_name="Oakwell Home Buyers",
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
