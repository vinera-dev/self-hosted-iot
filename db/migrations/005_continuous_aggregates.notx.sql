CREATE MATERIALIZED VIEW readings_5m
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket(INTERVAL '5 minutes', ts) AS bucket,
    device_id,
    avg(temperature_c) AS avg_temperature_c,
    min(temperature_c) AS min_temperature_c,
    max(temperature_c) AS max_temperature_c,
    avg(humidity_pct) AS avg_humidity_pct,
    count(*) AS samples
FROM readings
GROUP BY bucket, device_id
WITH NO DATA;

CREATE MATERIALIZED VIEW readings_1h
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    time_bucket(INTERVAL '1 hour', ts) AS bucket,
    device_id,
    avg(temperature_c) AS avg_temperature_c,
    min(temperature_c) AS min_temperature_c,
    max(temperature_c) AS max_temperature_c,
    avg(humidity_pct) AS avg_humidity_pct,
    count(*) AS samples
FROM readings
GROUP BY bucket, device_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'readings_5m',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes'
);

SELECT add_continuous_aggregate_policy(
    'readings_1h',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes'
);
