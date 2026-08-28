from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import (
    Buyer,
    BuyerBuyBox,
    BuyerBuyBoxVersion,
    BuyerEngagement,
    BuyerProofDocument,
    DispositionMatch,
)

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0114_buyer_profiles_buy_boxes.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], dict[str, object]]] = []
        self.altered_columns: list[tuple[str, str, dict[str, object]]] = []
        self.executed_statements: list[str] = []
        self.dropped_tables: list[str] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table_name, column))

    def create_table(self, table_name: str, *items: object) -> None:
        self.created_tables.append((table_name, items))

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
        **kwargs: object,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns), kwargs))

    def create_foreign_key(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def alter_column(self, table_name: str, column_name: str, **kwargs: object) -> None:
        self.altered_columns.append((table_name, column_name, kwargs))

    def execute(self, statement: object) -> None:
        self.executed_statements.append(str(statement))

    def drop_index(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def drop_constraint(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))

    def drop_table(self, table_name: str) -> None:
        self.dropped_tables.append(table_name)


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_buyer_profiles_migration_matches_canonical_models() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    assert namespace["revision"] == "0114_buyer_profiles_buy_boxes"
    assert namespace["down_revision"] == "0113_buyer_network_foundation"
    namespace["upgrade"]()

    buyer_columns = {
        str(column.name)
        for table, column in recorder.added_columns
        if table == "buyers"
    }
    assert buyer_columns == {
        "tier",
        "temperature",
        "tags",
        "relationship_status",
        "next_follow_up_at",
        "verification_status",
        "verified_by_user_id",
        "verified_at",
    }
    assert buyer_columns <= set(Buyer.__table__.columns.keys())

    proof_columns = {
        str(column.name)
        for table, column in recorder.added_columns
        if table == "buyer_proof_documents"
    }
    assert proof_columns == {"verified_by_user_id", "verified_at", "verification_source"}
    assert proof_columns <= set(BuyerProofDocument.__table__.columns.keys())

    engagement_columns = {
        str(column.name)
        for table, column in recorder.added_columns
        if table == "buyer_engagements"
    }
    assert engagement_columns == {"completed_at"}
    assert engagement_columns <= set(BuyerEngagement.__table__.columns.keys())
    assert (
        "buyer_engagements",
        "disposition_case_id",
        {"nullable": True},
    ) in recorder.altered_columns

    match_columns = {
        str(column.name)
        for table, column in recorder.added_columns
        if table == "disposition_matches"
    }
    assert match_columns == {"buy_box_version_id", "matcher_version", "criteria_snapshot"}
    assert match_columns <= set(DispositionMatch.__table__.columns.keys())

    created_tables = dict(recorder.created_tables)
    assert set(created_tables) == {"buyer_buy_boxes", "buyer_buy_box_versions"}
    buy_box_columns = {
        str(item.name)
        for item in created_tables["buyer_buy_boxes"]
        if hasattr(item, "name")
    }
    assert buy_box_columns >= {
        *BuyerBuyBox.__table__.columns.keys(),
        "uq_buyer_buy_boxes_org_buyer_asset",
        "ck_buyer_buy_boxes_asset_class",
    }
    assert {
        str(item.name)
        for item in created_tables["buyer_buy_box_versions"]
        if hasattr(item, "name")
    } >= {
        *BuyerBuyBoxVersion.__table__.columns.keys(),
        "uq_buyer_buy_box_versions_number",
    }
    current_index = next(
        item
        for item in recorder.created_indexes
        if item[0] == "uq_buyer_buy_box_versions_current"
    )
    assert current_index[3]["unique"] is True
    assert str(current_index[3]["postgresql_where"]) == "is_current = true"
    assert str(current_index[3]["sqlite_where"]) == "is_current = 1"
    assert any(
        "UPDATE buyer_proof_documents" in statement
        and "status = 'received'" in statement
        for statement in recorder.executed_statements
    )
    assert any(
        "UPDATE buyers" in statement
        and "proof_of_funds_status" in statement
        for statement in recorder.executed_statements
    )


def test_buyer_profiles_migration_downgrade_removes_added_schema() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)
    namespace["downgrade"]()

    assert recorder.dropped_tables == ["buyer_buy_box_versions", "buyer_buy_boxes"]
    assert ("buyers", "tier") in recorder.dropped_columns
    assert ("buyer_proof_documents", "verified_at") in recorder.dropped_columns
    assert ("buyer_engagements", "completed_at") in recorder.dropped_columns
    assert ("disposition_matches", "criteria_snapshot") in recorder.dropped_columns
    assert any(
        "DELETE FROM buyer_engagements" in statement
        and "disposition_case_id IS NULL" in statement
        for statement in recorder.executed_statements
    )
