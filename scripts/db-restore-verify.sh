#!/usr/bin/env bash
set -euo pipefail

backup_path="${1:-}"
if [[ -z "$backup_path" || ! -f "$backup_path" ]]; then
  echo "Usage: RESTORE_DATABASE_URL=... ALLOW_RESTORE_TEST=true $0 <backup.dump>" >&2
  exit 1
fi

if [[ "${ALLOW_RESTORE_TEST:-false}" != "true" ]]; then
  echo "Set ALLOW_RESTORE_TEST=true to confirm this guarded restore drill." >&2
  exit 1
fi

if [[ -z "${RESTORE_DATABASE_URL:-}" ]]; then
  echo "RESTORE_DATABASE_URL is required." >&2
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" && "$RESTORE_DATABASE_URL" == "$DATABASE_URL" ]]; then
  echo "Refusing to restore into DATABASE_URL." >&2
  exit 1
fi

normalized_target="$(printf '%s' "$RESTORE_DATABASE_URL" | tr '[:upper:]' '[:lower:]')"
if [[ "$normalized_target" != *test* && "$normalized_target" != *restore* && "$normalized_target" != *verify* ]]; then
  echo "Restore target must include test, restore, or verify in its URL." >&2
  exit 1
fi

for command_name in pg_restore psql; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required. Install the PostgreSQL client tools first." >&2
    exit 1
  fi
done

database_url="${RESTORE_DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$database_url" "$backup_path"

psql "$database_url" --set ON_ERROR_STOP=1 --tuples-only --command \
  "SELECT version_num FROM alembic_version; SELECT COUNT(*) FROM organizations; SELECT COUNT(*) FROM leads;"

echo "Restore verification completed against the isolated target database."
