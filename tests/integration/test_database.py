import uuid

import pytest
from stack import ROOT, compose, psql, psql_error

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
def device_id() -> str:
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup(device_id: str):
    yield
    psql(f"DELETE FROM readings WHERE device_id = '{device_id}'")


def test_timescaledb_extension_is_active() -> None:
    assert psql("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'") == "timescaledb"


def test_readings_is_a_hypertable_with_indexes() -> None:
    assert (
        psql(
            "SELECT hypertable_name FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'readings'"
        )
        == "readings"
    )
    indexes = psql("SELECT indexname FROM pg_indexes WHERE tablename = 'readings'").splitlines()
    assert "readings_device_ts_key" in indexes
    assert any(name.startswith("readings_ts_idx") for name in indexes)


def test_insert_and_query_a_reading(device_id: str) -> None:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"VALUES (now(), '{device_id}', 21.5, 48.2)"
    )
    row = psql(
        "SELECT device_id, temperature_c, humidity_pct FROM readings "
        f"WHERE device_id = '{device_id}'"
    )
    assert row == f"{device_id}|21.5|48.2"


def test_out_of_range_humidity_is_rejected(device_id: str) -> None:
    error = psql_error(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"VALUES (now(), '{device_id}', 21.5, 140)"
    )
    assert "readings_humidity_range" in error


def test_duplicate_device_and_timestamp_is_rejected(device_id: str) -> None:
    insert = (
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"VALUES ('2030-01-01T00:00:00Z', '{device_id}', 20, 50)"
    )
    psql(insert)
    assert "readings_device_ts_key" in psql_error(insert)


def test_all_migrations_are_recorded() -> None:
    versions = psql("SELECT version FROM schema_migrations ORDER BY version").splitlines()
    on_disk = sorted(path.stem for path in (ROOT / "db" / "migrations").glob("*.sql"))
    assert versions == on_disk


def test_migrations_build_an_empty_database_with_one_command() -> None:
    scratch = f"iot_migrate_{uuid.uuid4().hex[:8]}"
    psql(f"CREATE DATABASE {scratch}", database="postgres")
    try:
        run = ["run", "--rm", "--no-deps", "-T", "-e", f"PGDATABASE={scratch}", "migrate"]
        first = compose(*run).stdout
        assert "applied 001_extensions" in first
        assert "applied 002_readings" in first
        assert psql("SELECT count(*) FROM readings", database=scratch) == "0"
        second = compose(*run).stdout
        assert "applied" not in second
        assert "skip    002_readings" in second
    finally:
        psql(f"DROP DATABASE {scratch} WITH (FORCE)", database="postgres")
