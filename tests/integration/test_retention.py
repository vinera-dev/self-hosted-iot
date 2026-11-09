import pytest
from stack import psql

pytestmark = pytest.mark.usefixtures("database")

WINDOW = (
    "newer_than => '2030-01-31T00:00:00Z'::timestamptz, "
    "older_than => '2030-02-02T00:00:00Z'::timestamptz"
)


def policies() -> dict[tuple[str, str], str]:
    rows = psql(
        "SELECT hypertable_name, proc_name, config::text FROM timescaledb_information.jobs "
        "WHERE hypertable_name IS NOT NULL"
    ).splitlines()
    found = {}
    for row in rows:
        table, procedure, config = row.split("|", 2)
        found[(table, procedure)] = config
    return found


def test_readings_have_compression_and_retention_policies() -> None:
    found = policies()
    assert "7 days" in found[("readings", "policy_compression")]
    assert "90 days" in found[("readings", "policy_retention")]


def test_rejected_messages_have_a_retention_policy() -> None:
    assert "30 days" in policies()[("rejected_messages", "policy_retention")]


def test_readings_compression_is_segmented_by_device() -> None:
    assert (
        psql(
            "SELECT segmentby_column_index FROM timescaledb_information.compression_settings "
            "WHERE hypertable_name = 'readings' AND attname = 'device_id'"
        )
        == "1"
    )


def test_old_chunk_can_be_compressed_and_still_queried() -> None:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        "SELECT '2030-02-01T00:00:00Z'::timestamptz + n * INTERVAL '1 minute', "
        "'compress-test', 20, 50 FROM generate_series(0, 59) AS n"
    )
    try:
        psql(
            f"SELECT compress_chunk(c, if_not_compressed => true) "
            f"FROM show_chunks('readings', {WINDOW}) AS c"
        )
        assert (
            psql(
                "SELECT count(*) FROM chunk_compression_stats('readings') "
                "WHERE compression_status = 'Compressed'"
            )
            != "0"
        )
        assert psql("SELECT count(*) FROM readings WHERE device_id = 'compress-test'") == "60"
    finally:
        psql(
            f"SELECT decompress_chunk(c, if_compressed => true) "
            f"FROM show_chunks('readings', {WINDOW}) AS c"
        )
        psql("DELETE FROM readings WHERE device_id = 'compress-test'")
