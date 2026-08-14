-- ApplyLens AI: one structured, evidence-linked candidate profile per user.

CREATE TABLE IF NOT EXISTS candidate_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    full_name TEXT,
    headline TEXT,
    location TEXT,
    summary TEXT,
    education JSONB NOT NULL DEFAULT '[]'::jsonb,
    work_experience JSONB NOT NULL DEFAULT '[]'::jsonb,
    research_experience JSONB NOT NULL DEFAULT '[]'::jsonb,
    languages JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    publications JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS candidate_profiles_updated_at_idx
    ON candidate_profiles (updated_at);
