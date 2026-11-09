#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

usage() {
  echo "usage: $0 <backup-dir> [--database NAME] [--volumes]" >&2
  exit 1
}

if [ "$#" -lt 1 ]; then
  usage
fi

SOURCE="$1"
shift

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-iot}"
POSTGRES_DB="${POSTGRES_DB:-iot}"
PROJECT="${COMPOSE_PROJECT_NAME:-iot}"
HELPER_IMAGE="${BACKUP_HELPER_IMAGE:-alpine:3.20}"
VOLUME_SUFFIX="${RESTORE_VOLUME_SUFFIX:-}"
VOLUMES=(mosquitto-data nodered-data grafana-data)
TARGET_DB="$POSTGRES_DB"
RESTORE_VOLUMES=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --database)
      TARGET_DB="${2:?--database needs a name}"
      shift 2
      ;;
    --volumes)
      RESTORE_VOLUMES=1
      shift
      ;;
    *)
      usage
      ;;
  esac
done

if [ ! -f "$SOURCE/postgres.dump" ]; then
  echo "no postgres.dump in $SOURCE" >&2
  exit 1
fi

(cd "$SOURCE" && sha256sum --check --quiet SHA256SUMS)

psql_admin() {
  docker compose exec -T timescaledb psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -tA "$@"
}

exists="$(psql_admin -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET_DB'")"
if [ -n "$exists" ]; then
  tables="$(psql_admin -d "$TARGET_DB" -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
  if [ "$tables" != "0" ]; then
    echo "database $TARGET_DB is not empty; restore into an empty database" >&2
    exit 1
  fi
else
  psql_admin -d postgres -c "CREATE DATABASE \"$TARGET_DB\""
fi

psql_admin -d "$TARGET_DB" -c "CREATE EXTENSION IF NOT EXISTS timescaledb" > /dev/null
psql_admin -d "$TARGET_DB" -c "SELECT timescaledb_pre_restore()" > /dev/null

restore_status=0
docker compose exec -T timescaledb pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" \
  --no-owner --exit-on-error < "$SOURCE/postgres.dump" || restore_status=$?

psql_admin -d "$TARGET_DB" -c "SELECT timescaledb_post_restore()" > /dev/null

if [ "$restore_status" -ne 0 ]; then
  echo "pg_restore failed with status $restore_status" >&2
  exit "$restore_status"
fi

echo "database restored into $TARGET_DB"

if [ "$RESTORE_VOLUMES" -eq 1 ]; then
  for volume in "${VOLUMES[@]}"; do
    docker run --rm -i -v "${PROJECT}_${volume}${VOLUME_SUFFIX}:/data" "$HELPER_IMAGE" \
      sh -c 'rm -rf /data/* /data/.[!.]* 2> /dev/null; tar xzf - -C /data' < "$SOURCE/$volume.tar.gz"
    echo "volume ${PROJECT}_${volume}${VOLUME_SUFFIX} restored"
  done
fi
