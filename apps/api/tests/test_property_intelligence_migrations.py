from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATIONS = Path(__file__).parents[1] / "alembic" / "versions"


class MigrationRecorder:
    def __init__(self) -> None:
        self.tables: dict[str, tuple[Any, ...]] = {}
        self.alterations: list[tuple[str, str, dict[str, Any]]] = []

    def add_column(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def create_table(self, name: str, *elements: Any, **_kwargs: Any) -> None:
        self.tables[name] = elements

    def alter_column(self, table: str, column: str, **kwargs: Any) -> None:
        self.alterations.append((table, column, kwargs))


def migration_namespace(filename: str, recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATIONS / filename))
    namespace["upgrade"].__globals__["op"] = recorder
    return namespace


def test_property_intelligence_fresh_tables_have_timestamp_defaults() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace("0089_property_intelligence_hub.py", recorder)

    namespace["upgrade"]()

    for table_name in ("property_intelligence_snapshots", "property_research_runs"):
        columns = {
            element.name: element
            for element in recorder.tables[table_name]
            if isinstance(element, sa.Column)
        }
        assert columns["created_at"].server_default is not None
        assert columns["updated_at"].server_default is not None


def test_property_timestamp_repair_sets_defaults_on_deployed_tables() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace("0090_property_timestamp_defaults.py", recorder)

    namespace["upgrade"]()

    expected = {
        (table_name, column_name)
        for table_name in ("property_intelligence_snapshots", "property_research_runs")
        for column_name in ("created_at", "updated_at")
    }
    assert {(table, column) for table, column, _ in recorder.alterations} == expected
    assert all(change["server_default"] is not None for _, _, change in recorder.alterations)
