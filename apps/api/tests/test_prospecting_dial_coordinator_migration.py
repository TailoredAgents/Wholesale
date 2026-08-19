from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0105_prospecting_dial_coordinator.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.operations: list[tuple[str, str]] = []
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.checks: list[tuple[str, str, str]] = []
        self.indexes: list[tuple[str, str, tuple[str, ...], dict[str, Any]]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", f"{table}.{column.name}"))
        self.added_columns.append((table, column))

    def create_check_constraint(self, name: str, table: str, condition: str) -> None:
        self.operations.append(("create_check", f"{table}.{name}"))
        self.checks.append((name, table, condition))

    def create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        **kwargs: Any,
    ) -> None:
        self.operations.append(("create_index", f"{table}.{name}"))
        self.indexes.append((name, table, tuple(columns), kwargs))

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

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.operations.append(("drop_index", f"{table_name}.{name}"))
        self.dropped_indexes.append((name, table_name))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def operation_position(recorder: MigrationRecorder, operation: str, target: str) -> int:
    return recorder.operations.index((operation, target))


def test_d3_coordinator_upgrade_is_fail_closed_and_matches_queue_query() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0105_dial_session_coordinator"
    assert namespace["down_revision"] == "0104_prospecting_voice_context"

    namespace["upgrade"]()

    columns = {(table, str(column.name)): column for table, column in recorder.added_columns}
    assert columns.keys() == {
        ("organizations", "prospecting_dialer_enabled"),
        ("campaigns", "prospecting_dialer_enabled"),
        ("prospecting_dial_legs", "reserved_cost_cents"),
        ("prospecting_dial_legs", "actual_cost_cents"),
    }
    for table in ("organizations", "campaigns"):
        switch = columns[(table, "prospecting_dialer_enabled")]
        assert isinstance(switch.type, sa.Boolean)
        assert switch.nullable is False
        assert isinstance(switch.server_default, sa.DefaultClause)
        assert str(switch.server_default.arg) == "false"

    reserved_cost = columns[("prospecting_dial_legs", "reserved_cost_cents")]
    actual_cost = columns[("prospecting_dial_legs", "actual_cost_cents")]
    assert isinstance(reserved_cost.type, sa.BigInteger)
    assert reserved_cost.nullable is False
    assert isinstance(reserved_cost.server_default, sa.DefaultClause)
    assert str(reserved_cost.server_default.arg) == "0"
    assert isinstance(actual_cost.type, sa.BigInteger)
    assert actual_cost.nullable is True

    assert set(recorder.checks) == {
        (
            "ck_prospecting_dial_sessions_current_work",
            "prospecting_dial_sessions",
            namespace["CURRENT_WORK_CHECK"],
        ),
        (
            "ck_prospecting_dial_sessions_lease_lifecycle",
            "prospecting_dial_sessions",
            namespace["LEASE_LIFECYCLE_CHECK"],
        ),
        (
            "ck_prospecting_dial_legs_reserved_cost",
            "prospecting_dial_legs",
            "reserved_cost_cents >= 0",
        ),
        (
            "ck_prospecting_dial_legs_actual_cost",
            "prospecting_dial_legs",
            "actual_cost_cents IS NULL OR actual_cost_cents >= 0",
        ),
    }
    assert recorder.indexes == [
        (
            "ix_prospect_calling_batch_entries_dial_candidate",
            "prospect_calling_batch_entries",
            (
                "organization_id",
                "assigned_user_id",
                "prospect_calling_batch_id",
                "status",
                "next_attempt_at",
                "sequence_number",
            ),
            {},
        )
    ]


def test_d3_coordinator_downgrade_is_symmetric_and_dependency_safe() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert set(recorder.dropped_constraints) == {
        ("ck_prospecting_dial_legs_actual_cost", "prospecting_dial_legs", "check"),
        ("ck_prospecting_dial_legs_reserved_cost", "prospecting_dial_legs", "check"),
        (
            "ck_prospecting_dial_sessions_lease_lifecycle",
            "prospecting_dial_sessions",
            "check",
        ),
        (
            "ck_prospecting_dial_sessions_current_work",
            "prospecting_dial_sessions",
            "check",
        ),
    }
    assert set(recorder.dropped_columns) == {
        ("prospecting_dial_legs", "actual_cost_cents"),
        ("prospecting_dial_legs", "reserved_cost_cents"),
        ("campaigns", "prospecting_dialer_enabled"),
        ("organizations", "prospecting_dialer_enabled"),
    }
    assert recorder.dropped_indexes == [
        (
            "ix_prospect_calling_batch_entries_dial_candidate",
            "prospect_calling_batch_entries",
        )
    ]
    for check_name in (
        "ck_prospecting_dial_legs_actual_cost",
        "ck_prospecting_dial_legs_reserved_cost",
    ):
        assert operation_position(
            recorder,
            "drop_constraint",
            f"prospecting_dial_legs.{check_name}",
        ) < operation_position(
            recorder,
            "drop_column",
            "prospecting_dial_legs.reserved_cost_cents",
        )
