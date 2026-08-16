from pathlib import Path
from runpy import run_path
from typing import Any

from app.models.foundation import AttributionTouch, ConversionEvent, LeadFormSubmission

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0101_meta_click_capture_time.py"


class MigrationRecorder:
    def __init__(self) -> None:
        self.added: list[tuple[str, Any]] = []
        self.dropped: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: Any) -> None:
        self.added.append((table_name, column))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped.append((table_name, column_name))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_meta_click_capture_models_are_nullable() -> None:
    for model in (LeadFormSubmission, AttributionTouch, ConversionEvent):
        column = model.__table__.c.fbclid_captured_at
        assert column.nullable is True
        assert column.server_default is None


def test_meta_click_capture_migration_adds_nullable_columns_without_backfill() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["down_revision"] == "0100_voice_lines_always_on"
    namespace["upgrade"]()

    assert [table for table, _ in recorder.added] == [
        "lead_form_submissions",
        "attribution_touches",
        "conversion_events",
    ]
    assert all(column.name == "fbclid_captured_at" for _, column in recorder.added)
    assert all(column.nullable is True for _, column in recorder.added)


def test_meta_click_capture_migration_downgrade_removes_only_new_columns() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped == [
        ("conversion_events", "fbclid_captured_at"),
        ("attribution_touches", "fbclid_captured_at"),
        ("lead_form_submissions", "fbclid_captured_at"),
    ]
