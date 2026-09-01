from pathlib import Path
from runpy import run_path
from typing import Any
from unittest.mock import ANY

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.rbac import PermissionKeys
from app.models.foundation import (
    DispositionBuyerSelection,
    DispositionCase,
    DispositionOutreachRevision,
    DispositionPackageShareLink,
    DispositionProviderListingRevision,
    Permission,
    Role,
    RolePermission,
)
from app.services.bootstrap import bootstrap_foundation

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0123_disposition_advisory_workbench.py"
)


class _ScalarResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _Bind:
    def __init__(self, null_setup_count: int) -> None:
        self.null_setup_count = null_setup_count
        self.statements: list[str] = []

    def execute(self, statement: object) -> _ScalarResult:
        self.statements.append(str(statement))
        return _ScalarResult(self.null_setup_count)


class _BatchRecorder:
    def __init__(self, recorder: "MigrationRecorder", table_name: str) -> None:
        self.recorder = recorder
        self.table_name = table_name

    def __enter__(self) -> "_BatchRecorder":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def alter_column(self, column_name: str, **kwargs: object) -> None:
        self.recorder.operations.append(
            ("alter_column", self.table_name, column_name, kwargs)
        )

    def drop_column(self, column_name: str) -> None:
        self.recorder.operations.append(("drop_column", self.table_name, column_name))


class MigrationRecorder:
    def __init__(self, *, null_setup_count: int = 0) -> None:
        self.operations: list[tuple[object, ...]] = []
        self.bind = _Bind(null_setup_count)

    def batch_alter_table(self, table_name: str) -> _BatchRecorder:
        return _BatchRecorder(self, table_name)

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", table_name, column))

    def get_bind(self) -> _Bind:
        return self.bind


def _namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_advisory_migration_matches_nullable_shell_and_provenance_models() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)

    assert namespace["revision"] == "0123_disposition_advisory"
    assert namespace["down_revision"] == "0122_disposition_execution"
    assert len(namespace["revision"]) <= 32
    namespace["upgrade"]()

    altered = [item for item in recorder.operations if item[0] == "alter_column"]
    assert [(item[1], item[2], item[3]["nullable"]) for item in altered] == [
        ("disposition_cases", "owner_user_id", True),
        ("disposition_cases", "compensation_plan_version_id", True),
        ("disposition_cases", "disposition_operating_mode_id", True),
    ]
    for column_name in (
        "owner_user_id",
        "compensation_plan_version_id",
        "disposition_operating_mode_id",
    ):
        assert DispositionCase.__table__.c[column_name].nullable is True

    model_columns = {
        ("disposition_buyer_selections", "advisory_snapshot"): (
            DispositionBuyerSelection.__table__.c.advisory_snapshot
        ),
        ("disposition_package_share_links", "package_status_at_issue"): (
            DispositionPackageShareLink.__table__.c.package_status_at_issue
        ),
        ("disposition_package_share_links", "was_current_at_issue"): (
            DispositionPackageShareLink.__table__.c.was_current_at_issue
        ),
        ("disposition_provider_listing_revisions", "package_status_at_prepare"): (
            DispositionProviderListingRevision.__table__.c.package_status_at_prepare
        ),
        ("disposition_provider_listing_revisions", "package_was_current_at_prepare"): (
            DispositionProviderListingRevision.__table__.c.package_was_current_at_prepare
        ),
        ("disposition_outreach_revisions", "package_status_at_prepare"): (
            DispositionOutreachRevision.__table__.c.package_status_at_prepare
        ),
        ("disposition_outreach_revisions", "package_was_current_at_prepare"): (
            DispositionOutreachRevision.__table__.c.package_was_current_at_prepare
        ),
    }
    added = {
        (str(item[1]), str(item[2].name)): item[2]
        for item in recorder.operations
        if item[0] == "add_column"
    }
    assert set(added) == set(model_columns)
    for key, column in added.items():
        model_column = model_columns[key]
        assert type(column.type) is type(model_column.type)
        assert column.nullable is model_column.nullable is True


def test_advisory_migration_revokes_only_builtin_manager_global_bulk_permission() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)

    namespace["upgrade"]()

    cleanup_statements = [
        statement
        for statement in recorder.bind.statements
        if statement.lstrip().upper().startswith("DELETE FROM ROLE_PERMISSIONS")
    ]
    assert len(cleanup_statements) == 1
    cleanup = cleanup_statements[0]
    assert "roles.id = role_permissions.role_id" in cleanup
    assert "roles.organization_id = role_permissions.organization_id" in cleanup
    assert "roles.key = 'disposition_manager'" in cleanup
    assert "permissions.key = 'communications:send_bulk'" in cleanup
    assert "disposition_rep" not in cleanup


def test_advisory_migration_bulk_cleanup_executes_safely_on_canonical_tables(
    db_session: Session,
) -> None:
    foundation = bootstrap_foundation(
        db_session,
        organization_name="Migration RBAC Upgrade Tenant",
        admin_email="migration-rbac-owner@example.com",
        admin_name="Migration RBAC Owner",
    )
    roles = {
        role.key: role
        for role in db_session.scalars(
            sa.select(Role).where(Role.organization_id == foundation.organization.id)
        ).all()
    }
    permissions = {
        permission.key: permission
        for permission in db_session.scalars(
            sa.select(Permission).where(
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
    custom = Role(
        organization_id=foundation.organization.id,
        key="custom_bulk_role",
        name="Custom bulk role",
    )
    db_session.add(custom)
    db_session.flush()
    db_session.add_all(
        [
            RolePermission(
                organization_id=foundation.organization.id,
                role_id=manager.id,
                permission_id=global_bulk.id,
            ),
            RolePermission(
                organization_id=foundation.organization.id,
                role_id=custom.id,
                permission_id=global_bulk.id,
            ),
        ]
    )
    db_session.commit()

    namespace = _namespace(MigrationRecorder())
    db_session.execute(
        sa.text(namespace["STALE_DISPOSITION_MANAGER_GLOBAL_BULK_DELETE_SQL"])
    )
    db_session.commit()

    pairs = {
        (role_id, permission_id)
        for role_id, permission_id in db_session.execute(
            sa.select(RolePermission.role_id, RolePermission.permission_id).where(
                RolePermission.organization_id == foundation.organization.id
            )
        ).all()
    }
    assert (manager.id, global_bulk.id) not in pairs
    assert (manager.id, narrow_bulk.id) in pairs
    assert (marketing.id, global_bulk.id) in pairs
    assert (custom.id, global_bulk.id) in pairs


def test_advisory_migration_downgrade_preflights_and_reverses_in_batch_order() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)

    namespace["downgrade"]()

    assert "owner_user_id IS NULL" in recorder.bind.statements[0]
    assert recorder.operations == [
        ("drop_column", "disposition_outreach_revisions", "package_was_current_at_prepare"),
        ("drop_column", "disposition_outreach_revisions", "package_status_at_prepare"),
        (
            "drop_column",
            "disposition_provider_listing_revisions",
            "package_was_current_at_prepare",
        ),
        (
            "drop_column",
            "disposition_provider_listing_revisions",
            "package_status_at_prepare",
        ),
        ("drop_column", "disposition_package_share_links", "was_current_at_issue"),
        ("drop_column", "disposition_package_share_links", "package_status_at_issue"),
        ("drop_column", "disposition_buyer_selections", "advisory_snapshot"),
        (
            "alter_column",
            "disposition_cases",
            "disposition_operating_mode_id",
            {"existing_type": ANY, "nullable": False},
        ),
        (
            "alter_column",
            "disposition_cases",
            "compensation_plan_version_id",
            {"existing_type": ANY, "nullable": False},
        ),
        (
            "alter_column",
            "disposition_cases",
            "owner_user_id",
            {"existing_type": ANY, "nullable": False},
        ),
    ]


def test_advisory_migration_refuses_partial_downgrade_with_incomplete_shells() -> None:
    recorder = MigrationRecorder(null_setup_count=1)
    namespace = _namespace(recorder)

    with pytest.raises(RuntimeError, match="setup is incomplete"):
        namespace["downgrade"]()

    assert recorder.operations == []
