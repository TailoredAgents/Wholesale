from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0103_native_prospecting_dialer.py"

NATIVE_DIALER_TABLES = {
    "prospecting_dialer_profiles",
    "prospecting_dial_sessions",
    "prospecting_dial_legs",
    "prospecting_qualification_responses",
}


class MigrationRecorder:
    def __init__(self) -> None:
        self.operations: list[tuple[str, str]] = []
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.created_checks: list[tuple[str, str, str]] = []
        self.created_tables: list[str] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], dict[str, Any]]] = []
        self.created_foreign_keys: list[tuple[str, str, str]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", f"{table_name}.{column.name}"))
        self.added_columns.append((table_name, column))

    def create_check_constraint(
        self,
        name: str,
        table_name: str,
        condition: str,
    ) -> None:
        self.operations.append(("create_check", f"{table_name}.{name}"))
        self.created_checks.append((name, table_name, condition))

    def create_table(self, name: str, *elements: Any, **_kwargs: Any) -> None:
        self.operations.append(("create_table", name))
        self.created_tables.append(name)
        for element in elements:
            if isinstance(element, sa.CheckConstraint):
                assert element.name is not None
                self.created_checks.append((str(element.name), name, str(element.sqltext)))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **kwargs: Any,
    ) -> None:
        self.operations.append(("create_index", f"{table_name}.{name}"))
        self.created_indexes.append((name, table_name, tuple(columns), kwargs))

    def create_foreign_key(
        self,
        name: str,
        source_table: str,
        referent_table: str,
        _local_cols: list[str],
        _remote_cols: list[str],
        **_kwargs: Any,
    ) -> None:
        self.operations.append(("create_foreign_key", f"{source_table}.{name}"))
        self.created_foreign_keys.append((name, source_table, referent_table))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.operations.append(("drop_index", f"{table_name}.{name}"))
        self.dropped_indexes.append((name, table_name))

    def drop_constraint(
        self,
        name: str,
        table_name: str,
        *,
        type_: str | None = None,
    ) -> None:
        self.operations.append(("drop_constraint", f"{table_name}.{name}"))
        self.dropped_constraints.append((name, table_name, type_))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.operations.append(("drop_column", f"{table_name}.{column_name}"))
        self.dropped_columns.append((table_name, column_name))

    def drop_table(self, table_name: str) -> None:
        self.operations.append(("drop_table", table_name))
        self.dropped_tables.append(table_name)


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def operation_position(
    recorder: MigrationRecorder,
    operation: str,
    target: str,
) -> int:
    return recorder.operations.index((operation, target))


def test_native_dialer_migration_revision_and_safe_capacity_columns() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0103_native_prospecting_dialer"
    assert namespace["down_revision"] == "0102_address_only_website_leads"

    namespace["upgrade"]()

    capacity_tables = {"organizations", "campaigns", "voice_lines"}
    capacity_columns = {
        table_name: column
        for table_name, column in recorder.added_columns
        if column.name == "prospecting_dialer_max_concurrent_legs"
    }
    assert capacity_columns.keys() == capacity_tables
    for table_name, column in capacity_columns.items():
        assert isinstance(column.type, sa.Integer)
        assert column.nullable is False
        assert isinstance(column.server_default, sa.DefaultClause)
        assert str(column.server_default.arg) == "1"
        assert operation_position(
            recorder,
            "add_column",
            f"{table_name}.prospecting_dialer_max_concurrent_legs",
        ) < operation_position(
            recorder,
            "create_check",
            f"{table_name}.ck_{table_name}_prospecting_dialer_leg_limit",
        )


def test_native_dialer_upgrade_creates_foundation_and_extends_provider_events() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["upgrade"]()

    assert len(recorder.created_tables) == len(NATIVE_DIALER_TABLES)
    assert set(recorder.created_tables) == NATIVE_DIALER_TABLES

    partial_indexes = {
        name: (table_name, columns, kwargs)
        for name, table_name, columns, kwargs in recorder.created_indexes
        if name.startswith("uq_prospecting_dial_")
        and ("postgresql_where" in kwargs or "sqlite_where" in kwargs)
    }
    assert partial_indexes.keys() == {
        "uq_prospecting_dial_sessions_active_user",
        "uq_prospecting_dial_legs_active_prospect",
        "uq_prospecting_dial_legs_active_entry",
        "uq_prospecting_dial_legs_active_slot",
        "uq_prospecting_dial_legs_connected_session",
    }
    for _table_name, _columns, options in partial_indexes.values():
        assert options["unique"] is True
        assert str(options["postgresql_where"]) == str(options["sqlite_where"])

    predicates = {
        name: str(options["postgresql_where"])
        for name, (_table_name, _columns, options) in partial_indexes.items()
    }
    assert predicates["uq_prospecting_dial_sessions_active_user"] == "ended_at IS NULL"
    assert predicates["uq_prospecting_dial_legs_active_prospect"] == ("completed_at IS NULL")
    assert predicates["uq_prospecting_dial_legs_connected_session"] == (
        "connected_at IS NOT NULL AND completed_at IS NULL"
    )
    assert (
        "ck_prospecting_dial_legs_connected_timestamp",
        "prospecting_dial_legs",
        "status <> 'connected' OR connected_at IS NOT NULL",
    ) in recorder.created_checks

    provider_event_columns = {
        column.name
        for table_name, column in recorder.added_columns
        if table_name == "prospecting_provider_events"
    }
    assert {
        "dial_session_id",
        "dial_leg_id",
        "provider_sequence_number",
        "occurred_at",
        "signature_verified",
        "signature_fingerprint",
        "payload_sha256",
    } <= provider_event_columns
    assert "prospecting_provider_events" not in recorder.created_tables
    assert not any("event" in name for name in recorder.created_tables)
    assert {(source, target) for _name, source, target in recorder.created_foreign_keys} >= {
        ("prospecting_provider_events", "prospecting_dial_sessions"),
        ("prospecting_provider_events", "prospecting_dial_legs"),
    }


def test_native_dialer_downgrade_removes_only_its_additions_in_dependency_order() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert set(recorder.dropped_tables) == NATIVE_DIALER_TABLES
    assert recorder.dropped_tables == [
        "prospecting_qualification_responses",
        "prospecting_dial_legs",
        "prospecting_dial_sessions",
        "prospecting_dialer_profiles",
    ]

    provider_column_drops = [
        column_name
        for table_name, column_name in recorder.dropped_columns
        if table_name == "prospecting_provider_events"
    ]
    assert set(provider_column_drops) == {
        "payload_sha256",
        "signature_fingerprint",
        "signature_verified",
        "occurred_at",
        "provider_sequence_number",
        "dial_leg_id",
        "dial_session_id",
    }
    first_table_drop = min(
        operation_position(recorder, "drop_table", table_name)
        for table_name in NATIVE_DIALER_TABLES
    )
    assert all(
        operation_position(
            recorder,
            "drop_column",
            f"prospecting_provider_events.{column_name}",
        )
        < first_table_drop
        for column_name in provider_column_drops
    )

    capacity_drops = [
        (table_name, column_name)
        for table_name, column_name in recorder.dropped_columns
        if table_name != "prospecting_provider_events"
    ]
    assert capacity_drops == [
        ("voice_lines", "prospecting_dialer_max_concurrent_legs"),
        ("campaigns", "prospecting_dialer_max_concurrent_legs"),
        ("organizations", "prospecting_dialer_max_concurrent_legs"),
    ]
    last_table_drop = max(
        operation_position(recorder, "drop_table", table_name)
        for table_name in NATIVE_DIALER_TABLES
    )
    assert all(
        operation_position(
            recorder,
            "drop_column",
            f"{table_name}.prospecting_dialer_max_concurrent_legs",
        )
        > last_table_drop
        for table_name, _column_name in capacity_drops
    )
