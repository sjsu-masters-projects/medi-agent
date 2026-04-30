-- ============================================================
-- MediAgent — 015 Drug Knowledge RAG
-- Adds pgvector-backed medication knowledge chunks for grounded
-- patient medication education.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS drug_knowledge_chunks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  drug_name     text NOT NULL CHECK (char_length(drug_name) BETWEEN 1 AND 200),
  generic_name  text,
  rxcui         text,
  source        text NOT NULL CHECK (source IN ('dailymed', 'rxnorm', 'curated')),
  source_id     text NOT NULL,
  source_title  text NOT NULL,
  source_url    text,
  section       text NOT NULL CHECK (char_length(section) BETWEEN 1 AND 120),
  chunk_text    text NOT NULL CHECK (char_length(chunk_text) BETWEEN 20 AND 4000),
  chunk_hash    text NOT NULL,
  embedding     vector(768) NOT NULL,
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drug_knowledge_chunks_source_hash
  ON drug_knowledge_chunks(source, source_id, section, chunk_hash);

CREATE INDEX IF NOT EXISTS idx_drug_knowledge_chunks_drug_name
  ON drug_knowledge_chunks(lower(drug_name));

CREATE INDEX IF NOT EXISTS idx_drug_knowledge_chunks_rxcui
  ON drug_knowledge_chunks(rxcui)
  WHERE rxcui IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drug_knowledge_chunks_embedding
  ON drug_knowledge_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE TRIGGER drug_knowledge_chunks_updated_at
  BEFORE UPDATE ON drug_knowledge_chunks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE FUNCTION match_drug_knowledge_chunks(
  query_embedding vector(768),
  p_match_count integer DEFAULT 5,
  p_drug_names text[] DEFAULT NULL,
  p_rxcuis text[] DEFAULT NULL,
  p_min_similarity double precision DEFAULT 0.72
)
RETURNS TABLE (
  id uuid,
  drug_name text,
  generic_name text,
  rxcui text,
  source text,
  source_id text,
  source_title text,
  source_url text,
  section text,
  chunk_text text,
  metadata jsonb,
  similarity double precision
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    dkc.id,
    dkc.drug_name,
    dkc.generic_name,
    dkc.rxcui,
    dkc.source,
    dkc.source_id,
    dkc.source_title,
    dkc.source_url,
    dkc.section,
    dkc.chunk_text,
    dkc.metadata,
    1 - (dkc.embedding <=> query_embedding) AS similarity
  FROM drug_knowledge_chunks dkc
  WHERE
    (
      (p_drug_names IS NULL AND p_rxcuis IS NULL)
      OR lower(dkc.drug_name) = ANY (
        SELECT lower(filter_name.name) FROM unnest(p_drug_names) AS filter_name(name)
      )
      OR lower(COALESCE(dkc.generic_name, '')) = ANY (
        SELECT lower(filter_name.name) FROM unnest(p_drug_names) AS filter_name(name)
      )
      OR dkc.rxcui = ANY (p_rxcuis)
    )
    AND (1 - (dkc.embedding <=> query_embedding)) >= p_min_similarity
  ORDER BY dkc.embedding <=> query_embedding
  LIMIT LEAST(GREATEST(p_match_count, 1), 10);
$$;

ALTER TABLE drug_knowledge_chunks ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'drug_knowledge_chunks'
      AND policyname = 'drug_knowledge_chunks_authenticated_read'
  ) THEN
    CREATE POLICY drug_knowledge_chunks_authenticated_read ON drug_knowledge_chunks
      FOR SELECT TO authenticated USING (true);
  END IF;
END $$;
