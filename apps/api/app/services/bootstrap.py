from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.rbac import PERMISSIONS, ROLES
from app.models.foundation import (
    AuditEvent,
    Organization,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)


@dataclass(frozen=True)
class BootstrapResult:
    organization: Organization
    admin_user: User | None
    permissions_count: int
    roles_count: int


def slugify(value: str) -> str:
    normalized = "".join(character.lower() if character.isalnum() else "-" for character in value)
    parts = [part for part in normalized.split("-") if part]
    return "-".join(parts) or "organization"


def scalar_count(db: Session, statement: Select[Any]) -> int:
    return int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)


def bootstrap_foundation(
    db: Session,
    *,
    organization_name: str,
    admin_email: str | None = None,
    admin_name: str | None = None,
) -> BootstrapResult:
    organization = ensure_organization(db, organization_name)
    permissions_by_key = ensure_permissions(db)
    roles_by_key = ensure_roles(db, organization)
    ensure_role_permissions(db, organization, permissions_by_key, roles_by_key)
    admin_user = ensure_admin_user(db, organization, admin_email, admin_name)
    maybe_record_bootstrap_audit(db, organization, admin_user)
    db.commit()
    return BootstrapResult(
        organization=organization,
        admin_user=admin_user,
        permissions_count=scalar_count(db, select(Permission.id)),
        roles_count=scalar_count(
            db, select(Role.id).where(Role.organization_id == organization.id)
        ),
    )


def ensure_organization(db: Session, organization_name: str) -> Organization:
    slug = slugify(organization_name)
    organization = db.scalar(select(Organization).where(Organization.slug == slug))
    if organization is not None:
        return organization

    organization = Organization(name=organization_name, slug=slug)
    db.add(organization)
    db.flush()
    return organization


def ensure_permissions(db: Session) -> dict[str, Permission]:
    existing = {permission.key: permission for permission in db.scalars(select(Permission))}
    for definition in PERMISSIONS:
        permission = existing.get(definition.key)
        if permission is None:
            permission = Permission(
                key=definition.key,
                name=definition.name,
                description=definition.description,
            )
            db.add(permission)
            existing[definition.key] = permission
        else:
            permission.name = definition.name
            permission.description = definition.description
    db.flush()
    return existing


def ensure_roles(db: Session, organization: Organization) -> dict[str, Role]:
    existing = {
        role.key: role
        for role in db.scalars(select(Role).where(Role.organization_id == organization.id))
    }
    for definition in ROLES:
        role = existing.get(definition.key)
        if role is None:
            role = Role(organization_id=organization.id, key=definition.key, name=definition.name)
            db.add(role)
            existing[definition.key] = role
        else:
            role.name = definition.name
    db.flush()
    return existing


def ensure_role_permissions(
    db: Session,
    organization: Organization,
    permissions_by_key: dict[str, Permission],
    roles_by_key: dict[str, Role],
) -> None:
    existing_pairs = {
        (role_permission.role_id, role_permission.permission_id)
        for role_permission in db.scalars(
            select(RolePermission).where(RolePermission.organization_id == organization.id)
        )
    }
    for role_definition in ROLES:
        role = roles_by_key[role_definition.key]
        for permission_key in role_definition.permission_keys:
            permission = permissions_by_key[permission_key]
            pair = (role.id, permission.id)
            if pair not in existing_pairs:
                db.add(
                    RolePermission(
                        organization_id=organization.id,
                        role_id=role.id,
                        permission_id=permission.id,
                    )
                )
                existing_pairs.add(pair)
    db.flush()


def ensure_admin_user(
    db: Session,
    organization: Organization,
    admin_email: str | None,
    admin_name: str | None,
) -> User | None:
    if not admin_email:
        return None

    normalized_email = admin_email.lower().strip()
    user = db.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == normalized_email,
        )
    )
    if user is None:
        user = User(
            organization_id=organization.id,
            email=normalized_email,
            display_name=admin_name or normalized_email,
            is_active=True,
        )
        db.add(user)
        db.flush()

    owner_role = db.scalar(
        select(Role).where(Role.organization_id == organization.id, Role.key == "owner")
    )
    if owner_role is None:
        raise RuntimeError("owner role was not seeded")

    assignment = db.scalar(
        select(RoleAssignment).where(
            RoleAssignment.organization_id == organization.id,
            RoleAssignment.user_id == user.id,
            RoleAssignment.role_id == owner_role.id,
        )
    )
    if assignment is None:
        db.add(
            RoleAssignment(
                organization_id=organization.id,
                user_id=user.id,
                role_id=owner_role.id,
            )
        )
        db.flush()
    return user


def maybe_record_bootstrap_audit(
    db: Session,
    organization: Organization,
    admin_user: User | None,
) -> None:
    existing = db.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization.id,
            AuditEvent.action == "bootstrap.foundation",
        )
    )
    if existing is not None:
        return

    db.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=admin_user.id if admin_user else None,
            actor_type="system",
            action="bootstrap.foundation",
            entity_type="organization",
            entity_id=organization.id,
            previous_value=None,
            new_value={"organization_slug": organization.slug},
            reason="Initial local bootstrap",
        )
    )
