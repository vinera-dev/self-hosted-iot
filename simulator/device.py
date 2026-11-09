import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

MIN_TEMPERATURE_C = -10.0
MAX_TEMPERATURE_C = 60.0
MAX_HUMIDITY_PCT = 100.0
RELAY_STATES = ("on", "off")


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Device:
    device_id: str
    seed: int = 0
    base_temperature_c: float = 22.0
    base_humidity_pct: float = 50.0
    clock: Callable[[], datetime] = utc_now
    relay: str = "off"
    temperature_c: float = field(init=False)
    humidity_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(f"{self.device_id}:{self.seed}")
        self.temperature_c = self.base_temperature_c
        self.humidity_pct = self.base_humidity_pct

    @property
    def telemetry_topic(self) -> str:
        return f"devices/{self.device_id}/telemetry"

    @property
    def state_topic(self) -> str:
        return f"devices/{self.device_id}/state"

    @property
    def commands_topic(self) -> str:
        return f"devices/{self.device_id}/commands"

    def step(self) -> None:
        drift = -0.3 if self.relay == "on" else 0.0
        self.temperature_c += self._rng.uniform(-0.4, 0.4) + drift
        self.humidity_pct += self._rng.uniform(-1.0, 1.0)
        self.temperature_c = min(max(self.temperature_c, MIN_TEMPERATURE_C), MAX_TEMPERATURE_C)
        self.humidity_pct = min(max(self.humidity_pct, 0.0), MAX_HUMIDITY_PCT)

    def telemetry(self) -> str:
        self.step()
        return json.dumps(
            {
                "device_id": self.device_id,
                "ts": self.clock().isoformat(),
                "temperature_c": round(self.temperature_c, 2),
                "humidity_pct": round(self.humidity_pct, 2),
            }
        )

    def state(self) -> str:
        return json.dumps(
            {"device_id": self.device_id, "ts": self.clock().isoformat(), "relay": self.relay}
        )

    def handle_command(self, payload: bytes | str) -> str | None:
        try:
            command = json.loads(payload)
        except (ValueError, TypeError):
            return None
        if not isinstance(command, dict) or command.get("relay") not in RELAY_STATES:
            return None
        self.relay = command["relay"]
        return self.state()
