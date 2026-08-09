from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATIONS = Path(__file__).parents[1] / "alembic" / "versions"


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.tables: dict[str, tuple[Any, ...]] = {}
        self.statements: list[str] = []
        self.dropped_tables: list[str] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table, column))

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.indexes.append((name, table, tuple(columns)))

    def create_table(self, name: str, *elements: Any) -> None:
        self.tables[name] = elements

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))

    def drop_table(self, name: str) -> None:
        self.dropped_tables.append(name)

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATIONS / "0092_land_identity_and_valuation.py"))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def column_names(elements: tuple[Any, ...]) -> set[str]:
    return {
        element.name
        for element in elements
        if isinstance(element, sa.Column)
    }


def constraint_names(elements: tuple[Any, ...]) -> set[str | None]:
    return {
        element.name
        for element in elements
        if isinstance(element, sa.Constraint)
    }


def test_land_identity_and_valuation_migration_builds_dedicated_tables() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["down_revision"] == "0091_unified_asset_foundation"
    namespace["upgrade"]()

    assert [(table, column.name) for table, column in recorder.added_columns] == [
        ("properties", "normalized_parcel_key")
    ]
    assert (
        "ix_properties_normalized_parcel_key",
        "properties",
        ("normalized_parcel_key",),
    ) in recorder.indexes
    assert any("_county$" in statement for statement in recorder.statements)
    assert set(recorder.tables) == {
        "land_offer_policy_versions",
        "land_valuation_analyses",
    }

    analysis_columns = column_names(recorder.tables["land_valuation_analyses"])
    assert {
        "property_snapshot_id",
        "source_analysis_id",
        "policy_version_id",
        "valuation_profile",
        "analysis_fingerprint",
        "request_idempotency_key",
        "valuation_basis",
        "subject_acres_ten_thousandths",
        "selected_comps",
        "guidance_status",
        "guidance_blockers",
        "policy_snapshot",
    } <= analysis_columns
    assert {
        "uq_land_valuation_lead_version",
        "uq_land_valuation_lead_fingerprint",
        "uq_land_valuation_lead_idempotency",
        "ck_land_valuation_positive_acres",
    } <= constraint_names(recorder.tables["land_valuation_analyses"])


def test_land_identity_and_valuation_downgrade_removes_dependents_first() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "land_valuation_analyses",
        "land_offer_policy_versions",
    ]
    assert recorder.dropped_indexes == [
        ("ix_properties_normalized_parcel_key", "properties")
    ]
    assert recorder.dropped_columns == [("properties", "normalized_parcel_key")]
