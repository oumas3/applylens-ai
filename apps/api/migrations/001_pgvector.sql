-- ApplyLens AI: persistent opportunity evidence vectors.
-- Requires PostgreSQL with the pgvector extension installed.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS opportunity_chunks (
    opportunity_id TEXT NOT NULL,
    chunk_id TEXT PRIMARY KEY,
    chunk_text TEXT NOT NULL,
    source_name TEXT,
    page INTEGER,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS opportunity_chunks_opportunity_idx
    ON opportunity_chunks (opportunity_id);

CREATE INDEX IF NOT EXISTS opportunity_chunks_embedding_hnsw_idx
    ON opportunity_chunks
    USING hnsw (embedding vector_cosine_ops);
