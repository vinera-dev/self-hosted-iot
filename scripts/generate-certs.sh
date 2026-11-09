#!/usr/bin/env bash
set -euo pipefail

export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")/.."

CERTS_DIR=certs
DAYS="${CERT_DAYS:-825}"

mkdir -p "$CERTS_DIR"
WORK_DIR="$(mktemp -d "$CERTS_DIR/work.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

openssl req -x509 -newkey rsa:3072 -nodes -days "$DAYS" \
  -subj "/CN=self-hosted-iot development CA" \
  -keyout "$WORK_DIR/ca.key" -out "$CERTS_DIR/ca.crt" 2> /dev/null

cat > "$WORK_DIR/server.cnf" <<CNF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = self-hosted-iot
[ext]
subjectAltName = DNS:localhost, DNS:mosquitto, DNS:nginx, IP:127.0.0.1
extendedKeyUsage = serverAuth
basicConstraints = CA:FALSE
CNF

openssl req -newkey rsa:3072 -nodes -config "$WORK_DIR/server.cnf" \
  -keyout "$CERTS_DIR/server.key" -out "$WORK_DIR/server.csr" 2> /dev/null

openssl x509 -req -in "$WORK_DIR/server.csr" -days "$DAYS" \
  -CA "$CERTS_DIR/ca.crt" -CAkey "$WORK_DIR/ca.key" -CAcreateserial \
  -extfile "$WORK_DIR/server.cnf" -extensions ext \
  -out "$CERTS_DIR/server.crt" 2> /dev/null

chmod 644 "$CERTS_DIR/ca.crt" "$CERTS_DIR/server.crt" "$CERTS_DIR/server.key"

echo "certificates written to $CERTS_DIR (ca.crt, server.crt, server.key)"
