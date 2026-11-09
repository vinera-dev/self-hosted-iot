#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

IMAGES=(
  "eclipse-mosquitto:2"
  "timescale/timescaledb:2.17.2-pg16"
  "nodered/node-red:4.0.5"
  "grafana/grafana:11.3.0"
  "nginx:1.27-alpine"
  "alpine:3.20"
)

if [ "$#" -gt 0 ]; then
  IMAGES=("$@")
fi

status=0
printf '| Image | linux/amd64 | linux/arm64 |\n|---|---|---|\n'
for image in "${IMAGES[@]}"; do
  platforms="$(docker buildx imagetools inspect "$image" | awk '/Platform:/ {print $2}')"
  amd64="no"
  arm64="no"
  if printf '%s\n' "$platforms" | grep -qE '^linux/amd64(/|$)'; then amd64="yes"; fi
  if printf '%s\n' "$platforms" | grep -qE '^linux/arm64(/|$)'; then arm64="yes"; fi
  printf '| `%s` | %s | %s |\n' "$image" "$amd64" "$arm64"
  if [ "$amd64" != "yes" ] || [ "$arm64" != "yes" ]; then
    status=1
  fi
done
exit "$status"
