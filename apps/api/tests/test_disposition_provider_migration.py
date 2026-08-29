from pathlib import Path
from runpy import run_path
from typing import Any, cast

import sqlalchemy as sa

from app.models.foundation import (
    DispositionProviderAccount,
    DispositionProviderEvidence,
    DispositionProviderListing,
    DispositionProviderListingRevision,
    DispositionProviderSourceLink,
    DispositionProviderSyncRun,
)

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0119_disposition_provider.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], dict[str, object]]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_tables: list[str] = []

    def create_table(self, table_name: str, *items: object) -> None:
        self.created_tables.append((table_name, items))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **kwargs: object,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns), kwargs))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, table_name: str) -> None:
        self.dropped_tables.append(table_name)

    @staticmethod
    def f(name: str) -> str:
        return name


def _namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def _columns(items: tuple[object, ...]) -> dict[str, sa.Column[Any]]:
    return {str(item.name): item for item in items if isinstance(item, sa.Column)}


def _named_constraints(items: tuple[object, ...]) -> dict[str, sa.Constraint]:
    return {
        str(item.name): item
        for item in items
        if isinstance(item, sa.Constraint) and item.name is not None
    }


def _foreign_key_signature(constraint: sa.ForeignKeyConstraint) -> tuple[object, ...]:
    return (
        tuple(constraint.column_keys),
        tuple(element.target_fullname for element in constraint.elements),
        constraint.ondelete,
    )


def _migration_indexes(
    recorder: MigrationRecorder,
    table_name: str,
) -> set[tuple[object, ...]]:
    return {
        (name, columns, bool(kwargs.get("unique", False)))
        for name, recorded_table, columns, kwargs in recorder.created_indexes
        if recorded_table == table_name
    }


def _model_indexes(table: sa.Table) -> set[tuple[object, ...]]:
    return {
        (str(index.name), tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def test_ds8_migration_matches_provider_models() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    assert namespace["revision"] == "0119_disposition_provider"
    assert namespace["down_revision"] == "0118_disposition_offer_room"
    namespace["upgrade"]()

    models = {
        "disposition_provider_accounts": DispositionProviderAccount,
        "disposition_provider_listings": DispositionProviderListing,
        "disposition_provider_listing_revisions": DispositionProviderListingRevision,
        "disposition_provider_source_links": DispositionProviderSourceLink,
        "disposition_provider_evidence": DispositionProviderEvidence,
        "disposition_provider_sync_runs": DispositionProviderSyncRun,
    }
    created_tables = dict(recorder.created_tables)
    assert set(created_tables) == set(models)

    for table_name, model in models.items():
        items = created_tables[table_name]
        table = cast(sa.Table, model.__table__)
        assert set(_columns(items)) == set(table.columns.keys())
        assert _migration_indexes(recorder, table_name) == _model_indexes(table)

        migration_constraints = _named_constraints(items)
        model_constraints = {
            str(item.name): item
            for item in table.constraints
            if item.name is not None
        }
        assert set(migration_constraints) == set(model_constraints)
        assert {
            name: str(item.sqltext)
            for name, item in migration_constraints.items()
            if isinstance(item, sa.CheckConstraint)
        } == {
            name: str(item.sqltext)
            for name, item in model_constraints.items()
            if isinstance(item, sa.CheckConstraint)
        }
        assert {
            _foreign_key_signature(item)
            for item in items
            if isinstance(item, sa.ForeignKeyConstraint)
        } == {
            _foreign_key_signature(item) for item in table.foreign_key_constraints
        }


def test_ds8_downgrade_removes_only_provider_schema_in_dependency_order() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "disposition_provider_sync_runs",
        "disposition_provider_evidence",
        "disposition_provider_source_links",
        "disposition_provider_listing_revisions",
        "disposition_provider_listings",
        "disposition_provider_accounts",
    ]
    assert {table for _, table in recorder.dropped_indexes} == set(recorder.dropped_tables)
