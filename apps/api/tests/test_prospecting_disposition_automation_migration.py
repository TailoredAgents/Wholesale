from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0106_prospecting_disposition_automation.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.operations: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: object, **kwargs: object) -> None:
            self.operations.append((name, args, kwargs))

        return record


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_d6_appointment_source_identity_upgrade() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0106_prospecting_dispositions"
    assert namespace["down_revision"] == "0105_dial_session_coordinator"
    namespace["upgrade"]()

    assert [operation[0] for operation in recorder.operations] == [
        "add_column",
        "create_foreign_key",
        "create_index",
        "create_unique_constraint",
    ]
    table, column = recorder.operations[0][1]
    assert table == "appointments"
    assert isinstance(column, sa.Column)
    assert column.name == "prospecting_attempt_id"
    assert isinstance(column.type, sa.Uuid)
    assert column.nullable is True
    assert recorder.operations[1][1] == (
        "fk_appointments_prospecting_attempt",
        "appointments",
        "prospecting_attempts",
        ["prospecting_attempt_id"],
        ["id"],
    )
    assert recorder.operations[2][1] == (
        "ix_appointments_prospecting_attempt_id",
        "appointments",
        ["prospecting_attempt_id"],
    )
    assert recorder.operations[3][1] == (
        "uq_appointments_org_prospecting_attempt",
        "appointments",
        ["organization_id", "prospecting_attempt_id"],
    )


def test_d6_appointment_source_identity_downgrade_is_dependency_safe() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    namespace["downgrade"]()

    assert [operation[0] for operation in recorder.operations] == [
        "drop_constraint",
        "drop_index",
        "drop_constraint",
        "drop_column",
    ]
    assert recorder.operations[0][1] == (
        "uq_appointments_org_prospecting_attempt",
        "appointments",
    )
    assert recorder.operations[0][2] == {"type_": "unique"}
    assert recorder.operations[2][1] == (
        "fk_appointments_prospecting_attempt",
        "appointments",
    )
    assert recorder.operations[2][2] == {"type_": "foreignkey"}
    assert recorder.operations[-1][1] == ("appointments", "prospecting_attempt_id")
