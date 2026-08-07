-- ApplyLens AI: persistent application data and authentication.
-- Requires PostgreSQL 16+ (the development compose service uses pgvector/pg16).

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    category TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    extracted_text_length INTEGER NOT NULL DEFAULT 0,
    uploaded_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_user_id_idx ON documents(user_id);

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_text TEXT NOT NULL,
    institution TEXT,
    degree_type TEXT,
    source_name TEXT,
    source_url TEXT,
    requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    requirement_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    deadline TEXT,
    deadline_date DATE,
    funding TEXT
);

CREATE INDEX IF NOT EXISTS opportunities_user_id_idx ON opportunities(user_id);
CREATE INDEX IF NOT EXISTS opportunities_deadline_date_idx ON opportunities(deadline_date);

CREATE TABLE IF NOT EXISTS reviews (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    title TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    matched_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    deadline TEXT,
    funding TEXT,
    PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS reviews_user_id_idx ON reviews(user_id);

CREATE TABLE IF NOT EXISTS tasks (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    id BIGINT NOT NULL,
    opportunity_id TEXT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS tasks_user_id_idx ON tasks(user_id);
CREATE INDEX IF NOT EXISTS tasks_opportunity_idx ON tasks(user_id, opportunity_id);
