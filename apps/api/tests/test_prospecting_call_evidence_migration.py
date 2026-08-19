from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any

import sqlalchemy as sa

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0107_prospecting_call_evidence.py"


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def fetchall(self) -> list[object]:
        return self.rows


class MigrationRecorder:
    def __init__(self, *, with_duplicate: bool = True) -> None:
        self.with_duplicate = with_duplicate
        self.operations: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_bind(self) -> MigrationRecorder:
        self.operations.append(("get_bind", (), {}))
        return self

    def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        self.operations.append(("sql", (sql,), parameters or {}))
        if sql.startswith("SELECT recording_id FROM call_transcripts"):
            return _Result([("recording-d7",)] if self.with_duplicate else [])
        if sql.startswith("SELECT id, status, created_at FROM call_transcripts"):
            now = datetime.now(UTC)
            return _Result(
                [
                    SimpleNamespace(
                        id="newer-queued",
                        status="queued",
                        created_at=now,
                    ),
                    SimpleNamespace(
                        id="older-approved",
                        status="approved",
                        created_at=now - timedelta(days=1),
                    ),
                ]
            )
        return _Result([])

    def create_unique_constraint(
        self,
        name: str,
        table: str,
        columns: list[str],
    ) -> None:
        self.operations.append(("create_unique_constraint", (name, table, columns), {}))

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
                (name, table, target, local_columns, remote_columns),
                kwargs,
            )
        )

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.operations.append(("create_index", (name, table, columns), {}))

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.operations.append(("drop_index", (name,), {"table_name": table_name}))

    def drop_constraint(
        self,
        name: str,
        table: str,
        *,
        type_: str,
    ) -> None:
        self.operations.append(("drop_constraint", (name, table), {"type_": type_}))

    def drop_column(self, table: str, column: str) -> None:
        self.operations.append(("drop_column", (table, column), {}))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_d7_call_evidence_upgrade_deduplicates_before_adding_contract() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0107_prospecting_evidence"
    assert namespace["down_revision"] == "0106_prospecting_dispositions"
    namespace["upgrade"]()

    names = [name for name, _args, _kwargs in recorder.operations]
    unique_index = names.index("create_unique_constraint")
    delete_index = next(
        index
        for index, (name, args, _kwargs) in enumerate(recorder.operations)
        if name == "sql" and str(args[0]).startswith("DELETE FROM call_transcripts")
    )
    assert delete_index < unique_index
    delete_operation = recorder.operations[delete_index]
    assert delete_operation[2] == {"duplicate": "newer-queued"}
    redirect_operations = [
        item
        for item in recorder.operations[:delete_index]
        if item[0] == "sql" and str(item[1][0]).startswith("UPDATE ")
    ]
    assert [str(item[1][0]).split(" SET ", 1)[0] for item in redirect_operations] == [
        "UPDATE prospecting_call_quality_reviews",
        "UPDATE approval_requests",
        "UPDATE activity_events",
        "UPDATE audit_events",
    ]
    assert all(
        item[2] == {"keeper": "older-approved", "duplicate": "newer-queued"}
        for item in redirect_operations
    )
    for table_name in ("approval_requests", "activity_events", "audit_events"):
        statement = next(
            str(item[1][0])
            for item in redirect_operations
            if str(item[1][0]).startswith(f"UPDATE {table_name}")
        )
        assert "entity_type = 'call_transcript'" in statement
    assert recorder.operations[unique_index][1] == (
        "uq_call_transcripts_recording",
        "call_transcripts",
        ["recording_id"],
    )

    add_operation = next(item for item in recorder.operations if item[0] == "add_column")
    table, column = add_operation[1]
    assert table == "communication_records"
    assert isinstance(column, sa.Column)
    assert column.name == "source_call_record_id"
    assert isinstance(column.type, sa.Uuid)
    assert column.nullable is True

    foreign_key = next(item for item in recorder.operations if item[0] == "create_foreign_key")
    assert foreign_key[1] == (
        "fk_communication_records_source_call_record_id",
        "communication_records",
        "call_records",
        ["source_call_record_id"],
        ["id"],
    )
    assert foreign_key[2] == {"ondelete": "SET NULL"}
    index = next(item for item in recorder.operations if item[0] == "create_index")
    assert index[1] == (
        "ix_communication_records_source_call_record_id",
        "communication_records",
        ["source_call_record_id"],
    )


def test_d7_call_evidence_downgrade_removes_only_d7_objects() -> None:
    recorder = MigrationRecorder(with_duplicate=False)
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.operations == [
        (
            "drop_index",
            ("ix_communication_records_source_call_record_id",),
            {"table_name": "communication_records"},
        ),
        (
            "drop_constraint",
            (
                "fk_communication_records_source_call_record_id",
                "communication_records",
            ),
            {"type_": "foreignkey"},
        ),
        (
            "drop_column",
            ("communication_records", "source_call_record_id"),
            {},
        ),
        (
            "drop_constraint",
            ("uq_call_transcripts_recording", "call_transcripts"),
            {"type_": "unique"},
        ),
    ]
