"""Grant every human workspace role disposition read access.

Revision ID: 0126_company_disposition_view
Revises: 0125_disposition_explicit_queues
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0126_company_disposition_view"
down_revision: str | None = "0125_disposition_explicit_queues"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

permissions = sa.table(
    "permissions",
    sa.column("id", sa.Uuid()),
    sa.column("key", sa.String()),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
)
roles = sa.table(
    "roles",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("key", sa.String()),
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("id", sa.Uuid()),
    sa.column("organization_id", sa.Uuid()),
    sa.column("role_id", sa.Uuid()),
    sa.column("permission_id", sa.Uuid()),
)

PERMISSION_KEY = "dispositions:view"


def upgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == PERMISSION_KEY)
    ).scalar_one_or_none()
    if permission_id is None:
        permission_id = uuid.uuid4()
        bind.execute(
            sa.insert(permissions).values(
                id=permission_id,
                key=PERMISSION_KEY,
                name="View dispositions",
                description=(
                    "View company disposition cases, investor workspaces, "
                    "and outreach history."
                ),
            )
        )

    existing_role_ids = set(
        bind.execute(
            sa.select(role_permissions.c.role_id).where(
                role_permissions.c.permission_id == permission_id
            )
        ).scalars()
    )
    human_roles = bind.execute(
        sa.select(roles.c.id, roles.c.organization_id).where(roles.c.key != "ai_service")
    ).all()
    for role_id, organization_id in human_roles:
        if role_id in existing_role_ids:
            continue
        bind.execute(
            sa.insert(role_permissions).values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                role_id=role_id,
                permission_id=permission_id,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    permission_id = bind.execute(
        sa.select(permissions.c.id).where(permissions.c.key == PERMISSION_KEY)
    ).scalar_one_or_none()
    if permission_id is None:
        return
    bind.execute(
        sa.delete(role_permissions).where(role_permissions.c.permission_id == permission_id)
    )
    bind.execute(sa.delete(permissions).where(permissions.c.id == permission_id))
