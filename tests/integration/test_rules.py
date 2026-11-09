import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from itertools import groupby

import pytest
from mqtt_helpers import Session
from stack import ROOT, service_running

pytestmark = pytest.mark.usefixtures("database")

WAIT_SECONDS = 90.0
SETTLE_SECONDS = 6.0

Connect = Callable[[str], Session]


@pytest.fixture(scope="module", autouse=True)
def ingestion_running() -> None:
    if not service_running("nodered"):
        pytest.skip("nodered is not running; run `docker compose up -d --wait`")


def relay_states(session: Session, until: Callable[[list[str]], bool], timeout: float) -> list[str]:
    seen: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until(seen):
        message = session.received(1.0)
        if message is not None:
            seen.append(json.loads(message.payload)["relay"])
    return seen


def test_hot_device_switches_the_relay_on_then_off_without_oscillating(
    connect: Connect, credentials: dict[str, str], broker
) -> None:
    host, port = broker
    watcher = connect("service")
    watcher.subscribe("devices/device-04/state")
    environment = {
        **os.environ,
        **{key: value for key, value in credentials.items() if key.startswith("MQTT_PASSWORD_")},
        "SIM_DEVICES": "device-04",
        "SIM_BASE_TEMPERATURE_C": "31",
        "SIM_INTERVAL_SECONDS": "0.5",
        "MQTT_HOST": host,
        "MQTT_PORT": str(port),
    }
    process = subprocess.Popen([sys.executable, "-m", "simulator"], cwd=ROOT, env=environment)
    try:
        seen = relay_states(
            watcher, lambda states: "on" in states and states[-1] == "off", WAIT_SECONDS
        )
        seen += relay_states(watcher, lambda _states: False, SETTLE_SECONDS)
    finally:
        process.terminate()
        process.wait(timeout=15)

    collapsed = [state for state, _ in groupby(seen)]
    assert collapsed == ["off", "on", "off"]
