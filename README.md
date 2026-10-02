# self-hosted-iot

A self-hosted IoT platform that runs entirely on your own hardware with Docker Compose: MQTT messaging, rule-based automation, time-series storage and dashboards, without any commercial IoT cloud.

> **Status:** planned, not started. This README describes the intended scope.

## Purpose

Show how to build and operate an IoT backend on-premises, from device messaging to dashboards, on low-cost hardware such as a Raspberry Pi. A device simulator is included so the whole stack can be developed and tested without physical devices. All data is generated.

## Planned architecture

```
devices / simulator ──MQTT──► Mosquitto ──► Node-RED ──► TimescaleDB ──► Grafana
                                               │
                                               └──► alerts and commands back to devices
```

## Planned scope

- Eclipse Mosquitto broker with authentication, access control lists and TLS
- Python device simulator publishing telemetry (temperature, humidity and others) and reacting to commands
- Node-RED flows for ingestion, validation, rules and alerts (for example, switch a relay when a threshold is crossed)
- PostgreSQL with TimescaleDB for time-series storage, with retention and continuous aggregates
- Grafana dashboards and data sources provisioned as code
- Nginx reverse proxy with TLS in front of the web interfaces
- Backup and restore scripts, and a Compose setup that runs on both ARM64 and x86
- CI that validates the Compose configuration and the flows

## Planned stack

Docker Compose, Eclipse Mosquitto, Node-RED, PostgreSQL with TimescaleDB, Grafana, Nginx, Python, GitHub Actions.

## Running the broker locally

```bash
cp .env.example .env
docker compose up -d --wait
bash scripts/create-mqtt-users.sh device-01 device-02
docker compose restart mosquitto
```

The broker listens on `127.0.0.1:11883` (set `MQTT_PORT` to change it). The script creates the `service` user and one user per device with random passwords, writes the hashed password file used by Mosquitto, and saves the plain credentials to `.secrets/mqtt-credentials.env`. Both are ignored by git.

### Access model

Anonymous access is disabled. Topic permissions live in `mosquitto/config/acl`:

| User | Can publish | Can read |
|---|---|---|
| `device-NN` | `devices/device-NN/telemetry`, `devices/device-NN/state` | `devices/device-NN/commands` |
| `service` | `devices/+/commands` | `devices/+/telemetry`, `devices/+/state` |

Mosquitto's built-in ACL does not reject a subscription to a topic the client cannot read: the subscription is acknowledged, and the read permission is enforced when messages are delivered. The tests therefore check that nothing is delivered, with a positive control, rather than expecting a rejected subscription.

### Tests

```bash
python -m venv .venv
pip install -r requirements-dev.txt
pytest
```

The tests connect to the running broker with MQTT 5 and cover authentication and the ACL. They are skipped with an explanatory message when the broker or the credentials are not available.

## Roadmap

- [x] 1. Compose skeleton with an authenticated Mosquitto broker
- [ ] 2. Device simulator
- [ ] 3. TimescaleDB storage and Node-RED ingestion flow
- [ ] 4. Grafana dashboards provisioned as code
- [ ] 5. Alert rules and commands back to devices
- [ ] 6. Nginx with TLS, backups and documentation

## License

Released under the [MIT License](LICENSE).
