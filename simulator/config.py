import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceCredentials:
    device_id: str
    password: str


@dataclass(frozen=True)
class SimulatorConfig:
    host: str
    port: int
    interval_seconds: float
    seed: int
    base_temperature_c: float
    devices: tuple[DeviceCredentials, ...]


class ConfigError(ValueError):
    pass


def password_variable(device_id: str) -> str:
    return "MQTT_PASSWORD_" + device_id.upper().replace("-", "_")


def load_config(environ: Mapping[str, str] | None = None) -> SimulatorConfig:
    env = os.environ if environ is None else environ
    raw_ids = [item.strip() for item in env.get("SIM_DEVICES", "device-01").split(",")]
    ids = [item for item in raw_ids if item]
    if not ids:
        raise ConfigError("SIM_DEVICES must list at least one device id.")
    if len(set(ids)) != len(ids):
        raise ConfigError("SIM_DEVICES contains duplicated ids.")
    try:
        port = int(env.get("MQTT_PORT", "21883"))
        interval = float(env.get("SIM_INTERVAL_SECONDS", "5"))
        seed = int(env.get("SIM_SEED", "0"))
        base_temperature = float(env.get("SIM_BASE_TEMPERATURE_C", "22"))
    except ValueError as error:
        raise ConfigError(f"Invalid numeric setting: {error}") from error
    if not 0 < port < 65536:
        raise ConfigError("MQTT_PORT must be between 1 and 65535.")
    if interval <= 0:
        raise ConfigError("SIM_INTERVAL_SECONDS must be positive.")
    devices = []
    for device_id in ids:
        password = env.get(password_variable(device_id), "")
        if not password:
            raise ConfigError(f"Missing {password_variable(device_id)} for device {device_id}.")
        devices.append(DeviceCredentials(device_id, password))
    return SimulatorConfig(
        host=env.get("MQTT_HOST", "127.0.0.1"),
        port=port,
        interval_seconds=interval,
        seed=seed,
        base_temperature_c=base_temperature,
        devices=tuple(devices),
    )
