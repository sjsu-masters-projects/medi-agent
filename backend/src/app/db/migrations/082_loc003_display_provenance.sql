-- LOC-003 items 2 and 5: say where translated display text came from, and store the
-- English gloss of Spanish source evidence.
--
-- Two small changes, both additive and re-runnable:
--
-- 1. clinical_facts.display_model_id — the model that produced a fact's English display
--    fields. Without it the review screen can show the "may contain errors" caveat but not
--    what produced the text, which is the part a reviewer actually needs later.
--
-- 2. message_translations accepts 'evidence_excerpt' as a source_table. Source evidence is
--    never rewritten: an excerpt stays the exact printed Spanish, and the English gloss sits
--    beside it. A gloss is the same kind of record this table already holds — translated
--    text with its guard outcome and the model that produced it — so it is stored here
--    rather than in a second table with the same columns. Excerpt glosses are addressed by
--    a UUIDv5 of the excerpt text, so the same printed sentence is glossed once however
--    many citations quote it, and the retention sweep (080) leaves them alone because it
--    only looks for orphans under the two message labels.

ALTER TABLE public.clinical_facts
  ADD COLUMN IF NOT EXISTS display_model_id text
    CHECK (display_model_id IS NULL OR char_length(display_model_id) <= 200);

COMMENT ON COLUMN public.clinical_facts.display_model_id IS
  'LOC-003 item 5: the model that produced display_value. Shown with the translated fact '
  'so machine wording is never read as the printed source.';

-- Widen the source_table check in place. The constraint name comes from 068, where the
-- column carried an inline CHECK, so it is found rather than assumed.
DO $$
DECLARE
  existing text;
BEGIN
  SELECT conname INTO existing
  FROM pg_catalog.pg_constraint
  WHERE conrelid = 'public.message_translations'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%source_table%'
    AND pg_get_constraintdef(oid) NOT LIKE '%evidence_excerpt%';
  IF existing IS NOT NULL THEN
    EXECUTE format('ALTER TABLE public.message_translations DROP CONSTRAINT %I', existing);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public.message_translations'::regclass
      AND conname = 'message_translations_source_table_check'
  ) THEN
    ALTER TABLE public.message_translations
      ADD CONSTRAINT message_translations_source_table_check
      CHECK (source_table IN (
        'care_team_conversation_messages',
        'chat_messages',
        'evidence_excerpt'
      ));
  END IF;
END $$;

COMMENT ON COLUMN public.message_translations.source_table IS
  'What the stored translation belongs to: a care-team message, a Nora chat message, or '
  '(LOC-003 item 2) a piece of Spanish source evidence, addressed by a UUIDv5 of its text. '
  'The original is always the record; a translation is a reading aid.';

-- Fail closed: both changes must be in place, and the widened check must still reject
-- anything else, so a typo cannot quietly become a new kind of stored translation.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_attribute
    WHERE attrelid = 'public.clinical_facts'::regclass
      AND attname = 'display_model_id' AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'clinical_facts.display_model_id must exist';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public.message_translations'::regclass
      AND conname = 'message_translations_source_table_check'
      AND pg_get_constraintdef(oid) LIKE '%evidence_excerpt%'
  ) THEN
    RAISE EXCEPTION 'message_translations must accept evidence_excerpt as a source_table';
  END IF;
END $$;
