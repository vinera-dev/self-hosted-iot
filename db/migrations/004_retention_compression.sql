ALTER TABLE readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('readings', INTERVAL '7 days');
SELECT add_retention_policy('readings', INTERVAL '90 days');
SELECT add_retention_policy('rejected_messages', INTERVAL '30 days');
