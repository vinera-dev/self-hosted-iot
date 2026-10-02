#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <device-id> [<device-id> ...]" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

PASSWD_FILE=/mosquitto/config/passwd
SECRETS_DIR=.secrets
CREDENTIALS_FILE="$SECRETS_DIR/mqtt-credentials.env"

mkdir -p "$SECRETS_DIR"
: > "$CREDENTIALS_FILE"
chmod 600 "$CREDENTIALS_FILE"

generate_password() {
  head -c 18 /dev/urandom | base64 | tr '+/' 'ab'
}

env_name() {
  printf 'MQTT_PASSWORD_%s' "$(printf '%s' "$1" | tr 'a-z-' 'A-Z_')"
}

add_user() {
  local user="$1" password="$2" create_flag="$3"
  docker compose run --rm --no-deps -T --entrypoint mosquitto_passwd mosquitto \
    -b $create_flag "$PASSWD_FILE" "$user" "$password" > /dev/null
  printf '%s=%s\n' "$(env_name "$user")" "$password" >> "$CREDENTIALS_FILE"
}

docker compose run --rm --no-deps -T --entrypoint sh mosquitto \
  -c "rm -f $PASSWD_FILE" > /dev/null

add_user service "$(generate_password)" "-c"
for device in "$@"; do
  add_user "$device" "$(generate_password)" ""
done

docker compose run --rm --no-deps -T --entrypoint sh mosquitto \
  -c "chown mosquitto:mosquitto $PASSWD_FILE && chmod 600 $PASSWD_FILE" > /dev/null

echo "created users: service $*"
echo "credentials written to $CREDENTIALS_FILE"
