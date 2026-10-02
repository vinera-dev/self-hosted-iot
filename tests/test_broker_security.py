from collections.abc import Callable

from mqtt_helpers import BAD_CREDENTIALS, NOT_AUTHORIZED, Session

NO_MESSAGE_WAIT_SECONDS = 1.0
DELIVERY_WAIT_SECONDS = 5.0
SUCCESS = 0
GRANTED_QOS_1 = 1

Connect = Callable[[str], Session]
ConnectRaw = Callable[[str | None, str | None], Session]


def test_anonymous_connection_is_refused(connect_raw: ConnectRaw) -> None:
    session = connect_raw(None, None)
    assert session.connect_code in (NOT_AUTHORIZED, BAD_CREDENTIALS)


def test_wrong_password_is_refused(connect_raw: ConnectRaw) -> None:
    session = connect_raw("device-01", "not-the-password")
    assert session.connect_code in (NOT_AUTHORIZED, BAD_CREDENTIALS)


def test_unknown_user_is_refused(connect_raw: ConnectRaw) -> None:
    session = connect_raw("device-99", "anything")
    assert session.connect_code in (NOT_AUTHORIZED, BAD_CREDENTIALS)


def test_valid_credentials_are_accepted(connect: Connect) -> None:
    assert connect("device-01").connect_code == SUCCESS
    assert connect("service").connect_code == SUCCESS


def test_device_telemetry_reaches_the_service(connect: Connect) -> None:
    service = connect("service")
    device = connect("device-01")
    assert service.subscribe("devices/+/telemetry") == [GRANTED_QOS_1]

    assert device.publish("devices/device-01/telemetry", '{"t": 21.5}') == SUCCESS

    message = service.received(DELIVERY_WAIT_SECONDS)
    assert message is not None
    assert message.topic == "devices/device-01/telemetry"
    assert message.payload == '{"t": 21.5}'


def test_device_state_reaches_the_service(connect: Connect) -> None:
    service = connect("service")
    device = connect("device-01")
    service.subscribe("devices/+/state")

    assert device.publish("devices/device-01/state", "on") == SUCCESS
    assert service.received(DELIVERY_WAIT_SECONDS) is not None


def test_device_cannot_publish_another_devices_telemetry(connect: Connect) -> None:
    service = connect("service")
    device = connect("device-01")
    service.subscribe("devices/+/telemetry")

    assert device.publish("devices/device-02/telemetry", '{"t": 99}') == NOT_AUTHORIZED
    assert service.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_device_cannot_publish_commands(connect: Connect) -> None:
    service = connect("service")
    device = connect("device-01")
    service.subscribe("devices/+/commands")

    assert device.publish("devices/device-01/commands", "on") == NOT_AUTHORIZED
    assert service.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_service_command_reaches_only_the_target_device(connect: Connect) -> None:
    service = connect("service")
    target = connect("device-01")
    other = connect("device-02")
    assert target.subscribe("devices/device-01/commands") == [GRANTED_QOS_1]

    assert service.publish("devices/device-01/commands", "relay_on") == SUCCESS

    message = target.received(DELIVERY_WAIT_SECONDS)
    assert message is not None
    assert message.payload == "relay_on"
    assert other.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_device_does_not_receive_another_devices_commands(connect: Connect) -> None:
    service = connect("service")
    snooper = connect("device-01")
    target = connect("device-02")
    snooper.subscribe("devices/device-02/commands")
    target.subscribe("devices/device-02/commands")

    assert service.publish("devices/device-02/commands", "relay_on") == SUCCESS

    assert target.received(DELIVERY_WAIT_SECONDS) is not None
    assert snooper.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_device_does_not_receive_other_devices_telemetry_through_wildcards(
    connect: Connect,
) -> None:
    service = connect("service")
    snooper = connect("device-01")
    publisher = connect("device-02")
    service.subscribe("devices/+/telemetry")
    snooper.subscribe("devices/+/telemetry")
    snooper.subscribe("devices/#")

    assert publisher.publish("devices/device-02/telemetry", '{"t": 30}') == SUCCESS

    assert service.received(DELIVERY_WAIT_SECONDS) is not None
    assert snooper.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_device_does_not_receive_broker_internal_topics(connect: Connect) -> None:
    device = connect("device-01")
    device.subscribe("$SYS/#")
    assert device.received(NO_MESSAGE_WAIT_SECONDS) is None


def test_device_cannot_publish_outside_its_namespace(connect: Connect) -> None:
    device = connect("device-01")
    assert device.publish("anything/else", "x") == NOT_AUTHORIZED


def test_service_cannot_publish_telemetry(connect: Connect) -> None:
    service = connect("service")
    assert service.publish("devices/device-01/telemetry", '{"t": 1}') == NOT_AUTHORIZED
