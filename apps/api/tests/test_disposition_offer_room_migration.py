from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

from app.models.foundation import (
    BuyerOffer,
    DispositionBuyerOutcome,
    DispositionBuyerSelection,
    DispositionBuyerSelectionSlot,
    DispositionClosingCheckpoint,
    DispositionDeadlineAlert,
    DispositionOfferNegotiationEvent,
    DispositionOfferRevision,
)

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0118_disposition_offer_room.py"
)

BUYER_OFFER_COLUMNS = (
    "idempotency_key",
    "lock_version",
    "funding_confidence_basis_points",
    "due_diligence_days",
    "contingencies",
    "contingencies_confirmed",
    "proposed_closing_at",
    "special_terms",
)
BUYER_OFFER_CONSTRAINTS = {
    "uq_buyer_offer_case_idempotency",
    "ck_buyer_offer_lock_version",
    "ck_buyer_offer_funding_confidence",
}


class MigrationRecorder:
    def __init__(self) -> None:
        self.created_tables: list[tuple[str, tuple[object, ...]]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], dict[str, object]]] = []
        self.added_columns: list[tuple[str, sa.Column[Any]]] = []
        self.created_constraints: list[tuple[str, str, tuple[str, ...], str]] = []
        self.dropped_indexes: list[tuple[str, str | None]] = []
        self.dropped_tables: list[str] = []
        self.dropped_constraints: list[tuple[str, str, str | None]] = []
        self.dropped_columns: list[tuple[str, str]] = []

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

    def add_column(self, table_name: str, column: sa.Column[Any]) -> None:
        self.added_columns.append((table_name, column))

    def create_unique_constraint(
        self,
        name: str,
        table_name: str,
        columns: list[str],
    ) -> None:
        self.created_constraints.append((name, table_name, tuple(columns), "unique"))

    def create_check_constraint(self, name: str, table_name: str, condition: str) -> None:
        self.created_constraints.append((name, table_name, (condition,), "check"))

    def drop_index(self, name: str, *, table_name: str | None = None) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, table_name: str) -> None:
        self.dropped_tables.append(table_name)

    def drop_constraint(
        self,
        name: str,
        table_name: str,
        *,
        type_: str | None = None,
    ) -> None:
        self.dropped_constraints.append((name, table_name, type_))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))


def _namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def _columns(items: tuple[object, ...]) -> dict[str, sa.Column[Any]]:
    return {str(item.name): item for item in items if isinstance(item, sa.Column)}


def _named_constraints(items: tuple[object, ...]) -> dict[str, sa.Constraint]:
    return {
        str(item.name): item
        for item in items
        if isinstance(item, sa.Constraint) and item.name is not None
    }


def _foreign_key_signature(constraint: sa.ForeignKeyConstraint) -> tuple[object, ...]:
    return (
        tuple(constraint.column_keys),
        tuple(element.target_fullname for element in constraint.elements),
        constraint.ondelete,
    )


def _migration_indexes(
    recorder: MigrationRecorder,
    table_name: str,
) -> set[tuple[object, ...]]:
    return {
        (name, columns, bool(kwargs.get("unique", False)))
        for name, recorded_table, columns, kwargs in recorder.created_indexes
        if recorded_table == table_name
    }


def _model_indexes(table: sa.Table) -> set[tuple[object, ...]]:
    return {
        (str(index.name), tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def test_ds7_migration_matches_all_offer_room_models() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    assert namespace["revision"] == "0118_disposition_offer_room"
    assert namespace["down_revision"] == "0117_disposition_outreach"
    namespace["upgrade"]()

    models = {
        "disposition_offer_revisions": DispositionOfferRevision,
        "disposition_offer_negotiations": DispositionOfferNegotiationEvent,
        "disposition_buyer_selections": DispositionBuyerSelection,
        "disposition_buyer_selection_slots": DispositionBuyerSelectionSlot,
        "disposition_closing_checkpoints": DispositionClosingCheckpoint,
        "disposition_deadline_alerts": DispositionDeadlineAlert,
        "disposition_buyer_outcomes": DispositionBuyerOutcome,
    }
    created_tables = dict(recorder.created_tables)
    assert set(created_tables) == set(models)
    for table_name, model in models.items():
        items = created_tables[table_name]
        assert set(_columns(items)) == set(model.__table__.columns.keys())
        assert _migration_indexes(recorder, table_name) == _model_indexes(model.__table__)

        migration_constraints = _named_constraints(items)
        model_constraints = {
            str(item.name): item
            for item in model.__table__.constraints
            if item.name is not None
        }
        assert set(migration_constraints) == set(model_constraints)
        assert {
            name: str(item.sqltext)
            for name, item in migration_constraints.items()
            if isinstance(item, sa.CheckConstraint)
        } == {
            name: str(item.sqltext)
            for name, item in model_constraints.items()
            if isinstance(item, sa.CheckConstraint)
        }
        assert {
            _foreign_key_signature(item)
            for item in items
            if isinstance(item, sa.ForeignKeyConstraint)
        } == {
            _foreign_key_signature(item) for item in model.__table__.foreign_key_constraints
        }


def test_ds7_migration_alters_buyer_offer_to_match_model() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    namespace["upgrade"]()

    added = {
        str(column.name): column
        for table_name, column in recorder.added_columns
        if table_name == "buyer_offers"
    }
    assert tuple(added) == BUYER_OFFER_COLUMNS
    for name, column in added.items():
        model_column = BuyerOffer.__table__.columns[name]
        assert column.nullable == model_column.nullable
        assert type(column.type) is type(model_column.type)
    assert {
        name
        for name, table_name, _, _ in recorder.created_constraints
        if table_name == "buyer_offers"
    } == BUYER_OFFER_CONSTRAINTS
    unique = next(
        item
        for item in recorder.created_constraints
        if item[0] == "uq_buyer_offer_case_idempotency"
    )
    assert unique[2] == ("organization_id", "disposition_case_id", "idempotency_key")


def test_ds7_downgrade_only_removes_ds7_schema() -> None:
    recorder = MigrationRecorder()
    namespace = _namespace(recorder)
    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "disposition_buyer_outcomes",
        "disposition_deadline_alerts",
        "disposition_closing_checkpoints",
        "disposition_buyer_selection_slots",
        "disposition_buyer_selections",
        "disposition_offer_negotiations",
        "disposition_offer_revisions",
    ]
    assert {table for _, table in recorder.dropped_indexes} == {
        "disposition_buyer_outcomes",
        "disposition_deadline_alerts",
        "disposition_closing_checkpoints",
        "disposition_buyer_selections",
        "disposition_offer_negotiations",
        "disposition_offer_revisions",
    }
    assert {name for name, table, _ in recorder.dropped_constraints if table == "buyer_offers"} == (
        BUYER_OFFER_CONSTRAINTS
    )
    assert tuple(
        name for table, name in recorder.dropped_columns if table == "buyer_offers"
    ) == tuple(reversed(BUYER_OFFER_COLUMNS))
