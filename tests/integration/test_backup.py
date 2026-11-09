import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from stack import ROOT, compose, psql, service_running

pytestmark = pytest.mark.usefixtures("database")

COMMAND_TIMEOUT_SECONDS = 300
DEVICE = "zz-backup"
SAMPLES = 25
BASH = shutil.which("bash") or "bash"


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )


@pytest.fixture(scope="module", autouse=True)
def stack_running() -> None:
    if not service_running("grafana") or not service_running("nodered"):
        pytest.skip("the whole stack must be running; run `docker compose up -d --wait`")


@pytest.fixture(scope="module")
def backup() -> Iterator[Path]:
    psql(
        "INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) "
        f"SELECT now() - n * INTERVAL '1 minute', '{DEVICE}', 20 + n * 0.1, 50 "
        f"FROM generate_series(1, {SAMPLES}) AS n"
    )
    psql(
        "INSERT INTO rejected_messages (topic, payload, reason) "
        f"VALUES ('devices/{DEVICE}/telemetry', 'backup marker', 'test')"
    )
    destination = ROOT / "backups" / f"pytest-{uuid.uuid4().hex[:8]}"
    result = run_script("scripts/backup.sh", str(destination.relative_to(ROOT)))
    assert result.returncode == 0, result.stderr
    yield destination
    shutil.rmtree(destination, ignore_errors=True)
    psql(f"DELETE FROM readings WHERE device_id = '{DEVICE}'")
    psql(f"DELETE FROM rejected_messages WHERE topic = 'devices/{DEVICE}/telemetry'")


@pytest.fixture
def scratch_database() -> Iterator[str]:
    name = f"iot_restore_{uuid.uuid4().hex[:8]}"
    yield name
    psql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)", database="postgres")


def test_backup_contains_the_database_and_every_volume(backup: Path) -> None:
    names = sorted(path.name for path in backup.iterdir())
    assert names == [
        "SHA256SUMS",
        "grafana-data.tar.gz",
        "mosquitto-data.tar.gz",
        "nodered-data.tar.gz",
        "postgres.dump",
    ]
    assert (backup / "postgres.dump").stat().st_size > 0
    assert (backup / "grafana-data.tar.gz").stat().st_size > 0


def test_database_restores_into_a_clean_database(backup: Path, scratch_database: str) -> None:
    result = run_script(
        "scripts/restore.sh", str(backup.relative_to(ROOT)), "--database", scratch_database
    )
    assert result.returncode == 0, result.stderr

    def count(sql: str) -> str:
        return psql(sql, database=scratch_database)

    assert count(f"SELECT count(*) FROM readings WHERE device_id = '{DEVICE}'") == str(SAMPLES)
    assert count("SELECT count(*) FROM rejected_messages WHERE payload = 'backup marker'") == "1"
    assert count("SELECT count(*) FROM schema_migrations") == psql(
        "SELECT count(*) FROM schema_migrations"
    )
    assert (
        count(
            "SELECT string_agg(view_name, ',' ORDER BY view_name) "
            "FROM timescaledb_information.continuous_aggregates"
        )
        == "readings_1h,readings_5m"
    )
    assert count(
        "SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'"
    ) == psql(
        "SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'"
    )
    assert count("SELECT count(*) FROM timescaledb_information.hypertables") != "0"


def test_restore_refuses_a_database_that_already_has_data(backup: Path) -> None:
    result = run_script("scripts/restore.sh", str(backup.relative_to(ROOT)))
    assert result.returncode != 0
    assert "not empty" in result.stderr


def test_restore_refuses_a_tampered_backup(backup: Path, scratch_database: str) -> None:
    tampered = ROOT / "backups" / f"pytest-tampered-{uuid.uuid4().hex[:8]}"
    shutil.copytree(backup, tampered)
    try:
        dump = tampered / "postgres.dump"
        dump.write_bytes(dump.read_bytes()[:-200])
        result = run_script(
            "scripts/restore.sh", str(tampered.relative_to(ROOT)), "--database", scratch_database
        )
        assert result.returncode != 0
        exists = psql(
            f"SELECT count(*) FROM pg_database WHERE datname = '{scratch_database}'",
            database="postgres",
        )
        assert exists == "0"
    finally:
        shutil.rmtree(tampered, ignore_errors=True)


def test_volumes_restore_into_fresh_volumes(backup: Path, scratch_database: str) -> None:
    suffix = f"-restore-{uuid.uuid4().hex[:6]}"
    names = [
        f"iot_{volume}{suffix}" for volume in ("mosquitto-data", "nodered-data", "grafana-data")
    ]
    try:
        result = subprocess.run(
            [
                BASH,
                "scripts/restore.sh",
                str(backup.relative_to(ROOT)),
                "--database",
                scratch_database,
                "--volumes",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, "RESTORE_VOLUME_SUFFIX": suffix},
        )
        assert result.returncode == 0, result.stderr
        listing = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{names[2]}:/data:ro", "alpine:3.20", "ls", "/data"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert "grafana.db" in listing.stdout.split()
        assert compose("ps", "--status", "running", "--services").stdout
    finally:
        for name in names:
            subprocess.run(["docker", "volume", "rm", "-f", name], capture_output=True, check=False)
