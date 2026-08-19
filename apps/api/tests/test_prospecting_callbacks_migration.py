from __future__ import annotations

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0108_prospecting_inbound_callbacks.py"
)


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class MigrationRecorder:
    def __init__(self, *, as_sql: bool = True, has_evidence: bool = False) -> None:
        self.as_sql = as_sql
        self.has_evidence = has_evidence
        self.operations: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_context(self) -> SimpleNamespace:
        return SimpleNamespace(as_sql=self.as_sql)

    def get_bind(self) -> MigrationRecorder:
        return self

    def execute(self, statement: object) -> _ScalarResult:
        self.operations.append(("sql", (str(statement),), {}))
        return _ScalarResult(self.has_evidence)

    def create_table(self, name: str, *items: object) -> None:
        self.operations.append(("create_table", (name, *items), {}))

    def create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        **kwargs: object,
    ) -> None:
        self.operations.append(("create_index", (name, table, tuple(columns)), kwargs))

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", (table, column), {}))

    def create_foreign_key(
        self,
        name: str,
        table: str,
        target: str,
        local_columns: list[str],
        remote_columns: list[str],
        **kwargs: object,
    ) -> None:
        self.operations.append(
            (
                "create_foreign_key",
                (name, table, target, tuple(local_columns), tuple(remote_columns)),
                kwargs,
            )
        )

    def create_unique_constraint(
        self,
        name: str,
        table: str,
        columns: list[str],
    ) -> None:
        self.operations.append(("create_unique_constraint", (name, table, tuple(columns)), {}))

    def create_check_constraint(self, name: str, table: str, condition: str) -> None:
        self.operations.append(("create_check_constraint", (name, table, condition), {}))

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.operations.append(("drop_index", (name, table_name), {}))

    def drop_constraint(
        self,
        name: str,
        table: str,
        *,
        type_: str,
    ) -> None:
        self.operations.append(("drop_constraint", (name, table, type_), {}))

    def drop_column(self, table: str, column: str) -> None:
        self.operations.append(("drop_column", (table, column), {}))

    def drop_table(self, table: str) -> None:
        self.operations.append(("drop_table", (table,), {}))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_d8_callback_upgrade_adds_isolated_evidence_and_exactly_once_task_contracts() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0108_prospecting_callbacks"
    assert namespace["down_revision"] == "0107_prospecting_evidence"
    namespace["upgrade"]()

    create_table = next(item for item in recorder.operations if item[0] == "create_table")
    assert create_table[1][0] == "prospecting_inbound_callbacks"
    table_items = create_table[1][1:]
    columns = {item.name: item for item in table_items if isinstance(item, sa.Column)}
    assert {
        "organization_id",
        "voice_line_id",
        "provider_call_id",
        "normalized_caller",
        "matched_prospect_id",
        "matched_attempt_id",
        "assigned_user_id",
        "fallback_user_id",
        "routing_metadata",
    } <= columns.keys()
    assert columns["matched_prospect_id"].nullable is True
    assert columns["matched_attempt_id"].nullable is True
    constraint_names = {
        item.name for item in table_items if isinstance(item, sa.Constraint)
    }
    assert "uq_prospecting_inbound_callbacks_org_provider_call" in constraint_names
    assert "ck_prospecting_inbound_callbacks_match_context" in constraint_names

    added_columns = {
        (str(item[1][0]), str(item[1][1].name))
        for item in recorder.operations
        if item[0] == "add_column"
    }
    assert added_columns == {
        ("call_records", "prospecting_inbound_callback_id"),
        ("tasks", "prospecting_inbound_callback_id"),
        ("tasks", "prospect_id"),
        ("tasks", "call_record_id"),
    }
    callback_check = next(
        str(item[1][2])
        for item in recorder.operations
        if item[0] == "create_check_constraint" and item[1][0] == "ck_call_records_context"
    )
    assert "prospecting_inbound_callback_id IS NOT NULL" in callback_check
    assert "direction = 'inbound'" in callback_check

    missed_index = next(
        item
        for item in recorder.operations
        if item[0] == "create_index" and item[1][0] == "uq_tasks_prospecting_missed_callback"
    )
    assert missed_index[2]["unique"] is True
    assert str(missed_index[2]["postgresql_where"]) == str(
        missed_index[2]["sqlite_where"]
    )


def test_d8_callback_downgrade_refuses_to_discard_callback_evidence() -> None:
    recorder = MigrationRecorder(as_sql=False, has_evidence=True)
    namespace = migration_namespace(recorder)

    with pytest.raises(RuntimeError, match="callback evidence exists"):
        namespace["downgrade"]()

    assert not any(
        operation in {"drop_column", "drop_constraint", "drop_table"}
        for operation, _args, _kwargs in recorder.operations
    )
