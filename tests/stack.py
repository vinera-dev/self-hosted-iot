import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMAND_TIMEOUT_SECONDS = 180


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in (".env.example", ".env"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    return values


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or read_env_file().get(name, default)


def compose(
    *args: str, stdin: str | None = None, check: bool = True
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {result.stderr}")
    return result


def service_running(service: str) -> bool:
    try:
        result = compose("ps", "--status", "running", "--services", check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return service in result.stdout.split()


def psql_command(database: str | None) -> list[str]:
    return [
        "exec",
        "-T",
        "timescaledb",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        setting("POSTGRES_USER", "iot"),
        "-d",
        database or setting("POSTGRES_DB", "iot"),
        "-tA",
        "-F",
        "|",
        "-f",
        "-",
    ]


def psql(sql: str, database: str | None = None) -> str:
    return compose(*psql_command(database), stdin=sql).stdout.strip()


def psql_error(sql: str, database: str | None = None) -> str:
    result = compose(*psql_command(database), stdin=sql, check=False)
    assert result.returncode != 0, "the statement was expected to fail"
    return result.stderr
