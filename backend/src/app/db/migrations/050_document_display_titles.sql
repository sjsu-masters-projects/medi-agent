-- LOC-001: a short, descriptive record title in English and Spanish, drafted from a
-- document's existing summary or candidates. It names the document; it never carries
-- clinical instructions and never replaces the file name, which stays the source identity.
ALTER TABLE public.documents
  ADD COLUMN display_title jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(display_title) = 'object'
      AND (display_title - 'en-US' - 'es-MX') = '{}'::jsonb
      AND COALESCE(jsonb_typeof(display_title->'en-US'), 'string') = 'string'
      AND COALESCE(jsonb_typeof(display_title->'es-MX'), 'string') = 'string'
      AND char_length(COALESCE(display_title->>'en-US', '')) <= 80
      AND char_length(COALESCE(display_title->>'es-MX', '')) <= 80),
  -- Bounded drafting: a document whose title cannot be drafted keeps its file name.
  ADD COLUMN display_title_attempts smallint NOT NULL DEFAULT 0
    CHECK (display_title_attempts BETWEEN 0 AND 10);

-- The worker looks for untitled documents with something to describe.
CREATE INDEX documents_untitled_idx ON public.documents (created_at DESC)
  WHERE display_title = '{}'::jsonb;
