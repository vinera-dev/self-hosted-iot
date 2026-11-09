import json
import threading
from datetime import UTC, datetime

import pytest

from simulator.config import ConfigError, load_config, password_variable
from simulator.device import Device
from simulator.runner import DeviceSession, run

FIXED_TIME = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def fixed_clock():
    return FIXED_TIME


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscribed = []
        self.loop_started = False
        self.disconnected = False

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, json.loads(payload), qos))

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_started = False

    def disconnect(self):
        self.disconnected = True


ENV = {
    "SIM_DEVICES": "device-01,device-02",
    "MQTT_PASSWORD_DEVICE_01": "a",
    "MQTT_PASSWORD_DEVICE_02": "b",
}


def test_topics_follow_the_access_control_list():
    device = Device("device-07")

    assert device.telemetry_topic == "devices/device-07/telemetry"
    assert device.state_topic == "devices/device-07/state"
    assert device.commands_topic == "devices/device-07/commands"


def test_telemetry_is_json_with_time_temperature_and_humidity():
    device = Device("device-01", clock=fixed_clock)

    reading = json.loads(device.telemetry())

    assert set(reading) == {"device_id", "ts", "temperature_c", "humidity_pct"}
    assert reading["device_id"] == "device-01"
    assert reading["ts"] == "2030-01-01T12:00:00+00:00"
    assert isinstance(reading["temperature_c"], float)
    assert 0 <= reading["humidity_pct"] <= 100


def test_same_seed_produces_the_same_readings_and_devices_differ():
    first = [Device("device-01", seed=1, clock=fixed_clock).telemetry() for _ in range(1)]
    again = [Device("device-01", seed=1, clock=fixed_clock).telemetry() for _ in range(1)]
    other = [Device("device-02", seed=1, clock=fixed_clock).telemetry() for _ in range(1)]

    assert first == again
    assert first != other


def test_readings_drift_but_stay_in_physical_bounds():
    device = Device("device-01", base_temperature_c=59.9, base_humidity_pct=99.9, seed=3)

    readings = [json.loads(device.telemetry()) for _ in range(500)]

    assert all(-10 <= r["temperature_c"] <= 60 for r in readings)
    assert all(0 <= r["humidity_pct"] <= 100 for r in readings)
    assert len({r["temperature_c"] for r in readings}) > 10


def test_relay_on_cools_the_device_over_time():
    on = Device("device-01", seed=5, relay="on")
    off = Device("device-01", seed=5, relay="off")

    for _ in range(100):
        on.step()
        off.step()

    assert on.temperature_c < off.temperature_c


@pytest.mark.parametrize("command", [{"relay": "on"}, {"relay": "off"}])
def test_valid_commands_change_the_relay_and_return_the_state(command):
    device = Device("device-01", clock=fixed_clock)

    state = json.loads(device.handle_command(json.dumps(command)))

    assert state["relay"] == command["relay"]
    assert device.relay == command["relay"]
    assert state["ts"] == "2030-01-01T12:00:00+00:00"


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"[]", b'"on"', b'{"relay": "toggle"}', b'{"relay": 1}', b"{}", None],
)
def test_invalid_commands_are_ignored(payload):
    device = Device("device-01")

    assert device.handle_command(payload) is None
    assert device.relay == "off"


def test_session_subscribes_and_announces_its_state_on_connect():
    client = FakeClient()
    session = DeviceSession(Device("device-01", clock=fixed_clock), client)

    session.on_connect()

    assert client.subscribed == [("devices/device-01/commands", 1)]
    assert client.published[0][0] == "devices/device-01/state"
    assert client.published[0][1]["relay"] == "off"


def test_session_answers_commands_with_the_published_state():
    client = FakeClient()
    session = DeviceSession(Device("device-01", clock=fixed_clock), client)

    session.on_message("devices/device-01/commands", b'{"relay": "on"}')

    topic, state, qos = client.published[0]
    assert (topic, state["relay"], qos) == ("devices/device-01/state", "on", 1)


def test_session_ignores_other_topics_and_invalid_commands():
    client = FakeClient()
    session = DeviceSession(Device("device-01"), client)

    session.on_message("devices/device-02/commands", b'{"relay": "on"}')
    session.on_message("devices/device-01/commands", b"garbage")

    assert client.published == []
    assert session.device.relay == "off"


def test_session_publishes_telemetry_on_its_own_topic():
    client = FakeClient()
    session = DeviceSession(Device("device-01", clock=fixed_clock), client)

    session.publish_telemetry()

    topic, reading, _ = client.published[0]
    assert topic == "devices/device-01/telemetry"
    assert reading["device_id"] == "device-01"


def test_config_defaults_to_one_device():
    config = load_config({"MQTT_PASSWORD_DEVICE_01": "secret"})

    assert [d.device_id for d in config.devices] == ["device-01"]
    assert (config.host, config.port, config.interval_seconds, config.seed) == (
        "127.0.0.1",
        21883,
        5.0,
        0,
    )


def test_config_reads_the_base_temperature():
    config = load_config({"MQTT_PASSWORD_DEVICE_01": "secret", "SIM_BASE_TEMPERATURE_C": "31.5"})

    assert config.base_temperature_c == 31.5
    assert load_config({"MQTT_PASSWORD_DEVICE_01": "secret"}).base_temperature_c == 22.0


def test_config_supports_several_devices_with_their_own_passwords():
    config = load_config(ENV)

    assert [(d.device_id, d.password) for d in config.devices] == [
        ("device-01", "a"),
        ("device-02", "b"),
    ]


def test_password_variable_name():
    assert password_variable("device-12") == "MQTT_PASSWORD_DEVICE_12"


@pytest.mark.parametrize(
    "env",
    [
        {"SIM_DEVICES": "device-01"},
        {"SIM_DEVICES": " , "},
        {"SIM_DEVICES": "device-01,device-01", "MQTT_PASSWORD_DEVICE_01": "a"},
        {"SIM_DEVICES": "device-01", "MQTT_PASSWORD_DEVICE_01": "a", "MQTT_PORT": "abc"},
        {"SIM_DEVICES": "device-01", "MQTT_PASSWORD_DEVICE_01": "a", "MQTT_PORT": "70000"},
        {"SIM_DEVICES": "device-01", "MQTT_PASSWORD_DEVICE_01": "a", "SIM_INTERVAL_SECONDS": "0"},
        {
            "SIM_DEVICES": "device-01",
            "MQTT_PASSWORD_DEVICE_01": "a",
            "SIM_BASE_TEMPERATURE_C": "hot",
        },
    ],
)
def test_invalid_configuration_is_rejected(env):
    with pytest.raises(ConfigError):
        load_config(env)


def test_run_publishes_for_every_device_each_interval_and_stops(monkeypatch):
    clients = []

    def fake_build(credentials, config):
        client = FakeClient()
        clients.append((credentials.device_id, client))
        return client

    monkeypatch.setattr("simulator.runner.build_client", fake_build)
    config = load_config({**ENV, "SIM_INTERVAL_SECONDS": "0.01"})
    stop = threading.Event()
    timer = threading.Timer(0.15, stop.set)
    timer.start()

    run(config, stop)
    timer.join()

    assert [device_id for device_id, _ in clients] == ["device-01", "device-02"]
    for device_id, client in clients:
        topics = {topic for topic, _, _ in client.published}
        assert topics == {f"devices/{device_id}/telemetry"}
        assert len(client.published) >= 2
        assert client.disconnected is True
        assert client.loop_started is False
