#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required." >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is required. Install the PostgreSQL client tools first." >&2
  exit 1
fi

backup_dir="${BACKUP_DIR:-.backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="${backup_dir}/stonegate-${timestamp}.dump"
database_url="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

mkdir -p "$backup_dir"
umask 077
pg_dump --format=custom --no-owner --no-acl --file="$backup_path" "$database_url"

echo "Backup created: $backup_path"
