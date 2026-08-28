from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import (
    DispositionOutreachDelivery,
    DispositionOutreachRevision,
    DispositionReplyLink,
)

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0117_disposition_outreach_foundation.py"
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


def migration_columns(items: tuple[object, ...]) -> dict[str, sa.Column[Any]]:
    return {
        str(item.name): item
        for item in items
        if isinstance(item, sa.Column)
    }


def named_constraints(items: tuple[object, ...]) -> dict[str, sa.Constraint]:
    return {
        str(item.name): item
        for item in items
        if isinstance(item, sa.Constraint) and item.name is not None
    }


def foreign_key_signature(constraint: sa.ForeignKeyConstraint) -> tuple[object, ...]:
    return (
        tuple(constraint.column_keys),
        tuple(element.target_fullname for element in constraint.elements),
        constraint.ondelete,
    )


def migration_index_signature(
    recorder: MigrationRecorder,
    table_name: str,
) -> set[tuple[object, ...]]:
    return {
        (name, columns, bool(kwargs.get("unique", False)))
        for name, recorded_table, columns, kwargs in recorder.created_indexes
        if recorded_table == table_name
    }


def model_index_signature(table: sa.Table) -> set[tuple[object, ...]]:
    return {
        (
            str(index.name),
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in table.indexes
    }


def test_disposition_outreach_migration_matches_canonical_models() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    assert namespace["revision"] == "0117_disposition_outreach_foundation"
    assert namespace["down_revision"] == "0116_disposition_package_versions"
    namespace["upgrade"]()

    models = {
        "disposition_outreach_revisions": DispositionOutreachRevision,
        "disposition_outreach_deliveries": DispositionOutreachDelivery,
        "disposition_reply_links": DispositionReplyLink,
    }
    created_tables = dict(recorder.created_tables)
    assert set(created_tables) == set(models)

    for table_name, model in models.items():
        items = created_tables[table_name]
        migration_table_columns = migration_columns(items)
        assert set(migration_table_columns) == set(model.__table__.columns.keys())
        assert migration_index_signature(recorder, table_name) == model_index_signature(
            model.__table__
        )

        migration_constraints = named_constraints(items)
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
            foreign_key_signature(item)
            for item in items
            if isinstance(item, sa.ForeignKeyConstraint)
        }
        model_foreign_keys = {
            foreign_key_signature(constraint)
            for constraint in model.__table__.foreign_key_constraints
        }
        assert migration_foreign_keys == model_foreign_keys


def test_reply_links_can_persist_before_a_candidate_is_resolved() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    namespace["upgrade"]()
    columns = migration_columns(dict(recorder.created_tables)["disposition_reply_links"])

    for column_name in (
        "outreach_delivery_id",
        "outreach_revision_id",
        "disposition_campaign_id",
        "disposition_case_id",
        "buyer_id",
    ):
        assert columns[column_name].nullable is True
        assert DispositionReplyLink.__table__.columns[column_name].nullable is True
    assert columns["communication_record_id"].nullable is False


def test_disposition_outreach_downgrade_only_removes_ds6_tables() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "disposition_reply_links",
        "disposition_outreach_deliveries",
        "disposition_outreach_revisions",
    ]
    assert {table_name for _, table_name in recorder.dropped_indexes} == {
        "disposition_reply_links",
        "disposition_outreach_deliveries",
        "disposition_outreach_revisions",
    }
