#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

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
VOLUMES=(mosquitto-data nodered-data grafana-data)

DEST="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$DEST"
chmod 700 "$DEST"

docker compose exec -T timescaledb pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$DEST/postgres.dump"

for volume in "${VOLUMES[@]}"; do
  name="$(docker volume ls -q \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter "label=com.docker.compose.volume=$volume")"
  if [ -z "$name" ]; then
    echo "volume $volume not found for project $PROJECT" >&2
    exit 1
  fi
  docker run --rm -v "$name:/data:ro" "$HELPER_IMAGE" tar czf - -C /data . > "$DEST/$volume.tar.gz"
done

(cd "$DEST" && sha256sum postgres.dump ./*.tar.gz > SHA256SUMS)

echo "backup written to $DEST"
