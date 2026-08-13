from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import StaffLeadAlert, User

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0098_inbound_message_alerts.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.alterations: list[tuple[str, str, dict[str, Any]]] = []
        self.indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.statements: list[str] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table, column))

    def alter_column(self, table: str, column: str, **kwargs: Any) -> None:
        self.alterations.append((table, column, kwargs))

    def create_index(self, name: str, table: str, columns: list[str]) -> None:
        self.indexes.append((name, table, tuple(columns)))

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_column(self, table: str, column: str) -> None:
        self.dropped_columns.append((table, column))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_inbound_message_alert_model_supports_conversation_alerts() -> None:
    preference = User.__table__.c.inbound_message_alert_sms_enabled
    lead_id = StaffLeadAlert.__table__.c.lead_id
    conversation_id = StaffLeadAlert.__table__.c.conversation_id

    assert preference.nullable is False
    assert preference.server_default is not None
    assert lead_id.nullable is True
    assert conversation_id.nullable is True
    assert conversation_id.index is True
    foreign_key = next(iter(conversation_id.foreign_keys))
    assert foreign_key.target_fullname == "conversations.id"
    assert foreign_key.ondelete == "SET NULL"


def test_inbound_message_alert_migration_backfills_existing_opt_ins() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["down_revision"] == "0097_general_staff_lead_alerts"
    namespace["upgrade"]()

    assert [(table, column.name) for table, column in recorder.added_columns] == [
        ("users", "inbound_message_alert_sms_enabled"),
        ("staff_lead_alerts", "conversation_id"),
    ]
    preference = recorder.added_columns[0][1]
    conversation_id = recorder.added_columns[1][1]
    assert preference.nullable is False
    assert preference.server_default is not None
    assert conversation_id.nullable is True
    assert any(
        "inbound_message_alert_sms_enabled = lead_alert_sms_enabled" in statement
        for statement in recorder.statements
    )
    assert recorder.alterations[0][0:2] == ("staff_lead_alerts", "lead_id")
    assert isinstance(recorder.alterations[0][2]["existing_type"], sa.Uuid)
    assert recorder.alterations[0][2]["nullable"] is True
    assert recorder.indexes == [
        (
            "ix_staff_lead_alerts_conversation_id",
            "staff_lead_alerts",
            ("conversation_id",),
        )
    ]


def test_inbound_message_alert_migration_downgrade_restores_lead_requirement() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_indexes == [
        ("ix_staff_lead_alerts_conversation_id", "staff_lead_alerts")
    ]
    assert recorder.dropped_columns == [
        ("staff_lead_alerts", "conversation_id"),
        ("users", "inbound_message_alert_sms_enabled"),
    ]
    assert any(
        "DELETE FROM staff_lead_alerts WHERE lead_id IS NULL" in item
        for item in recorder.statements
    )
    assert recorder.alterations[0][0:2] == ("staff_lead_alerts", "lead_id")
    assert recorder.alterations[0][2]["nullable"] is False
