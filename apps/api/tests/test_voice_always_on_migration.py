from pathlib import Path
from runpy import run_path
from typing import Any

from app.models.foundation import VoiceLine

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0100_voice_lines_always_on.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.alterations: list[tuple[str, str, dict[str, Any]]] = []
        self.statements: list[str] = []

    def alter_column(self, table: str, column: str, **kwargs: Any) -> None:
        self.alterations.append((table, column, kwargs))

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_voice_line_model_defaults_to_always_on_coverage() -> None:
    start = VoiceLine.__table__.c.coverage_start_hour
    end = VoiceLine.__table__.c.coverage_end_hour

    assert start.server_default is not None
    assert end.server_default is not None
    assert str(start.server_default.arg) == "0"
    assert str(end.server_default.arg) == "24"


def test_voice_line_always_on_migration_backfills_active_lines_and_defaults() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["down_revision"] == "0099_sms_consent_recipient"
    namespace["upgrade"]()

    assert any("WHERE status = 'active'" in statement for statement in recorder.statements)
    assert any("coverage_start_hour = 0" in statement for statement in recorder.statements)
    assert any("coverage_end_hour = 24" in statement for statement in recorder.statements)
    assert all("missed_call_action" not in statement for statement in recorder.statements)
    defaults = {
        column: str(change["server_default"])
        for table, column, change in recorder.alterations
        if table == "voice_lines"
    }
    assert defaults == {"coverage_start_hour": "0", "coverage_end_hour": "24"}


def test_voice_line_always_on_migration_downgrade_restores_legacy_defaults() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    defaults = {
        column: str(change["server_default"])
        for table, column, change in recorder.alterations
        if table == "voice_lines"
    }
    assert defaults == {"coverage_end_hour": "20", "coverage_start_hour": "9"}
