-- ============================================================
-- MediAgent — 011 Locale Contract Upgrade
-- Canonicalizes locale values to BCP 47 tags for persisted language fields.
-- ============================================================

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE t.typname = 'language_enum' AND e.enumlabel = 'en'
  ) THEN
    ALTER TYPE language_enum RENAME VALUE 'en' TO 'en-US';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_enum e ON e.enumtypid = t.oid
    WHERE t.typname = 'language_enum' AND e.enumlabel = 'es'
  ) THEN
    ALTER TYPE language_enum RENAME VALUE 'es' TO 'es-MX';
  END IF;
END $$;

ALTER TABLE patients
  ALTER COLUMN preferred_language SET DEFAULT 'en-US';

ALTER TABLE chat_messages
  ALTER COLUMN language SET DEFAULT 'en-US';

ALTER TABLE chat_conversation_states
  ALTER COLUMN language SET DEFAULT 'en-US';
