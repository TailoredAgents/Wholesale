from pathlib import Path
from runpy import run_path
from typing import Any

from app.models.foundation import LeadFormSubmission

MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "0102_address_only_website_leads.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added: list[tuple[str, Any]] = []
        self.executed: list[Any] = []
        self.indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.unique_constraints: list[tuple[str, str, tuple[str, ...]]] = []
        self.check_constraints: list[tuple[str, str, str]] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: Any) -> None:
        self.added.append((table_name, column))

    def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    def create_index(self, name: str, table_name: str, columns: list[str]) -> None:
        self.indexes.append((name, table_name, tuple(columns)))

    def create_unique_constraint(self, name: str, table_name: str, columns: list[str]) -> None:
        self.unique_constraints.append((name, table_name, tuple(columns)))

    def create_check_constraint(self, name: str, table_name: str, condition: str) -> None:
        self.check_constraints.append((name, table_name, condition))

    def drop_constraint(self, name: str, table_name: str, *, type_: str | None = None) -> None:
        self.dropped_constraints.append((name, table_name, type_))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_address_only_submission_model_has_idempotency_and_state_constraints() -> None:
    table = LeadFormSubmission.__table__
    assert table.c.intake_attempt_id.nullable is True
    assert table.c.completion_status.nullable is False
    assert table.c.completed_at.nullable is True
    constraint_names = {constraint.name for constraint in table.constraints}
    assert "uq_lead_form_submissions_org_intake_attempt" in constraint_names
    assert "ck_lead_form_submissions_completion_state" in constraint_names
    state_constraint = next(
        constraint
        for constraint in table.constraints
        if constraint.name == "ck_lead_form_submissions_completion_state"
    )
    condition = str(state_constraint.sqltext)
    assert "completion_status = 'completed'" in condition
    assert "completed_at IS NOT NULL" not in condition
    assert "address_only" in condition and "completed_at IS NULL" in condition


def test_address_only_lead_migration_backfills_before_constraints() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["down_revision"] == "0101_meta_click_capture_time"
    namespace["upgrade"]()

    assert [column.name for _, column in recorder.added] == [
        "intake_attempt_id",
        "completion_status",
        "completed_at",
    ]
    assert len(recorder.executed) == 1
    assert "SET completed_at = created_at" in str(recorder.executed[0])
    assert recorder.unique_constraints == [
        (
            "uq_lead_form_submissions_org_intake_attempt",
            "lead_form_submissions",
            ("organization_id", "intake_attempt_id"),
        )
    ]
    assert recorder.check_constraints[0][0] == "ck_lead_form_submissions_completion_state"
    migration_condition = recorder.check_constraints[0][2]
    assert "address_only" in migration_condition
    assert "completion_status = 'completed'" in migration_condition
    assert "completed_at IS NOT NULL" not in migration_condition


def test_address_only_lead_migration_downgrade_is_scoped() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_columns == [
        ("lead_form_submissions", "completed_at"),
        ("lead_form_submissions", "completion_status"),
        ("lead_form_submissions", "intake_attempt_id"),
    ]
