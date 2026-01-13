#!/usr/bin/env bash
set -euo pipefail

# Simple migrations apply script using psql.
# Requires DATABASE_URL env var pointing to your Supabase Postgres connection string.

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL env var is required (postgres://user:pass@host:port/db)" >&2
  exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"

for f in $(ls -1 ${DIR}/*.sql | sort); do
  echo "Applying: $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "All migrations applied."

