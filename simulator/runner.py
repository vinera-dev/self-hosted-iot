import signal
import sys
import threading
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from simulator.config import ConfigError, DeviceCredentials, SimulatorConfig, load_config
from simulator.device import Device


class MqttClient(Protocol):
    def publish(self, topic: str, payload: str, qos: int = 0) -> Any: ...

    def subscribe(self, topic: str, qos: int = 0) -> Any: ...


class DeviceSession:
    def __init__(self, device: Device, client: MqttClient) -> None:
        self.device = device
        self.client = client

    def on_connect(self) -> None:
        self.client.subscribe(self.device.commands_topic, qos=1)
        self.client.publish(self.device.state_topic, self.device.state(), qos=1)

    def on_message(self, topic: str, payload: bytes) -> None:
        if topic != self.device.commands_topic:
            return
        state = self.device.handle_command(payload)
        if state is not None:
            self.client.publish(self.device.state_topic, state, qos=1)

    def publish_telemetry(self) -> None:
        self.client.publish(self.device.telemetry_topic, self.device.telemetry(), qos=1)


def build_client(credentials: DeviceCredentials, config: SimulatorConfig) -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=credentials.device_id)
    client.username_pw_set(credentials.device_id, credentials.password)
    client.connect(config.host, config.port)
    return client


def start_sessions(config: SimulatorConfig) -> list[DeviceSession]:
    sessions = []
    for credentials in config.devices:
        client = build_client(credentials, config)
        device = Device(
            credentials.device_id,
            seed=config.seed,
            base_temperature_c=config.base_temperature_c,
        )
        session = DeviceSession(device, client)
        client.on_connect = lambda _c, _u, _f, _r, _p, session=session: session.on_connect()
        client.on_message = lambda _c, _u, message, session=session: session.on_message(
            message.topic, message.payload
        )
        client.loop_start()
        sessions.append(session)
    return sessions


def run(config: SimulatorConfig, stop: threading.Event) -> None:
    sessions = start_sessions(config)
    try:
        while not stop.wait(config.interval_seconds):
            for session in sessions:
                session.publish_telemetry()
    finally:
        for session in sessions:
            session.client.loop_stop()
            session.client.disconnect()


def main() -> int:
    try:
        config = load_config()
    except ConfigError as error:
        sys.stderr.write(f"configuration error: {error}\n")
        return 2
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    run(config, stop)
    return 0
