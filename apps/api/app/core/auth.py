import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.foundation import Permission, RoleAssignment, RolePermission, User


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    permission_keys: frozenset[str]


def get_current_principal(
    db: Annotated[Session, Depends(get_db)],
    x_dev_user_email: Annotated[str | None, Header(alias="X-Dev-User-Email")] = None,
) -> Principal:
    settings = get_settings()
    if settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Production authentication provider is not configured yet.",
        )
    if not x_dev_user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing development user header.",
        )

    user = db.scalar(select(User).where(User.email == x_dev_user_email.lower().strip()))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user.")

    permission_keys = frozenset(
        db.scalars(
            select(distinct(Permission.key))
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(RoleAssignment, RoleAssignment.role_id == RolePermission.role_id)
            .where(
                RoleAssignment.organization_id == user.organization_id,
                RoleAssignment.user_id == user.id,
            )
        )
    )
    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        permission_keys=permission_keys,
    )


def require_permission(permission_key: str) -> Callable[[Principal], Principal]:
    def dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if permission_key not in principal.permission_keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )
        return principal

    return dependency
