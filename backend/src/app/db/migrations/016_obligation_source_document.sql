-- Track obligations that came from document extraction so deleting a document
-- can remove derived Today-feed tasks without touching manual tasks.

ALTER TABLE obligations
  ADD COLUMN IF NOT EXISTS source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_medications_source_document
  ON medications(source_document_id)
  WHERE source_document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_obligations_source_document
  ON obligations(source_document_id)
  WHERE source_document_id IS NOT NULL;
