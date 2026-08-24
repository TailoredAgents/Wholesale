from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0112_batchdialer_campaign_asset_mapping.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.created_checks: list[tuple[str, str, str]] = []
        self.created_foreign_keys: list[tuple[object, ...]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table_name, column))

    def create_check_constraint(self, name: str, table_name: str, condition: str) -> None:
        self.created_checks.append((name, table_name, condition))

    def create_foreign_key(
        self,
        name: str,
        source_table: str,
        referent_table: str,
        local_cols: list[str],
        remote_cols: list[str],
        **kwargs: object,
    ) -> None:
        self.created_foreign_keys.append(
            (
                name,
                source_table,
                referent_table,
                tuple(local_cols),
                tuple(remote_cols),
                kwargs.get("ondelete"),
            )
        )

    def drop_constraint(
        self,
        name: str,
        table_name: str,
        *,
        type_: str | None = None,
    ) -> None:
        self.dropped_constraints.append((name, table_name, type_))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))


def _migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_campaign_asset_mapping_migration_is_nullable_and_constrained() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    assert namespace["revision"] == "0112_batchdialer_campaign_assets"
    assert namespace["down_revision"] == "0111_batchdialer_va_facts"

    namespace["upgrade"]()

    columns = {str(column.name): column for _, column in recorder.added_columns}
    assert columns.keys() == {
        "asset_class",
        "asset_class_mapped_by_user_id",
        "asset_class_mapped_at",
    }
    assert all(table == "batchdialer_campaigns" for table, _ in recorder.added_columns)
    assert all(column.nullable is True for column in columns.values())
    assert columns["asset_class"].server_default is None
    assert recorder.created_checks == [
        (
            "ck_batchdialer_campaigns_asset_class",
            "batchdialer_campaigns",
            "asset_class IS NULL OR asset_class IN ('house', 'land')",
        )
    ]
    assert recorder.created_foreign_keys == [
        (
            "fk_batchdialer_campaigns_asset_mapped_by_user",
            "batchdialer_campaigns",
            "users",
            ("asset_class_mapped_by_user_id",),
            ("id",),
            "SET NULL",
        )
    ]


def test_campaign_asset_mapping_downgrade_removes_dependencies_first() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_constraints == [
        (
            "fk_batchdialer_campaigns_asset_mapped_by_user",
            "batchdialer_campaigns",
            "foreignkey",
        ),
        (
            "ck_batchdialer_campaigns_asset_class",
            "batchdialer_campaigns",
            "check",
        ),
    ]
    assert recorder.dropped_columns == [
        ("batchdialer_campaigns", "asset_class_mapped_at"),
        ("batchdialer_campaigns", "asset_class_mapped_by_user_id"),
        ("batchdialer_campaigns", "asset_class"),
    ]
