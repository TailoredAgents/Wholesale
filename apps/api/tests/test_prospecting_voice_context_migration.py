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
    / "0104_prospecting_voice_context.py"
)


class MigrationRecorder:
    def __init__(self, *, as_sql: bool = True) -> None:
        self.as_sql = as_sql
        self.operations: list[tuple[str, str]] = []
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.altered_columns: list[tuple[str, str, dict[str, Any]]] = []
        self.foreign_keys: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.indexes: list[tuple[str, str, tuple[str, ...], dict[str, Any]]] = []
        self.unique_constraints: list[tuple[str, str, tuple[str, ...]]] = []
        self.check_constraints: list[tuple[str, str, str]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []

    def get_context(self) -> SimpleNamespace:
        return SimpleNamespace(as_sql=self.as_sql)

    def alter_column(self, table: str, column: str, **kwargs: Any) -> None:
        self.operations.append(("alter_column", f"{table}.{column}"))
        self.altered_columns.append((table, column, kwargs))

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", f"{table}.{column.name}"))
        self.added_columns.append((table, column))

    def create_foreign_key(
        self,
        name: str,
        table: str,
        target: str,
        local_columns: list[str],
        _remote_columns: list[str],
        **_kwargs: Any,
    ) -> None:
        self.operations.append(("create_foreign_key", f"{table}.{name}"))
        self.foreign_keys.append((name, table, target, tuple(local_columns)))

    def create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        **kwargs: Any,
    ) -> None:
        self.operations.append(("create_index", f"{table}.{name}"))
        self.indexes.append((name, table, tuple(columns), kwargs))

    def create_unique_constraint(
        self,
        name: str,
        table: str,
        columns: list[str],
    ) -> None:
        self.operations.append(("create_unique", f"{table}.{name}"))
        self.unique_constraints.append((name, table, tuple(columns)))

    def create_check_constraint(self, name: str, table: str, condition: str) -> None:
        self.operations.append(("create_check", f"{table}.{name}"))
        self.check_constraints.append((name, table, condition))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.operations.append(("drop_index", f"{table_name}.{name}"))

    def drop_constraint(
        self,
        name: str,
        table: str,
        *,
        type_: str | None = None,
    ) -> None:
        self.operations.append(("drop_constraint", f"{table}.{name}"))
        self.dropped_constraints.append((name, table, type_))

    def drop_column(self, table: str, column: str) -> None:
        self.operations.append(("drop_column", f"{table}.{column}"))
        self.dropped_columns.append((table, column))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_prospecting_voice_context_upgrade_is_additive_and_strict() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0104_prospecting_voice_context"
    assert namespace["down_revision"] == "0103_native_prospecting_dialer"

    namespace["upgrade"]()

    expected_columns = {
        (table, column)
        for table in ("voice_call_intents", "call_records")
        for column in (
            "prospect_id",
            "prospecting_attempt_id",
            "prospecting_dial_leg_id",
        )
    }
    assert {(table, str(column.name)) for table, column in recorder.added_columns} == (
        expected_columns
    )
    assert all(column.nullable is True for _table, column in recorder.added_columns)

    nullable_changes = {
        (table, column, options["nullable"])
        for table, column, options in recorder.altered_columns
    }
    assert nullable_changes == {
        (table, column, True)
        for table in ("voice_call_intents", "call_records")
        for column in ("conversation_id", "contact_id")
    }

    assert {
        (name, table, target, columns)
        for name, table, target, columns in recorder.foreign_keys
    } == {
        (f"fk_{prefix}_prospect_id", table, "prospects", ("prospect_id",))
        for table, prefix in (
            ("voice_call_intents", "voice_call_intents"),
            ("call_records", "call_records"),
        )
    } | {
        (
            f"fk_{prefix}_prospecting_attempt_id",
            table,
            "prospecting_attempts",
            ("prospecting_attempt_id",),
        )
        for table, prefix in (
            ("voice_call_intents", "voice_call_intents"),
            ("call_records", "call_records"),
        )
    } | {
        (
            f"fk_{prefix}_prospecting_dial_leg_id",
            table,
            "prospecting_dial_legs",
            ("prospecting_dial_leg_id",),
        )
        for table, prefix in (
            ("voice_call_intents", "voice_call_intents"),
            ("call_records", "call_records"),
        )
    }

    checks = {name: condition for name, _table, condition in recorder.check_constraints}
    assert checks.keys() == {"ck_voice_call_intents_context", "ck_call_records_context"}
    for condition in checks.values():
        assert "prospect_id IS NOT NULL" in condition
        assert "prospecting_attempt_id IS NOT NULL" in condition
        assert "prospecting_dial_leg_id IS NOT NULL" in condition
        assert "conversation_id IS NULL" in condition
        assert "contact_id IS NULL" in condition
    assert "communication_record_id IS NULL" in checks["ck_call_records_context"]

    assert set(recorder.unique_constraints) == {
        (
            "uq_voice_call_intents_prospecting_dial_leg",
            "voice_call_intents",
            ("prospecting_dial_leg_id",),
        ),
        (
            "uq_call_records_prospecting_dial_leg",
            "call_records",
            ("prospecting_dial_leg_id",),
        ),
        (
            "uq_prospecting_dial_legs_call_record",
            "prospecting_dial_legs",
            ("call_record_id",),
        ),
    }

    indexes = {
        name: (table, columns, options)
        for name, table, columns, options in recorder.indexes
    }
    sequence_index = indexes["ix_prospecting_provider_events_leg_sequence"]
    assert sequence_index[0] == "prospecting_provider_events"
    assert sequence_index[1] == (
        "organization_id",
        "provider",
        "dial_leg_id",
        "provider_sequence_number",
    )
    assert "unique" not in sequence_index[2]
    assert str(sequence_index[2]["postgresql_where"]) == str(
        sequence_index[2]["sqlite_where"]
    )


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class _GuardRecorder(MigrationRecorder):
    def __init__(self, values: list[bool]) -> None:
        super().__init__(as_sql=False)
        self.values = iter(values)

    def get_bind(self) -> "_GuardRecorder":
        return self

    def execute(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(next(self.values))


def test_downgrade_guard_refuses_to_discard_cold_call_evidence() -> None:
    recorder = _GuardRecorder([False, True])
    namespace = migration_namespace(recorder)

    with pytest.raises(RuntimeError, match="cold-call evidence exists"):
        namespace["downgrade"]()

    assert recorder.dropped_columns == []
    assert recorder.dropped_constraints == []


def test_clean_downgrade_restores_required_warm_context_columns() -> None:
    recorder = _GuardRecorder([False, False])
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert set(recorder.dropped_columns) == {
        (table, column)
        for table in ("voice_call_intents", "call_records")
        for column in (
            "prospect_id",
            "prospecting_attempt_id",
            "prospecting_dial_leg_id",
        )
    }
    restored = {
        (table, column, options["nullable"])
        for table, column, options in recorder.altered_columns
    }
    assert restored == {
        (table, column, False)
        for table in ("voice_call_intents", "call_records")
        for column in ("conversation_id", "contact_id")
    }
