import pytest
from stack import service_running


@pytest.fixture(scope="session")
def database() -> None:
    if not service_running("timescaledb"):
        pytest.skip("timescaledb is not running; run `docker compose up -d --wait`")
