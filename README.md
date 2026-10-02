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

## Roadmap

- [ ] 1. Compose skeleton with an authenticated Mosquitto broker
- [ ] 2. Device simulator
- [ ] 3. TimescaleDB storage and Node-RED ingestion flow
- [ ] 4. Grafana dashboards provisioned as code
- [ ] 5. Alert rules and commands back to devices
- [ ] 6. Nginx with TLS, backups and documentation

## License

Released under the [MIT License](LICENSE).
