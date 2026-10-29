-- Presentation only: no source rewrite, review decision or clinical truth change.
-- Each document retains at most one current presentation per supported locale.
CREATE TABLE public.document_explanation_presentations (
  document_id uuid NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  language text NOT NULL CHECK (language IN ('en-US', 'es-MX')),
  source_hash text NOT NULL CHECK (source_hash ~ '^[a-f0-9]{64}$'),
  presentation_version integer NOT NULL CHECK (presentation_version > 0),
  payload jsonb NOT NULL CHECK (
    jsonb_typeof(payload) = 'object'
    AND (payload->>'language') IS NOT DISTINCT FROM language
    AND octet_length(payload::text) <= 131072
  ),
  generated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, language)
);
ALTER TABLE public.document_explanation_presentations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.document_explanation_presentations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_explanation_presentations TO service_role;
