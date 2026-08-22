from pathlib import Path
from runpy import run_path
from typing import Any

import sqlalchemy as sa

MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "0110_batchdialer_direct_sync.py"
)


class MigrationRecorder:
    def __init__(self) -> None:
        self.created_tables: dict[str, tuple[object, ...]] = {}
        self.created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_tables: list[str] = []

    def create_table(self, name: str, *items: object) -> None:
        self.created_tables[name] = items

    def create_index(
        self,
        name: str,
        table_name: str,
        columns: list[str],
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


def test_batchdialer_direct_migration_builds_checkpoint_and_campaign_state() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    assert namespace["revision"] == "0110_batchdialer_direct_sync"
    assert namespace["down_revision"] == "0109_prospecting_acceptance"

    namespace["upgrade"]()

    assert recorder.created_tables.keys() == {
        "batchdialer_sync_checkpoints",
        "batchdialer_campaigns",
    }
    checkpoint_items = recorder.created_tables["batchdialer_sync_checkpoints"]
    checkpoint_columns = _columns(checkpoint_items)
    assert {
        "organization_id",
        "stream",
        "status",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "next_poll_at",
        "scan_date",
        "next_page_cursor",
        "last_attempt_at",
        "last_success_at",
        "last_campaign_refresh_at",
        "last_error",
        "consecutive_failure_count",
        "poll_count",
        "fetched_cdr_count",
        "archived_event_count",
        "updated_event_count",
        "qualified_event_count",
        "quarantined_event_count",
        "sync_metadata",
        "created_at",
        "updated_at",
    } <= checkpoint_columns.keys()
    assert checkpoint_columns["stream"].nullable is False
    stream_default = checkpoint_columns["stream"].server_default
    assert isinstance(stream_default, sa.DefaultClause)
    assert str(stream_default.arg) == "cdrs"
    assert checkpoint_columns["sync_metadata"].nullable is False
    assert {
        "uq_batchdialer_sync_checkpoints_org_stream",
        "ck_batchdialer_sync_checkpoints_lease",
        "ck_batchdialer_sync_checkpoints_counters",
        "fk_batchdialer_sync_checkpoints_organization",
    } <= _constraint_names(checkpoint_items)

    campaign_items = recorder.created_tables["batchdialer_campaigns"]
    campaign_columns = _columns(campaign_items)
    assert {
        "organization_id",
        "provider_campaign_id",
        "parent_campaign_id",
        "external_campaign_id",
        "name",
        "mode",
        "status",
        "is_active",
        "recycle_count",
        "hierarchy_level",
        "contact_count",
        "cdr_seen_count",
        "qualified_cdr_count",
        "imported_lead_count",
        "provider_created_at",
        "first_seen_at",
        "last_seen_at",
        "last_cdr_at",
        "provider_snapshot",
        "created_at",
        "updated_at",
    } <= campaign_columns.keys()
    assert campaign_columns["provider_campaign_id"].nullable is False
    assert campaign_columns["provider_snapshot"].nullable is False
    assert {
        "uq_batchdialer_campaigns_org_provider",
        "ck_batchdialer_campaigns_identity",
        "ck_batchdialer_campaigns_counters",
        "fk_batchdialer_campaigns_organization",
    } <= _constraint_names(campaign_items)

    assert set(recorder.created_indexes) == {
        (
            "ix_batchdialer_sync_checkpoints_due",
            "batchdialer_sync_checkpoints",
            ("stream", "next_poll_at"),
        ),
        (
            "ix_batchdialer_sync_checkpoints_lease",
            "batchdialer_sync_checkpoints",
            ("stream", "lease_expires_at"),
        ),
        (
            "ix_batchdialer_campaigns_org_active_status",
            "batchdialer_campaigns",
            ("organization_id", "is_active", "status"),
        ),
        (
            "ix_batchdialer_campaigns_org_last_cdr",
            "batchdialer_campaigns",
            ("organization_id", "last_cdr_at"),
        ),
    }


def test_batchdialer_direct_migration_downgrade_reverses_dependency_order() -> None:
    recorder = MigrationRecorder()
    namespace = _migration_namespace(recorder)

    namespace["downgrade"]()

    assert recorder.dropped_tables == [
        "batchdialer_campaigns",
        "batchdialer_sync_checkpoints",
    ]
    assert recorder.dropped_indexes == [
        ("ix_batchdialer_campaigns_org_last_cdr", "batchdialer_campaigns"),
        ("ix_batchdialer_campaigns_org_active_status", "batchdialer_campaigns"),
        ("ix_batchdialer_sync_checkpoints_lease", "batchdialer_sync_checkpoints"),
        ("ix_batchdialer_sync_checkpoints_due", "batchdialer_sync_checkpoints"),
    ]
