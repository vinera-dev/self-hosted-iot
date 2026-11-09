CREATE TABLE readings (
    ts timestamptz NOT NULL,
    device_id text NOT NULL,
    temperature_c double precision NOT NULL,
    humidity_pct double precision NOT NULL,
    CONSTRAINT readings_temperature_range CHECK (temperature_c BETWEEN -50 AND 100),
    CONSTRAINT readings_humidity_range CHECK (humidity_pct BETWEEN 0 AND 100)
);

SELECT create_hypertable('readings', 'ts', chunk_time_interval => INTERVAL '1 day');

CREATE UNIQUE INDEX readings_device_ts_key ON readings (device_id, ts DESC);

CREATE TABLE device_states (
    device_id text PRIMARY KEY,
    relay text NOT NULL CHECK (relay IN ('on', 'off')),
    updated_at timestamptz NOT NULL
);
