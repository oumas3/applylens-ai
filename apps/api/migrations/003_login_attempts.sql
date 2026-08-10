-- ApplyLens AI: persistent authentication throttling.

CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_key TEXT PRIMARY KEY,
    failed_attempts INTEGER NOT NULL CHECK (failed_attempts >= 0),
    window_started TIMESTAMPTZ NOT NULL,
    blocked_until TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS login_attempts_blocked_until_idx
    ON login_attempts (blocked_until);

CREATE INDEX IF NOT EXISTS login_attempts_window_started_idx
    ON login_attempts (window_started);
