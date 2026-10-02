import os
import socket
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from mqtt_helpers import Session, open_session

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = ROOT / ".secrets" / "mqtt-credentials.env"


def load_credentials() -> dict[str, str]:
    credentials = {
        key: value for key, value in os.environ.items() if key.startswith("MQTT_PASSWORD_")
    }
    if credentials:
        return credentials
    if not CREDENTIALS_FILE.exists():
        return {}
    pairs = (
        line.split("=", 1)
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    return {key: value for key, value in pairs}


@pytest.fixture(scope="session")
def broker() -> tuple[str, int]:
    host = os.environ.get("MQTT_HOST", "127.0.0.1")
    port = int(os.environ.get("MQTT_PORT", "11883"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        pytest.skip(f"broker not reachable at {host}:{port}; run `docker compose up -d --wait`")
    return host, port


@pytest.fixture(scope="session")
def credentials() -> dict[str, str]:
    loaded = load_credentials()
    if "MQTT_PASSWORD_SERVICE" not in loaded:
        pytest.skip("no MQTT credentials; run scripts/create-mqtt-users.sh device-01 device-02")
    return loaded


@pytest.fixture
def connect(
    broker: tuple[str, int], credentials: dict[str, str]
) -> Iterator[Callable[[str], Session]]:
    sessions: list[Session] = []

    def _connect(username: str) -> Session:
        key = "MQTT_PASSWORD_" + username.upper().replace("-", "_")
        session = open_session(broker[0], broker[1], username, credentials[key])
        sessions.append(session)
        return session

    yield _connect
    for session in sessions:
        session.close()


@pytest.fixture
def connect_raw(broker: tuple[str, int]) -> Iterator[Callable[[str | None, str | None], Session]]:
    sessions: list[Session] = []

    def _connect(username: str | None, password: str | None) -> Session:
        session = open_session(broker[0], broker[1], username, password)
        sessions.append(session)
        return session

    yield _connect
    for session in sessions:
        session.close()
