import time
from collections.abc import Iterator

import grafana_client as grafana
import pytest
from stack import compose, psql, service_running

pytestmark = pytest.mark.usefixtures("database")

DEVICE = "zz-alert"
WAIT_SECONDS = 90.0


@pytest.fixture(scope="module", autouse=True)
def stack_running() -> None:
    if not service_running("grafana") or not service_running("nodered"):
        pytest.skip("grafana and nodered must be running; run `docker compose up -d --wait`")


@pytest.fixture
def clean_alerts() -> Iterator[None]:
    psql(f"DELETE FROM alert_events WHERE device_id = '{DEVICE}'")
    yield
    psql(f"DELETE FROM readings WHERE device_id = '{DEVICE}'")
    psql(f"DELETE FROM alert_events WHERE device_id = '{DEVICE}'")


def wait_for_alert(status: str) -> str:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        row = psql(
            "SELECT alert_name || '|' || summary FROM alert_events "
            f"WHERE device_id = '{DEVICE}' AND status = '{status}' LIMIT 1"
        )
        if row:
            return row
        time.sleep(2)
    raise AssertionError(f"no {status} alert for {DEVICE}")


def test_alert_rule_and_contact_point_are_provisioned() -> None:
    status, rules = grafana.request("/api/v1/provisioning/alert-rules")
    assert status == 200
    assert [rule["title"] for rule in rules] == ["High temperature"]
    status, points = grafana.request("/api/v1/provisioning/contact-points")
    assert status == 200
    webhook = next(point for point in points if point["name"] == "nodered-webhook")
    assert webhook["settings"]["url"] == "http://nodered:1880/alerts/grafana"


def test_high_temperature_fires_an_alert_that_reaches_node_red(clean_alerts: None) -> None:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"VALUES (now(), '{DEVICE}', 38, 40)"
    )

    row = wait_for_alert("firing")

    assert row == "High temperature|Temperature above 32 C in the last minute"


def test_normal_temperature_does_not_alert(clean_alerts: None) -> None:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"VALUES (now(), '{DEVICE}', 22, 40)"
    )
    time.sleep(35)

    assert (
        psql(
            f"SELECT count(*) FROM alert_events WHERE device_id = '{DEVICE}' AND status = 'firing'"
        )
        == "0"
    )


def test_malformed_webhook_is_refused_by_node_red() -> None:
    result = compose(
        "exec",
        "-T",
        "nodered",
        "node",
        "-e",
        "fetch('http://127.0.0.1:1880/alerts/grafana', {method: 'POST', "
        "headers: {'content-type': 'application/json'}, body: '{\"alerts\": \"x\"}'})"
        ".then(r => console.log(r.status))",
    )
    assert result.stdout.strip() == "400"
