import json
import urllib.parse

import pytest
from stack import service_running, setting
from web import fetch

pytestmark = pytest.mark.usefixtures("database")

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture(scope="module", autouse=True)
def stack_running() -> None:
    if not service_running("nginx") or not service_running("nodered"):
        pytest.skip("nginx and nodered must be running; run `docker compose up -d --wait`")


def login(username: str, password: str) -> tuple[int, dict]:
    body = urllib.parse.urlencode(
        {
            "client_id": "node-red-editor",
            "grant_type": "password",
            "scope": "*",
            "username": username,
            "password": password,
        }
    )
    status, _, text = fetch("/nodered/auth/token", method="POST", headers=FORM, body=body)
    return status, json.loads(text) if text else {}


def test_anonymous_access_to_the_flows_is_denied() -> None:
    status, _, _ = fetch("/nodered/flows")
    assert status == 401


def test_anonymous_deploy_is_denied() -> None:
    status, _, _ = fetch(
        "/nodered/flows",
        method="POST",
        headers={"Content-Type": "application/json"},
        body="[]",
    )
    assert status == 401


def test_anonymous_cannot_list_installed_nodes_or_read_the_context() -> None:
    assert fetch("/nodered/nodes")[0] == 401
    assert fetch("/nodered/context/global")[0] == 401


def test_wrong_password_is_refused() -> None:
    status, body = login(setting("NODE_RED_ADMIN_USER", "admin"), "not-the-password")
    assert status == 403
    assert "access_token" not in body


def test_unknown_user_is_refused() -> None:
    status, body = login("someone-else", setting("NODE_RED_ADMIN_PASSWORD"))
    assert status == 403
    assert "access_token" not in body


def test_valid_credentials_give_a_token_that_opens_the_flows() -> None:
    status, token = login(
        setting("NODE_RED_ADMIN_USER", "admin"), setting("NODE_RED_ADMIN_PASSWORD")
    )
    assert status == 200
    status, _, text = fetch(
        "/nodered/flows", headers={"Authorization": f"Bearer {token['access_token']}"}
    )
    assert status == 200
    assert "in-telemetry" in {node["id"] for node in json.loads(text)}
