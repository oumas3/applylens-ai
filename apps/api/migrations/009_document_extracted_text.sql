-- ApplyLens AI: persist bounded extracted text without retaining source uploads.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS extracted_text TEXT;
