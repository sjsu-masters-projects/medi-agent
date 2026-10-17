-- LOC-003: Store one translation per care-team message. The original stays the
-- message of record; translations are for display convenience only. Safety
-- checks and escalation use only the original text.

CREATE TABLE IF NOT EXISTS public.message_translations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- The source message. For care_team_conversation_messages the ID is inside the
  -- RPC result; for chat_messages it is the chat_messages.id row.
  source_table text NOT NULL CHECK (source_table IN ('care_team_conversation_messages', 'chat_messages')),
  source_message_id uuid NOT NULL,
  -- What was translated and into which language.
  source_locale text NOT NULL CHECK (source_locale IN ('en-US', 'es-MX')),
  target_locale text NOT NULL CHECK (target_locale IN ('en-US', 'es-MX')),
  translated_text text NOT NULL CHECK (char_length(translated_text) BETWEEN 1 AND 8000),
  -- LOC-001 guard outcome: did numbers/doses/names survive the translation?
  guard_passed boolean NOT NULL DEFAULT true,
  guard_failure_code text,
  -- Provenance
  model_id text,
  translated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  -- One translation per message per target language.
  UNIQUE (source_table, source_message_id, target_locale)
);

CREATE INDEX IF NOT EXISTS message_translations_source
  ON public.message_translations(source_table, source_message_id);

COMMENT ON TABLE public.message_translations IS
  'LOC-003: stored translations for care-team and chat messages. '
  'The original text is always the message of record. '
  'Safety checks use only the original, never a translation.';

-- Backend-only: the service reads and writes translations; browser roles get nothing.
-- Idempotent because some environments created this table under its earlier filename.
ALTER TABLE public.message_translations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.message_translations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.message_translations TO service_role;

DO $$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class
           WHERE oid = 'public.message_translations'::regclass) THEN
    RAISE EXCEPTION 'message_translations must have row level security enabled';
  END IF;
  IF has_table_privilege('anon', 'public.message_translations', 'SELECT')
     OR has_table_privilege('authenticated', 'public.message_translations', 'SELECT')
     OR has_table_privilege('authenticated', 'public.message_translations', 'INSERT') THEN
    RAISE EXCEPTION 'Browser roles must not access message_translations';
  END IF;
END $$;
