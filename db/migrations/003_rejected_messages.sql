CREATE TABLE rejected_messages (
    received_at timestamptz NOT NULL DEFAULT now(),
    topic text NOT NULL,
    payload text NOT NULL,
    reason text NOT NULL
);

SELECT create_hypertable('rejected_messages', 'received_at', chunk_time_interval => INTERVAL '7 days');

CREATE INDEX rejected_messages_topic_idx ON rejected_messages (topic, received_at DESC);
