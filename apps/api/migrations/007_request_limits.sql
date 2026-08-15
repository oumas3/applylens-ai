-- ApplyLens AI: persistent fixed-window limits for abuse-sensitive actions.

CREATE TABLE IF NOT EXISTS request_limits (
    limit_key TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    window_started TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS request_limits_window_started_idx
    ON request_limits (window_started);
