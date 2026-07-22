from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.database import get_db
from app.models.foundation import Notification, Role, RoleAssignment, User

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("")
def read_me(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    user = db.get(User, principal.user_id)
    role_keys = sorted(
        db.scalars(
            select(Role.key)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.organization_id == principal.organization_id,
                RoleAssignment.user_id == principal.user_id,
            )
        )
    )
    unread_notification_count = int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.organization_id == principal.organization_id,
                Notification.recipient_user_id == principal.user_id,
                Notification.read_at.is_(None),
            )
        )
        or 0
    )
    return {
        "user_id": str(principal.user_id),
        "organization_id": str(principal.organization_id),
        "email": principal.email,
        "display_name": user.display_name if user is not None else principal.email,
        "role_keys": role_keys,
        "permissions": sorted(principal.permission_keys),
        "unread_notification_count": unread_notification_count,
    }
