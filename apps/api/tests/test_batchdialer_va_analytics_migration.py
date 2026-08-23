from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0111_batchdialer_va_analytics.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.created_tables: dict[str, tuple[object, ...]] = {}
        self.created_indexes: list[tuple[str, str, tuple[object, ...]]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

    def create_table(self, name: str, *items: object) -> None:
        self.created_tables[name] = items

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[object],
        **_kwargs: object,
    ) -> None:
        self.created_indexes.append((name, table_name, tuple(columns)))

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.dropped_indexes.append((name, table_name))

    def drop_table(self, table_name: str) -> None:
        self.dropped_tables.append(table_name)


def _migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def _columns(items: tuple[object, ...]) -> dict[str, sa.Column[Any]]:
    return {
        str(item.name): item
        for item in items
        if isinstance(item, sa.Column) and item.name is not None
    }


def _constraint_names(items: tuple[object, ...]) -> set[str]:
    return {
        str(item.name)
        for item in items
        if isinstance(item, sa.Constraint) and item.name is not None
    }


def test_migration_builds_agent_identity_and_normalized_call_fact_tables() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    assert namespace["revision"] == "0111_batchdialer_va_facts"
    assert namespace["down_revision"] == "0110_batchdialer_direct_sync"
    namespace["upgrade"]()

    assert recorder.created_tables.keys() == {
        "batchdialer_agent_identities",
        "batchdialer_call_facts",
    }
    agent_items = recorder.created_tables["batchdialer_agent_identities"]
    assert {
        "organization_id",
        "provider_agent_id",
        "display_name",
        "mapped_user_id",
        "mapped_by_user_id",
        "mapped_at",
        "first_seen_at",
        "last_seen_at",
        "provider_snapshot",
    } <= _columns(agent_items).keys()
    assert {
        "uq_batchdialer_agent_identities_org_provider",
        "uq_batchdialer_agent_identities_org_mapped_user",
        "ck_batchdialer_agent_identities_explicit_mapping",
        "fk_batchdialer_agent_identities_mapped_user",
    } <= _constraint_names(agent_items)
    mapping_check = next(
        item
        for item in agent_items
        if isinstance(item, sa.CheckConstraint)
        and item.name == "ck_batchdialer_agent_identities_explicit_mapping"
    )
    assert "mapped_at IS NOT NULL" in str(mapping_check.sqltext)
    assert "mapped_by_user_id" not in str(mapping_check.sqltext)

    fact_items = recorder.created_tables["batchdialer_call_facts"]
    assert {
        "provider_event_id",
        "agent_identity_id",
        "lead_id",
        "call_record_id",
        "provider_cdr_id",
        "provider_call_id",
        "provider_contact_id",
        "provider_campaign_id",
        "provider_agent_id",
        "started_at",
        "ended_at",
        "duration_seconds",
        "direction",
        "provider_status",
        "raw_disposition",
        "disposition_classification",
        "final_outcome",
        "final_qualification_status",
        "is_voicemail",
        "recording_available",
        "transcript_available",
        "qualification_evidence_present",
        "normalization_version",
        "final_processing_status",
    } <= _columns(fact_items).keys()
    assert {
        "uq_batchdialer_call_facts_provider_event",
        "uq_batchdialer_call_facts_org_cdr",
        "fk_batchdialer_call_facts_provider_event",
        "fk_batchdialer_call_facts_agent_identity",
    } <= _constraint_names(fact_items)
    assert len(recorder.created_indexes) == 6
    assert any(
        name == "ix_batchdialer_call_facts_org_activity"
        and "COALESCE(started_at, occurred_at, received_at)" in str(columns[1])
        for name, _table, columns in recorder.created_indexes
    )


def test_migration_downgrade_removes_facts_before_agent_identities() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "batchdialer_call_facts",
        "batchdialer_agent_identities",
    ]
    assert len(recorder.dropped_indexes) == 6
