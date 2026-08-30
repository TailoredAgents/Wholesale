from pathlib import Path
from runpy import run_path
from typing import Any, cast

import sqlalchemy as sa

from app.models.foundation import BuyerDiscoveryRun

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0121_dealmachine_discovery_governance.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table_name, column))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **_kwargs: object,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns)))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_ds11_migration_matches_discovery_governance_model() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0121_dealmachine_buyer_tiers"
    assert namespace["down_revision"] == "0120_disposition_copilot_eval"
    namespace["upgrade"]()

    added_columns = {
        str(column.name): column
        for table_name, column in recorder.added_columns
        if table_name == "buyer_discovery_runs"
    }
    assert set(added_columns) == {
        "search_tier",
        "request_fingerprint",
        "target_candidate_count",
        "estimated_credit_cap",
        "estimated_credits",
        "actual_credits",
    }
    assert set(added_columns) <= set(BuyerDiscoveryRun.__table__.columns.keys())
    for column_name, migration_column in added_columns.items():
        model_column = BuyerDiscoveryRun.__table__.columns[column_name]
        assert type(migration_column.type) is type(model_column.type)
        assert migration_column.nullable is model_column.nullable is True

    assert recorder.created_indexes == [
        (
            "ix_buyer_discovery_runs_org_case_tier_created",
            "buyer_discovery_runs",
            ("organization_id", "disposition_case_id", "search_tier", "created_at"),
        ),
        (
            "ix_buyer_discovery_runs_org_fingerprint_created",
            "buyer_discovery_runs",
            ("organization_id", "request_fingerprint", "created_at"),
        ),
    ]
    model_table = cast(sa.Table, BuyerDiscoveryRun.__table__)
    model_indexes = {
        str(index.name): tuple(column.name for column in index.columns)
        for index in model_table.indexes
    }
    for name, _table_name, columns in recorder.created_indexes:
        assert model_indexes[name] == columns


def test_ds11_migration_downgrade_removes_only_governance_schema() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_indexes == [
        (
            "ix_buyer_discovery_runs_org_fingerprint_created",
            "buyer_discovery_runs",
        ),
        (
            "ix_buyer_discovery_runs_org_case_tier_created",
            "buyer_discovery_runs",
        ),
    ]
    assert recorder.dropped_columns == [
        ("buyer_discovery_runs", "actual_credits"),
        ("buyer_discovery_runs", "estimated_credits"),
        ("buyer_discovery_runs", "estimated_credit_cap"),
        ("buyer_discovery_runs", "target_candidate_count"),
        ("buyer_discovery_runs", "request_fingerprint"),
        ("buyer_discovery_runs", "search_tier"),
    ]
