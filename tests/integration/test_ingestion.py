import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from mqtt_helpers import Session
from stack import ROOT, psql, service_running

pytestmark = pytest.mark.usefixtures("database")

POLL_TIMEOUT_SECONDS = 25.0
POLL_INTERVAL_SECONDS = 0.5
SUCCESS = 0

Connect = Callable[[str], Session]


@pytest.fixture(scope="module", autouse=True)
def ingestion_running() -> None:
    if not service_running("nodered"):
        pytest.skip("nodered is not running; run `docker compose up -d --wait`")


def wait_for(sql: str) -> str:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = psql(sql)
        if result:
            return result
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"no result for: {sql}")


def telemetry(device_id: str, **overrides: object) -> str:
    body = {
        "device_id": device_id,
        "ts": datetime.now(UTC).isoformat(),
        "temperature_c": 21.5,
        "humidity_pct": 47.0,
    }
    body.update(overrides)
    return json.dumps(body)


def test_valid_reading_is_stored(connect: Connect) -> None:
    device = connect("device-01")
    ts = datetime.now(UTC).isoformat()
    payload = telemetry("device-01", ts=ts, temperature_c=23.25, humidity_pct=51.5)

    assert device.publish("devices/device-01/telemetry", payload) == SUCCESS

    row = wait_for(
        "SELECT device_id, temperature_c, humidity_pct FROM readings "
        f"WHERE device_id = 'device-01' AND ts = '{ts}'"
    )
    assert row == "device-01|23.25|51.5"


def test_broken_payload_is_recorded_as_rejected(connect: Connect) -> None:
    device = connect("device-01")
    marker = uuid.uuid4().hex
    payload = '{"temperature_c": ' + marker

    assert device.publish("devices/device-01/telemetry", payload) == SUCCESS

    row = wait_for(
        f"SELECT topic, payload, reason FROM rejected_messages WHERE payload LIKE '%{marker}%'"
    )
    topic, stored, reason = row.split("|")
    assert topic == "devices/device-01/telemetry"
    assert stored == payload
    assert "not valid JSON" in reason


def test_out_of_range_reading_is_rejected_and_not_stored(connect: Connect) -> None:
    device = connect("device-01")
    ts = datetime.now(UTC).isoformat()
    payload = telemetry("device-01", ts=ts, temperature_c=999)

    device.publish("devices/device-01/telemetry", payload)

    row = wait_for(f"SELECT reason FROM rejected_messages WHERE payload LIKE '%{ts}%'")
    assert "temperature_c" in row
    assert psql(f"SELECT count(*) FROM readings WHERE ts = '{ts}'") == "0"


def test_reading_for_another_device_is_rejected(connect: Connect) -> None:
    device = connect("device-02")
    ts = datetime.now(UTC).isoformat()

    device.publish("devices/device-02/telemetry", telemetry("device-01", ts=ts))

    row = wait_for(f"SELECT reason FROM rejected_messages WHERE payload LIKE '%{ts}%'")
    assert "does not match the topic" in row
    assert psql(f"SELECT count(*) FROM readings WHERE ts = '{ts}'") == "0"


def test_device_state_is_stored(connect: Connect) -> None:
    device = connect("device-02")
    ts = datetime.now(UTC).isoformat()
    payload = json.dumps({"device_id": "device-02", "ts": ts, "relay": "on"})

    device.publish("devices/device-02/state", payload)

    row = wait_for(
        f"SELECT relay FROM device_states WHERE device_id = 'device-02' AND updated_at = '{ts}'"
    )
    assert row == "on"


def test_simulator_readings_reach_the_database(credentials: dict[str, str], broker) -> None:
    host, port = broker
    environment = {
        **os.environ,
        **{key: value for key, value in credentials.items() if key.startswith("MQTT_PASSWORD_")},
        "SIM_DEVICES": "device-01,device-02,device-03",
        "SIM_INTERVAL_SECONDS": "0.5",
        "MQTT_HOST": host,
        "MQTT_PORT": str(port),
    }
    started = datetime.now(UTC).isoformat()
    process = subprocess.Popen([sys.executable, "-m", "simulator"], cwd=ROOT, env=environment)
    try:
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        devices = ""
        while time.monotonic() < deadline:
            devices = psql(
                "SELECT string_agg(device_id, ',' ORDER BY device_id) FROM "
                f"(SELECT DISTINCT device_id FROM readings WHERE ts > '{started}') AS recent"
            )
            if devices == "device-01,device-02,device-03":
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        assert devices == "device-01,device-02,device-03"
    finally:
        process.terminate()
        process.wait(timeout=15)
