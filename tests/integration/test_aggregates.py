import pytest
from stack import psql

pytestmark = pytest.mark.usefixtures("database")

DEVICE = "aggregate-test"
DAY = "date_trunc('day', now() - INTERVAL '3 days')"
REFRESH = f"CALL refresh_continuous_aggregate('{{view}}', {DAY}, {DAY} + INTERVAL '1 day')"


@pytest.fixture
def samples():
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"SELECT {DAY} + n * INTERVAL '1 minute', "
        f"'{DEVICE}', 20 + n * 0.5, 50 FROM generate_series(0, 119) AS n"
    )
    yield
    psql(f"DELETE FROM readings WHERE device_id = '{DEVICE}'")
    psql(REFRESH.format(view="readings_5m"))
    psql(REFRESH.format(view="readings_1h"))


def test_continuous_aggregates_and_policies_exist() -> None:
    views = psql(
        "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY view_name"
    ).splitlines()
    assert views == ["readings_1h", "readings_5m"]
    refresh_jobs = psql(
        "SELECT hypertable_name FROM timescaledb_information.jobs "
        "WHERE proc_name = 'policy_refresh_continuous_aggregate' ORDER BY 1"
    ).splitlines()
    assert len(refresh_jobs) == 2


def test_five_minute_aggregate_matches_the_raw_data(samples) -> None:
    psql(REFRESH.format(view="readings_5m"))
    row = psql(
        "SELECT samples, avg_temperature_c, min_temperature_c, max_temperature_c "
        f"FROM readings_5m WHERE device_id = '{DEVICE}' AND bucket = {DAY}"
    )
    assert row == "5|21|20|22"
    assert psql(f"SELECT count(*) FROM readings_5m WHERE device_id = '{DEVICE}'") == "24"


def test_hourly_aggregate_matches_the_raw_data(samples) -> None:
    psql(REFRESH.format(view="readings_1h"))
    row = psql(
        "SELECT samples, avg_temperature_c FROM readings_1h "
        f"WHERE device_id = '{DEVICE}' AND bucket = {DAY} + INTERVAL '1 hour'"
    )
    assert row == "60|64.75"


def test_queries_read_from_the_materialized_hypertable(samples) -> None:
    psql(REFRESH.format(view="readings_5m"))
    plan = psql(
        "EXPLAIN SELECT bucket, avg_temperature_c FROM readings_5m "
        f"WHERE device_id = '{DEVICE}' AND bucket >= {DAY} AND bucket < {DAY} + INTERVAL '1 day'"
    )
    assert "_materialized_hypertable_" in plan
