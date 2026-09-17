from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.main import app

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0134_pg_stat_statements.py"


class MigrationRecorder:
    def __init__(self, dialect_name: str) -> None:
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.executed: list[str] = []

    def get_bind(self) -> Any:
        return self.bind

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def _migration_namespace(recorder: MigrationRecorder) -> dict[str, Any]:
    namespace = run_path(str(MIGRATION))
    namespace["upgrade"].__globals__["op"] = recorder
    namespace["downgrade"].__globals__["op"] = recorder
    return namespace


def test_pg_stat_statements_migration_is_postgresql_only_and_idempotent() -> None:
    postgres = MigrationRecorder("postgresql")
    postgres_migration = _migration_namespace(postgres)

    assert postgres_migration["down_revision"] == "0133_batchdialer_campaign_route"
    postgres_migration["upgrade"]()
    postgres_migration["downgrade"]()

    assert postgres.executed == ["CREATE EXTENSION IF NOT EXISTS pg_stat_statements"]

    sqlite = MigrationRecorder("sqlite")
    sqlite_migration = _migration_namespace(sqlite)
    sqlite_migration["upgrade"]()

    assert sqlite.executed == []


def test_database_observability_endpoint_is_safe_for_sqlite(
    api_db_override: None,
) -> None:
    response = TestClient(app).get("/health/database-observability")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "database": {
            "dialect": "sqlite",
            "pg_stat_statements": "not_applicable",
        },
        "pool": {
            "class": "StaticPool",
            "size": None,
            "checked_in": None,
            "checked_out": None,
            "overflow": None,
        },
    }
