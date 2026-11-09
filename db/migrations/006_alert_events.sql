CREATE TABLE alert_events (
    received_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN ('firing', 'resolved')),
    alert_name text NOT NULL,
    device_id text,
    summary text,
    payload jsonb NOT NULL
);

CREATE INDEX alert_events_received_idx ON alert_events (received_at DESC);
