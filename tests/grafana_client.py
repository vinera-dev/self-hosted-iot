import base64
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from stack import ROOT, setting

REQUEST_TIMEOUT_SECONDS = 20


def tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=str(ROOT / "certs" / "ca.crt"))


def base_url() -> str:
    return setting("GRAFANA_URL") or f"https://127.0.0.1:{setting('HTTPS_PORT', '21443')}/grafana"


def credentials() -> str:
    user = setting("GRAFANA_ADMIN_USER", "admin")
    password = setting("GRAFANA_ADMIN_PASSWORD")
    return base64.b64encode(f"{user}:{password}".encode()).decode()


def request(path: str, body: dict | None = None, authenticated: bool = True) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = f"Basic {credentials()}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base_url() + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(
            req, timeout=REQUEST_TIMEOUT_SECONDS, context=tls_context()
        ) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        payload = error.read()
        return error.code, json.loads(payload) if payload else None


def dashboard(uid: str) -> dict:
    status, body = request(f"/api/dashboards/uid/{uid}")
    assert status == 200, f"dashboard {uid} not found"
    return body["dashboard"]


def panel(dash: dict, title: str) -> dict:
    for item in dash["panels"]:
        if item["title"] == title:
            return item
    raise KeyError(title)


def substitute(sql: str, variables: dict[str, str | list[str]]) -> str:
    for name, value in variables.items():
        if isinstance(value, list):
            value = ",".join(f"'{item}'" for item in value)
        sql = re.sub(r"\$\{" + name + r"\}|\$" + name + r"(?!\w)", lambda _m, v=value: v, sql)
    return sql


def run_panel(
    uid: str,
    title: str,
    variables: dict[str, str | list[str]],
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[dict]:
    target = panel(dashboard(uid), title)["targets"][0]
    now = int(time.time() * 1000)
    body = {
        "queries": [
            {
                "refId": target["refId"],
                "datasource": target["datasource"],
                "rawSql": substitute(target["rawSql"], variables),
                "format": target["format"],
                "rawQuery": True,
                "intervalMs": 30000,
                "maxDataPoints": 500,
            }
        ],
        "from": str(start_ms if start_ms is not None else now - 3600000),
        "to": str(end_ms if end_ms is not None else now),
    }
    status, payload = request("/api/ds/query", body)
    assert status == 200, payload
    result = payload["results"][target["refId"]]
    assert "error" not in result, result.get("error")
    return result.get("frames", [])


def table_rows(frames: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for frame in frames:
        names = [field["name"] for field in frame["schema"]["fields"]]
        columns = frame["data"]["values"]
        for index in range(len(columns[0]) if columns else 0):
            rows.append({name: column[index] for name, column in zip(names, columns, strict=True)})
    return rows


def series(frames: list[dict]) -> dict[str, list[tuple[int, float]]]:
    found: dict[str, list[tuple[int, float]]] = {}
    for frame in frames:
        fields = frame["schema"]["fields"]
        times, *values = frame["data"]["values"]
        for field, column in zip(fields[1:], values, strict=True):
            found[field["name"]] = list(zip(times, column, strict=True))
    return found
