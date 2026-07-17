from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_any_permission
from app.domain.rbac import PermissionKeys

router = APIRouter(prefix="/api/v1/me", tags=["me"])
workspace_access_dependency = require_any_permission(
    PermissionKeys.VIEW_LEADS,
    PermissionKeys.VIEW_ASSIGNED_LEADS,
)


@router.get("")
def read_me(
    principal: Annotated[Principal, Depends(workspace_access_dependency)],
) -> dict[str, object]:
    return {
        "user_id": str(principal.user_id),
        "organization_id": str(principal.organization_id),
        "email": principal.email,
        "permissions": sorted(principal.permission_keys),
    }
