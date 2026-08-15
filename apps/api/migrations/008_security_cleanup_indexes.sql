-- ApplyLens AI: indexes used by opportunistic security-record cleanup.

CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
    ON sessions (expires_at);
