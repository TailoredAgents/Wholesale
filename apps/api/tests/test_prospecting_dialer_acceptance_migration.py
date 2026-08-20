from __future__ import annotations

from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

from app.services import prospecting_dialer_acceptance as acceptance_service

MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "0109_prospecting_dialer_acceptance.py"
)
COORDINATOR_MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "0105_prospecting_dial_coordinator.py"
)


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class MigrationRecorder:
    def __init__(self, *, as_sql: bool = True, has_evidence: bool = False) -> None:
        self.as_sql = as_sql
        self.has_evidence = has_evidence
        self.operations: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_context(self) -> SimpleNamespace:
        return SimpleNamespace(as_sql=self.as_sql)

    def get_bind(self) -> MigrationRecorder:
        return self

    def execute(self, statement: object) -> _ScalarResult:
        self.operations.append(("sql", (str(statement),), {}))
        return _ScalarResult(self.has_evidence)

    def create_table(self, name: str, *items: object) -> None:
        self.operations.append(("create_table", (name, *items), {}))

    def create_index(
        self,
        name: str,
        table: str,
        columns: list[str],
        **kwargs: object,
    ) -> None:
        self.operations.append(("create_index", (name, table, tuple(columns)), kwargs))

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.operations.append(("add_column", (table, column), {}))

    def create_foreign_key(
        self,
        name: str,
        table: str,
        target: str,
        local_columns: list[str],
        remote_columns: list[str],
        **kwargs: object,
    ) -> None:
        self.operations.append(
            (
                "create_foreign_key",
                (name, table, target, tuple(local_columns), tuple(remote_columns)),
                kwargs,
            )
        )

    def drop_index(self, name: str, *, table_name: str) -> None:
        self.operations.append(("drop_index", (name, table_name), {}))

    def drop_constraint(self, name: str, table: str, *, type_: str) -> None:
        self.operations.append(("drop_constraint", (name, table, type_), {}))

    def drop_column(self, table: str, column: str) -> None:
        self.operations.append(("drop_column", (table, column), {}))

    def drop_table(self, table: str) -> None:
        self.operations.append(("drop_table", (table,), {}))


def migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def _created_table(
    recorder: MigrationRecorder,
    table_name: str,
) -> tuple[object, ...]:
    return next(
        operation[1][1:]
        for operation in recorder.operations
        if operation[0] == "create_table" and operation[1][0] == table_name
    )


def test_d10_upgrade_adds_bounded_pilot_and_single_use_review_evidence() -> None:
    recorder = MigrationRecorder()
    namespace = migration_namespace(recorder)

    assert namespace["revision"] == "0109_prospecting_acceptance"
    assert namespace["down_revision"] == "0108_prospecting_callbacks"
    namespace["upgrade"]()

    added_columns = {
        (str(operation[1][0]), str(operation[1][1].name)): operation[1][1]
        for operation in recorder.operations
        if operation[0] == "add_column"
    }
    acceptance_required = added_columns[("organizations", "prospecting_dialer_acceptance_required")]
    assert acceptance_required.nullable is False
    assert str(acceptance_required.server_default.arg) == "true"
    assert ("prospecting_dial_sessions", "pilot_id") in added_columns

    pilot_items = _created_table(recorder, "prospecting_dialer_pilots")
    pilot_columns = {item.name: item for item in pilot_items if isinstance(item, sa.Column)}
    assert {
        "caller_user_id",
        "campaign_id",
        "cohort_id",
        "prospect_calling_batch_id",
        "voice_line_id",
        "effective_line_count",
        "required_clean_shift_count",
        "minimum_attempts_per_shift",
        "minimum_productive_minutes_per_shift",
        "minimum_total_attempts",
        "minimum_batch_size",
        "maximum_batch_size",
        "daily_dial_limit",
        "daily_spend_limit_cents",
        "configuration_fingerprint",
        "final_evidence_snapshot",
        "evidence_hash",
        "accepted_by_user_id",
        "rollback_reason",
        "revoked_at",
        "cancelled_at",
        "cancellation_reason",
    } <= pilot_columns.keys()
    pilot_constraints = {
        item.name: item for item in pilot_items if isinstance(item, sa.Constraint) and item.name
    }
    pilot_fk_targets = {
        item.elements[0].target_fullname
        for item in pilot_items
        if isinstance(item, sa.ForeignKeyConstraint)
    }
    assert {
        "organizations.id",
        "users.id",
        "campaigns.id",
        "prospecting_cohorts.id",
        "prospect_calling_batches.id",
        "voice_lines.id",
    } <= pilot_fk_targets
    assert "ck_prospecting_dialer_pilots_one_line" in pilot_constraints
    assert "ck_prospecting_dialer_pilots_thresholds" in pilot_constraints
    batch_check = str(pilot_constraints["ck_prospecting_dialer_pilots_batch_bounds"].sqltext)
    assert "minimum_batch_size >= 75" in batch_check
    assert "maximum_batch_size <= 250" in batch_check
    daily_dials = str(pilot_constraints["ck_prospecting_dialer_pilots_daily_dials"].sqltext)
    assert "BETWEEN 25 AND 50" in daily_dials
    daily_spend = str(pilot_constraints["ck_prospecting_dialer_pilots_daily_spend"].sqltext)
    assert "BETWEEN 1 AND 1000" in daily_spend
    assert "ck_prospecting_dialer_pilots_cancelled" in pilot_constraints
    assert "uq_prospecting_dialer_pilots_org_revision" not in pilot_constraints
    assert "uq_prospecting_dialer_pilots_org_fingerprint" not in pilot_constraints

    attempt_items = _created_table(recorder, "prospecting_dialer_pilot_attempt_reviews")
    attempt_constraints = {item.name for item in attempt_items if isinstance(item, sa.Constraint)}
    assert "uq_prospecting_pilot_attempt_reviews_attempt" in attempt_constraints
    assert "ck_prospecting_pilot_attempt_reviews_passed" in attempt_constraints
    attempt_fk_targets = {
        item.elements[0].target_fullname
        for item in attempt_items
        if isinstance(item, sa.ForeignKeyConstraint)
    }
    assert {
        "prospecting_dialer_pilots.id",
        "prospecting_attempts.id",
        "prospecting_dial_sessions.id",
    } <= attempt_fk_targets

    shift_items = _created_table(recorder, "prospecting_dialer_pilot_shift_reviews")
    shift_constraints = {item.name for item in shift_items if isinstance(item, sa.Constraint)}
    assert "uq_prospecting_pilot_shift_reviews_session" not in shift_constraints
    assert "uq_prospecting_pilot_shift_reviews_pilot_date" in shift_constraints
    assert "ck_prospecting_pilot_shift_reviews_passed" in shift_constraints
    shift_fk_targets = {
        item.elements[0].target_fullname
        for item in shift_items
        if isinstance(item, sa.ForeignKeyConstraint)
    }
    assert {
        "prospecting_dialer_pilots.id",
        "prospecting_dial_sessions.id",
    } <= shift_fk_targets

    session_pilot_fk = next(
        operation
        for operation in recorder.operations
        if operation[0] == "create_foreign_key"
        and operation[1][0] == "fk_prospecting_dial_sessions_pilot_id"
    )
    assert session_pilot_fk[1][2] == "prospecting_dialer_pilots"
    assert session_pilot_fk[2]["ondelete"] == "SET NULL"

    open_index = next(
        operation
        for operation in recorder.operations
        if operation[0] == "create_index"
        and operation[1][0] == "uq_prospecting_dialer_pilots_open_org"
    )
    assert open_index[2]["unique"] is True
    assert str(open_index[2]["postgresql_where"]) == str(open_index[2]["sqlite_where"])


def test_d10_downgrade_refuses_to_discard_acceptance_evidence() -> None:
    recorder = MigrationRecorder(as_sql=False, has_evidence=True)
    namespace = migration_namespace(recorder)

    with pytest.raises(RuntimeError, match="pilot evidence exists"):
        namespace["downgrade"]()

    assert not any(
        operation in {"drop_column", "drop_constraint", "drop_table"}
        for operation, _args, _kwargs in recorder.operations
    )


def test_d10_does_not_redeclare_coordinator_provider_cost_column() -> None:
    coordinator_source = COORDINATOR_MIGRATION.read_text(encoding="utf-8")
    d10_source = MIGRATION.read_text(encoding="utf-8")

    assert '"actual_cost_cents"' in coordinator_source
    assert 'add_column(\n        "prospecting_dial_legs"' not in d10_source
    assert 'drop_column("prospecting_dial_legs", "actual_cost_cents")' not in d10_source


def test_d10_ready_pilot_keeps_manager_rollback_and_owner_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pilot = SimpleNamespace(status="ready_for_owner_review")
    principal = SimpleNamespace()

    monkeypatch.setattr(acceptance_service, "_is_owner", lambda _db, _principal: False)
    assert acceptance_service._allowed_actions(None, principal, pilot, []) == ["rollback"]

    monkeypatch.setattr(acceptance_service, "_is_owner", lambda _db, _principal: True)
    assert acceptance_service._allowed_actions(None, principal, pilot, []) == [
        "accept",
        "reject",
        "rollback",
    ]


@pytest.mark.parametrize("status", ["rejected", "rolled_back", "revoked", "cancelled"])
def test_d10_terminal_pilot_exposes_replacement_create(status: str) -> None:
    pilot = SimpleNamespace(status=status)

    assert acceptance_service._allowed_actions(None, SimpleNamespace(), pilot, []) == ["create"]


@pytest.mark.parametrize(
    ("decision", "phrase"),
    [
        ("accept", "ACCEPT SINGLE-LINE DIALER"),
        ("reject", "REJECT SINGLE-LINE DIALER"),
    ],
)
def test_d10_owner_decisions_require_the_exact_server_phrase(
    decision: str,
    phrase: str,
) -> None:
    payload = acceptance_service.ProspectingDialerPilotDecision(
        expected_revision=1,
        idempotency_key=f"decision-{decision}",
        decision=decision,
        confirmation_phrase=phrase,
        reason="Controlled decision test.",
    )
    acceptance_service._require_decision_confirmation(payload)

    payload.confirmation_phrase = None
    with pytest.raises(ValueError, match=phrase):
        acceptance_service._require_decision_confirmation(payload)
