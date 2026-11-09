#!/bin/sh
set -eu

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/db/migrations}"

psql -v ON_ERROR_STOP=1 -q -o /dev/null -c "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"

for file in "$MIGRATIONS_DIR"/*.sql; do
  version=$(basename "$file" .sql)
  applied=$(psql -v ON_ERROR_STOP=1 -tA -c "SELECT 1 FROM schema_migrations WHERE version = '$version'")
  if [ -n "$applied" ]; then
    echo "skip    $version"
    continue
  fi
  record="INSERT INTO schema_migrations (version) VALUES ('$version')"
  case "$version" in
    *.notx)
      psql -v ON_ERROR_STOP=1 -q -o /dev/null -f "$file"
      psql -v ON_ERROR_STOP=1 -q -o /dev/null -c "$record"
      ;;
    *)
      psql -v ON_ERROR_STOP=1 -q -o /dev/null --single-transaction -f "$file" -c "$record"
      ;;
  esac
  echo "applied $version"
done
