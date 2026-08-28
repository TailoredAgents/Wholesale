from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import (
    BuyerSourceLink,
    DispositionBuyerPoolCandidate,
    DispositionBuyerPoolEntry,
    DispositionBuyerPoolRun,
)

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0115_disposition_buyer_pool.py"
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


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def _migration_columns(items: tuple[object, ...]) -> set[str]:
    return {str(item.name) for item in items if isinstance(item, sa.Column)}


def _named_constraints(
    items: tuple[object, ...],
) -> dict[str, sa.Constraint]:
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


def _migration_index_signature(
    recorder: MigrationRecorder, table_name: str
) -> set[tuple[object, ...]]:
    return {
        (name, columns, bool(kwargs.get("unique", False)))
        for name, recorded_table, columns, kwargs in recorder.created_indexes
        if recorded_table == table_name
    }


def _model_index_signature(table: sa.Table) -> set[tuple[object, ...]]:
    return {
        (
            str(index.name),
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in table.indexes
    }


def test_disposition_buyer_pool_migration_matches_canonical_models() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    assert namespace["revision"] == "0115_disposition_buyer_pool"
    assert namespace["down_revision"] == "0114_buyer_profiles_buy_boxes"
    namespace["upgrade"]()

    models = {
        "buyer_source_links": BuyerSourceLink,
        "disposition_buyer_pool_runs": DispositionBuyerPoolRun,
        "disposition_buyer_pool_candidates": DispositionBuyerPoolCandidate,
        "disposition_buyer_pool_entries": DispositionBuyerPoolEntry,
    }
    created_tables = dict(recorder.created_tables)
    assert set(created_tables) == set(models)

    for table_name, model in models.items():
        items = created_tables[table_name]
        assert _migration_columns(items) == set(model.__table__.columns.keys())
        assert _migration_index_signature(recorder, table_name) == _model_index_signature(
            model.__table__
        )

        migration_constraints = _named_constraints(items)
        model_constraints = {
            str(constraint.name): constraint
            for constraint in model.__table__.constraints
            if constraint.name is not None
        }
        assert set(migration_constraints) == set(model_constraints)

        migration_checks = {
            name: str(constraint.sqltext)
            for name, constraint in migration_constraints.items()
            if isinstance(constraint, sa.CheckConstraint)
        }
        model_checks = {
            name: str(constraint.sqltext)
            for name, constraint in model_constraints.items()
            if isinstance(constraint, sa.CheckConstraint)
        }
        assert migration_checks == model_checks

        migration_foreign_keys = {
            _foreign_key_signature(item)
            for item in items
            if isinstance(item, sa.ForeignKeyConstraint)
        }
        model_foreign_keys = {
            _foreign_key_signature(constraint)
            for constraint in model.__table__.foreign_key_constraints
        }
        assert migration_foreign_keys == model_foreign_keys


def test_disposition_buyer_pool_downgrade_only_removes_new_tables() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "disposition_buyer_pool_entries",
        "disposition_buyer_pool_candidates",
        "disposition_buyer_pool_runs",
        "buyer_source_links",
    ]
    assert {table_name for _, table_name in recorder.dropped_indexes} == {
        "disposition_buyer_pool_entries",
        "disposition_buyer_pool_candidates",
        "disposition_buyer_pool_runs",
        "buyer_source_links",
    }
