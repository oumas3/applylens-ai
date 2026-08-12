-- ApplyLens AI: explicit account-level consent for external AI processing.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS external_ai_consent BOOLEAN NOT NULL DEFAULT FALSE;
