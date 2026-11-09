import json
import time
from collections.abc import Iterator

import grafana_client as grafana
import pytest
from stack import ROOT, psql, service_running

pytestmark = pytest.mark.usefixtures("database")

DEVICES = ("zz-online", "zz-offline", "zz-old")
TELEMETRY = "iot-telemetry"
HEALTH = "iot-health"


@pytest.fixture(scope="module", autouse=True)
def grafana_running() -> None:
    if not service_running("grafana"):
        pytest.skip("grafana is not running; run `docker compose up -d --wait`")


@pytest.fixture(scope="module")
def seeded() -> Iterator[None]:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        "SELECT now() - n * INTERVAL '10 seconds', 'zz-online', 20 + n * 0.1, 50 "
        "FROM generate_series(0, 30) AS n UNION ALL "
        "SELECT now() - INTERVAL '10 minutes' - n * INTERVAL '10 seconds', 'zz-offline', 24, 55 "
        "FROM generate_series(0, 10) AS n UNION ALL "
        "SELECT now() - INTERVAL '50 minutes' - n * INTERVAL '10 seconds', 'zz-old', 30, 60 "
        "FROM generate_series(0, 5) AS n"
    )
    yield
    psql("DELETE FROM readings WHERE device_id LIKE 'zz-%'")


def test_datasource_is_provisioned_and_connects() -> None:
    status, body = grafana.request("/api/datasources/uid/timescaledb")
    assert status == 200
    assert body["readOnly"] is True
    assert body["isDefault"] is True
    status, health = grafana.request("/api/datasources/uid/timescaledb/health")
    assert status == 200
    assert health["status"] == "OK"


def test_anonymous_users_cannot_query_grafana() -> None:
    status, _ = grafana.request("/api/datasources", authenticated=False)
    assert status == 401


def test_dashboards_are_provisioned_with_the_repository_json() -> None:
    for name, uid in (("telemetry", TELEMETRY), ("health", HEALTH)):
        on_disk = json.loads((ROOT / "grafana" / "dashboards" / f"{name}.json").read_text("utf-8"))
        live = grafana.dashboard(uid)
        assert live["title"] == on_disk["title"]
        assert [item["title"] for item in live["panels"]] == [
            item["title"] for item in on_disk["panels"]
        ]


def test_telemetry_panels_return_data_per_device(seeded: None) -> None:
    variables = {"device": ["zz-online", "zz-offline"]}
    temperature = grafana.series(grafana.run_panel(TELEMETRY, "Temperature", variables))
    humidity = grafana.series(grafana.run_panel(TELEMETRY, "Humidity", variables))
    assert set(temperature) == {"zz-online", "zz-offline"}
    assert set(humidity) == {"zz-online", "zz-offline"}
    offline_values = [value for _, value in temperature["zz-offline"] if value is not None]
    assert offline_values
    assert {round(value) for value in offline_values} == {24}


def test_device_filter_limits_the_series(seeded: None) -> None:
    one = grafana.series(grafana.run_panel(TELEMETRY, "Temperature", {"device": ["zz-online"]}))
    assert set(one) == {"zz-online"}
    latest = grafana.table_rows(
        grafana.run_panel(TELEMETRY, "Latest reading per device", {"device": ["zz-offline"]})
    )
    assert [row["device"] for row in latest] == ["zz-offline"]


def test_time_range_filter_limits_the_points(seeded: None) -> None:
    now = int(time.time() * 1000)
    narrow = grafana.series(
        grafana.run_panel(
            TELEMETRY, "Temperature", {"device": ["zz-old", "zz-online"]}, now - 120_000, now
        )
    )
    assert set(narrow) == {"zz-online"}
    wide = grafana.series(
        grafana.run_panel(
            TELEMETRY, "Temperature", {"device": ["zz-old", "zz-online"]}, now - 3_600_000, now
        )
    )
    assert set(wide) == {"zz-old", "zz-online"}


def test_hourly_panel_reads_the_aggregate() -> None:
    target = grafana.panel(
        grafana.dashboard(TELEMETRY), "Hourly average temperature (hourly aggregate)"
    )
    assert "readings_1h" in target["targets"][0]["rawSql"]
    frames = grafana.run_panel(
        TELEMETRY, "Hourly average temperature (hourly aggregate)", {"device": ["zz-online"]}
    )
    assert isinstance(frames, list)


def health_status(offline_after: int) -> dict[str, str]:
    frames = grafana.run_panel(
        HEALTH,
        "Devices",
        {"device": list(DEVICES), "offline_after": str(offline_after)},
    )
    return {row["device"]: row["status"] for row in grafana.table_rows(frames)}


def test_stalled_device_is_listed_as_offline(seeded: None) -> None:
    status = health_status(60)
    assert status["zz-online"] == "online"
    assert status["zz-offline"] == "offline"
    assert status["zz-old"] == "offline"


def test_offline_threshold_is_respected(seeded: None) -> None:
    status = health_status(3600)
    assert status == {"zz-online": "online", "zz-offline": "online", "zz-old": "online"}


def test_offline_counter_matches_the_table(seeded: None) -> None:
    variables = {"device": list(DEVICES), "offline_after": "60"}
    offline = grafana.table_rows(grafana.run_panel(HEALTH, "Devices offline", variables))
    online = grafana.table_rows(grafana.run_panel(HEALTH, "Devices online", variables))
    assert offline[0]["offline"] == 2
    assert online[0]["online"] == 1


def test_dashboards_declare_the_device_and_threshold_variables() -> None:
    telemetry = {item["name"] for item in grafana.dashboard(TELEMETRY)["templating"]["list"]}
    health = {item["name"] for item in grafana.dashboard(HEALTH)["templating"]["list"]}
    assert telemetry == {"device"}
    assert health == {"device", "offline_after"}
    assert grafana.dashboard(TELEMETRY)["refresh"] == "10s"
