import json

import pytest
from stack import compose, service_running
from web import fetch

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture(scope="module", autouse=True)
def proxy_running() -> None:
    if not service_running("nginx"):
        pytest.skip("nginx is not running; run `docker compose up -d --wait`")


def test_plain_http_is_redirected_to_https() -> None:
    status, headers, _ = fetch("/grafana/login?x=1", secure=False)
    assert status == 308
    assert headers["location"].startswith("https://127.0.0.1:")
    assert headers["location"].endswith("/grafana/login?x=1")


def test_root_redirects_to_grafana() -> None:
    status, headers, _ = fetch("/")
    assert status == 302
    assert headers["location"].endswith("/grafana/")


def test_grafana_is_served_under_its_prefix() -> None:
    status, _, body = fetch("/grafana/api/health")
    assert status == 200
    assert json.loads(body)["database"] == "ok"


def test_node_red_editor_is_served_under_its_prefix() -> None:
    status, _, body = fetch("/nodered/")
    assert status == 200
    assert "Node-RED" in body


def test_websocket_upgrade_reaches_node_red() -> None:
    status, headers, _ = fetch(
        "/nodered/comms",
        headers={
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        },
    )
    assert status == 101
    assert headers["upgrade"].lower() == "websocket"


def test_unknown_paths_are_not_proxied() -> None:
    status, _, _ = fetch("/alerts/grafana", method="POST", body="{}")
    assert status == 404


def test_only_the_proxy_publishes_the_web_interfaces() -> None:
    rows = [
        json.loads(line)
        for line in compose("ps", "--format", "json").stdout.splitlines()
        if line.strip()
    ]
    published = {row["Service"]: row.get("Publishers") or [] for row in rows}
    assert not [item for item in published["grafana"] if item.get("PublishedPort")]
    assert not [item for item in published["nodered"] if item.get("PublishedPort")]
    assert [item for item in published["nginx"] if item.get("PublishedPort")]
