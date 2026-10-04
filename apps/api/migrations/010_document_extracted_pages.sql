-- ApplyLens AI: preserve applicant PDF page provenance for evidence citations.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS extracted_pages JSONB NOT NULL DEFAULT '[]'::JSONB;
