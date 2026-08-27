from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import Buyer, BuyerCriteria

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0113_buyer_network_foundation.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.executed: list[str] = []
        self.created_foreign_keys: list[tuple[object, ...]] = []
        self.created_uniques: list[tuple[str, str, tuple[str, ...]]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], dict[str, object]]] = []
        self.altered_columns: list[tuple[str, str, dict[str, object]]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table_name, column))

    def execute(self, statement: object) -> None:
        self.executed.append(str(statement))

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

    def create_unique_constraint(
        self,
        name: str,
        table_name: str,
        columns: list[str],
    ) -> None:
        self.created_uniques.append((name, table_name, tuple(columns)))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **kwargs: object,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns), kwargs))

    def alter_column(self, table_name: str, column_name: str, **kwargs: object) -> None:
        self.altered_columns.append((table_name, column_name, kwargs))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

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


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_buyer_network_migration_matches_model_and_safely_backfills() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0113_buyer_network_foundation"
    assert namespace["down_revision"] == "0112_batchdialer_campaign_assets"
    namespace["upgrade"]()

    buyer_columns = {
        str(column.name): column
        for table, column in recorder.added_columns
        if table == "buyers"
    }
    expected_buyer_columns = {
        "normalized_email",
        "normalized_phone",
        "normalized_company_name",
        "source_key",
        "source_detail",
        "source_external_key",
        "created_by_user_id",
        "relationship_owner_user_id",
        "last_verified_at",
        "archived_at",
        "archived_by_user_id",
        "archive_reason",
    }
    assert set(buyer_columns) == expected_buyer_columns
    assert expected_buyer_columns <= set(Buyer.__table__.columns.keys())
    criteria_columns = {
        str(column.name): column
        for table, column in recorder.added_columns
        if table == "buyer_criteria"
    }
    assert set(criteria_columns) == {"version_number", "is_current"}
    assert set(criteria_columns) <= set(BuyerCriteria.__table__.columns.keys())

    sql = "\n".join(recorder.executed)
    assert "~*" in sql
    assert "ELSE NULL" in sql
    assert "SET status = 'needs_review'" in sql
    assert "normalized_email IS NULL" in sql
    assert "normalized_phone IS NULL" in sql
    assert "row_number() OVER" in sql

    one_current = next(
        item for item in recorder.created_indexes if item[0] == "uq_buyer_criteria_one_current"
    )
    assert one_current[3]["unique"] is True
    assert str(one_current[3]["postgresql_where"]) == "is_current = true"
    assert str(one_current[3]["sqlite_where"]) == "is_current = 1"
    model_index = next(
        index
        for index in BuyerCriteria.__table__.indexes
        if index.name == "uq_buyer_criteria_one_current"
    )
    assert model_index.unique is True
    assert str(model_index.dialect_options["postgresql"]["where"]) == "is_current = true"
    assert str(model_index.dialect_options["sqlite"]["where"]) == "is_current = 1"


def test_buyer_network_downgrade_removes_added_schema() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_indexes[0] == (
        "uq_buyer_criteria_one_current",
        "buyer_criteria",
    )
    assert ("buyer_criteria", "is_current") in recorder.dropped_columns
    assert ("buyer_criteria", "version_number") in recorder.dropped_columns
    assert ("buyers", "normalized_email") in recorder.dropped_columns
    assert ("buyers", "source_key") in recorder.dropped_columns
