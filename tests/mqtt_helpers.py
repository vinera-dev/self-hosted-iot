import queue
import threading
import uuid
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

NOT_AUTHORIZED = 135
BAD_CREDENTIALS = 134
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class Message:
    topic: str
    payload: str


@dataclass
class Session:
    client: mqtt.Client
    connect_code: int | None = None
    connected: threading.Event = field(default_factory=threading.Event)
    messages: "queue.Queue[Message]" = field(default_factory=queue.Queue)
    publish_codes: dict[int, int] = field(default_factory=dict)
    publish_events: dict[int, threading.Event] = field(default_factory=dict)
    subscribe_codes: dict[int, list[int]] = field(default_factory=dict)
    subscribe_events: dict[int, threading.Event] = field(default_factory=dict)

    def publish(self, topic: str, payload: str) -> int:
        info = self.client.publish(topic, payload, qos=1)
        event = self.publish_events.setdefault(info.mid, threading.Event())
        if not event.wait(DEFAULT_TIMEOUT_SECONDS):
            raise TimeoutError(f"no PUBACK for {topic}")
        return self.publish_codes[info.mid]

    def subscribe(self, topic: str) -> list[int]:
        _, mid = self.client.subscribe(topic, qos=1)
        event = self.subscribe_events.setdefault(mid, threading.Event())
        if not event.wait(DEFAULT_TIMEOUT_SECONDS):
            raise TimeoutError(f"no SUBACK for {topic}")
        return self.subscribe_codes[mid]

    def received(self, timeout: float) -> Message | None:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


def open_session(
    host: str, port: int, username: str | None, password: str | None
) -> Session:
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=f"test-{uuid.uuid4().hex[:12]}",
        protocol=mqtt.MQTTv5,
    )
    if username is not None:
        client.username_pw_set(username, password)
    session = Session(client=client)

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        session.connect_code = reason_code.value
        session.connected.set()

    def on_publish(_client, _userdata, mid, reason_code, _properties):
        session.publish_codes[mid] = reason_code.value
        session.publish_events.setdefault(mid, threading.Event()).set()

    def on_subscribe(_client, _userdata, mid, reason_codes, _properties):
        session.subscribe_codes[mid] = [code.value for code in reason_codes]
        session.subscribe_events.setdefault(mid, threading.Event()).set()

    def on_message(_client, _userdata, message):
        session.messages.put(Message(message.topic, message.payload.decode()))

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(host, port)
    client.loop_start()
    if not session.connected.wait(DEFAULT_TIMEOUT_SECONDS):
        client.loop_stop()
        raise TimeoutError("no CONNACK from the broker")
    return session
