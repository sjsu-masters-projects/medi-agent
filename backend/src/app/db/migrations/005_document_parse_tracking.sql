-- Add ingestion lifecycle tracking to documents.

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS file_path text,
ADD COLUMN IF NOT EXISTS parse_status text NOT NULL DEFAULT 'none'
    CHECK (parse_status IN ('none', 'pending', 'processing', 'completed', 'failed')),
ADD COLUMN IF NOT EXISTS parse_error text,
ADD COLUMN IF NOT EXISTS parse_attempts integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_documents_parse_status
ON documents (patient_id, parse_status)
WHERE parse_status IN ('pending', 'processing');
