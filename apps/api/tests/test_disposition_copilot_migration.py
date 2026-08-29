from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import AiRunLog, DispositionCopilotReview

MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "0120_disposition_copilot_evaluation.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.operations: list[tuple[str, str, str, object]] = []

    def alter_column(self, table_name: str, column_name: str, **kwargs: object) -> None:
        self.operations.append(("alter_column", table_name, column_name, kwargs))

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", table_name, str(column.name), column))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.operations.append(("drop_column", table_name, column_name, {}))

    @staticmethod
    def get_bind() -> object:
        class Dialect:
            name = "postgresql"

        class Bind:
            dialect = Dialect()

        return Bind()

    def execute(self, statement: object) -> None:
        self.operations.append(("execute", "ai_run_logs", "output_summary", statement))


def _namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_ds9_migration_matches_copilot_review_and_ai_trace_models() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    assert namespace["revision"] == "0120_disposition_copilot_eval"
    assert namespace["down_revision"] == "0119_disposition_provider"

    namespace["upgrade"]()
    assert [item[:3] for item in recorder.operations] == [
        ("alter_column", "ai_run_logs", "output_summary"),
        ("add_column", "disposition_copilot_reviews", "quality_evaluation"),
    ]
    alter_kwargs = recorder.operations[0][3]
    assert isinstance(alter_kwargs, dict)
    assert isinstance(alter_kwargs["existing_type"], sa.String)
    assert alter_kwargs["existing_type"].length == 4000
    assert isinstance(alter_kwargs["type_"], sa.Text)
    assert alter_kwargs["existing_nullable"] is True
    assert isinstance(AiRunLog.__table__.columns["output_summary"].type, sa.Text)

    migration_column = recorder.operations[1][3]
    assert isinstance(migration_column, sa.Column)
    model_column = DispositionCopilotReview.__table__.columns["quality_evaluation"]
    assert isinstance(migration_column.type, sa.JSON)
    assert type(migration_column.type) is type(model_column.type)
    assert migration_column.nullable is False
    assert model_column.nullable is False
    assert migration_column.server_default is not None
    assert "{}" in str(migration_column.server_default.arg)


def test_ds9_downgrade_restores_output_limit_after_removing_evaluations() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    namespace["downgrade"]()

    assert [item[:3] for item in recorder.operations] == [
        ("drop_column", "disposition_copilot_reviews", "quality_evaluation"),
        ("execute", "ai_run_logs", "output_summary"),
        ("alter_column", "ai_run_logs", "output_summary"),
    ]
    assert "SUBSTRING(output_summary FROM 1 FOR 4000)" in str(recorder.operations[1][3])
    alter_kwargs = recorder.operations[2][3]
    assert isinstance(alter_kwargs, dict)
    assert isinstance(alter_kwargs["existing_type"], sa.Text)
    assert isinstance(alter_kwargs["type_"], sa.String)
    assert alter_kwargs["type_"].length == 4000
    assert alter_kwargs["existing_nullable"] is True
