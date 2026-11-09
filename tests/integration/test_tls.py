import os
import socket
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime

import pytest
from mqtt_helpers import open_session
from stack import ROOT, psql, service_running, setting
from web import CA_FILE, fetch, trusted_context

pytestmark = pytest.mark.usefixtures("database")

HOST = "127.0.0.1"
POLL_TIMEOUT_SECONDS = 25.0


@pytest.fixture(scope="module", autouse=True)
def tls_ready() -> None:
    if not CA_FILE.exists():
        pytest.skip("no certificates; run scripts/generate-certs.sh")
    if not service_running("mosquitto") or not service_running("nginx"):
        pytest.skip("mosquitto and nginx must be running; run `docker compose up -d --wait`")


def tls_port() -> int:
    return int(setting("MQTT_TLS_PORT", "21884"))


def test_encrypted_mqtt_connection_works_and_data_is_ingested(credentials: dict[str, str]) -> None:
    session = open_session(
        HOST, tls_port(), "device-01", credentials["MQTT_PASSWORD_DEVICE_01"], ca_certs=str(CA_FILE)
    )
    try:
        assert session.connect_code == 0
        ts = datetime.now(UTC).isoformat()
        payload = (
            f'{{"device_id": "device-01", "ts": "{ts}", "temperature_c": 20.5, "humidity_pct": 40}}'
        )
        assert session.publish("devices/device-01/telemetry", payload) == 0
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        stored = ""
        while time.monotonic() < deadline and not stored:
            stored = psql(
                f"SELECT count(*) FROM readings WHERE ts = '{ts}' AND device_id = 'device-01'"
            )
            stored = "" if stored == "0" else stored
            time.sleep(0.5)
        assert stored == "1"
    finally:
        session.close()


def test_mqtt_tls_still_requires_valid_credentials() -> None:
    session = open_session(HOST, tls_port(), "device-01", "wrong-password", ca_certs=str(CA_FILE))
    try:
        assert session.connect_code in (134, 135)
    finally:
        session.close()


def test_mqtt_client_that_does_not_trust_the_ca_cannot_complete_the_handshake() -> None:
    with (
        pytest.raises(ssl.SSLCertVerificationError),
        socket.create_connection((HOST, tls_port()), timeout=10) as raw,
        ssl.create_default_context().wrap_socket(raw, server_hostname=HOST),
    ):
        pass


def test_mqtt_client_rejects_a_certificate_for_another_hostname() -> None:
    with (
        pytest.raises(ssl.SSLCertVerificationError),
        socket.create_connection((HOST, tls_port()), timeout=10) as raw,
        trusted_context().wrap_socket(raw, server_hostname="broker.example.org"),
    ):
        pass


def test_plain_mqtt_to_the_tls_port_is_refused(credentials: dict[str, str]) -> None:
    with pytest.raises((TimeoutError, OSError)):
        open_session(HOST, tls_port(), "device-01", credentials["MQTT_PASSWORD_DEVICE_01"])


def test_certificate_is_signed_by_the_ca_and_names_loopback() -> None:
    with (
        socket.create_connection((HOST, tls_port()), timeout=10) as raw,
        trusted_context().wrap_socket(raw, server_hostname=HOST) as secured,
    ):
        assert secured.version() in ("TLSv1.2", "TLSv1.3")
        names = secured.getpeercert()["subjectAltName"]
    assert ("IP Address", "127.0.0.1") in names


def test_https_works_with_the_ca_and_fails_without_it() -> None:
    status, _, _ = fetch("/grafana/api/health")
    assert status == 200
    with pytest.raises(ssl.SSLCertVerificationError):
        fetch("/grafana/api/health", context=ssl.create_default_context())


def test_simulator_publishes_over_tls(credentials: dict[str, str]) -> None:
    started = datetime.now(UTC).isoformat()
    environment = {
        **os.environ,
        "MQTT_PASSWORD_DEVICE_05": credentials["MQTT_PASSWORD_DEVICE_05"],
        "SIM_DEVICES": "device-05",
        "SIM_INTERVAL_SECONDS": "0.5",
        "MQTT_HOST": HOST,
        "MQTT_PORT": str(tls_port()),
        "MQTT_TLS_CA": str(CA_FILE),
    }
    process = subprocess.Popen([sys.executable, "-m", "simulator"], cwd=ROOT, env=environment)
    try:
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        count = "0"
        while time.monotonic() < deadline and count == "0":
            count = psql(
                f"SELECT count(*) FROM readings WHERE device_id = 'device-05' AND ts > '{started}'"
            )
            time.sleep(0.5)
        assert count != "0"
    finally:
        process.terminate()
        process.wait(timeout=15)
