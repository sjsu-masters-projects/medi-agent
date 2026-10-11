-- NORA-002: cached public reference text for Nora, and separate chat conversations.
--
-- health_knowledge holds plain-language summaries (MedlinePlus) and label sections
-- (DailyMed) for a medication or condition, with the source's own version and date. It is
-- public reference text, never patient data, and is refreshed weekly. Reads and writes go
-- through the API's service role only.
CREATE TABLE public.health_knowledge (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_type      text NOT NULL CHECK (subject_type IN ('medication', 'condition')),
  -- The RxNorm ingredient RxCUI for a medication; a lower-cased name for a condition.
  subject_key       text NOT NULL CHECK (char_length(subject_key) BETWEEN 1 AND 200),
  subject_name      text NOT NULL CHECK (char_length(subject_name) BETWEEN 1 AND 200),
  source            text NOT NULL CHECK (source IN ('medlineplus', 'dailymed')),
  locale            text NOT NULL CHECK (locale IN ('en-US', 'es-MX')),
  -- 'not_found' is cached too, so a miss is not re-fetched on every message.
  status            text NOT NULL CHECK (status IN ('found', 'not_found')),
  title             text NOT NULL DEFAULT '' CHECK (char_length(title) <= 300),
  url               text CHECK (url IS NULL OR url ~ '^https://'),
  summary           text NOT NULL DEFAULT '' CHECK (char_length(summary) <= 6000),
  sections          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(sections) = 'object'),
  source_version    text CHECK (source_version IS NULL OR char_length(source_version) <= 80),
  source_updated_on date,
  content_hash      text NOT NULL DEFAULT '',
  fetched_at        timestamptz NOT NULL DEFAULT now(),
  checked_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (subject_type, subject_key, source, locale)
);

CREATE INDEX health_knowledge_checked_idx ON public.health_knowledge (checked_at);

-- A medication name as written ("Metformina 500 mg") resolved to its RxNorm ingredient,
-- so a repeat question needs no RxNorm call. An unresolved name has a NULL rxcui.
CREATE TABLE public.medication_name_resolutions (
  name_key     text PRIMARY KEY CHECK (char_length(name_key) BETWEEN 1 AND 200),
  rxcui        text CHECK (rxcui IS NULL OR rxcui ~ '^[0-9]{1,12}$'),
  ingredient   text CHECK (ingredient IS NULL OR char_length(ingredient) <= 200),
  resolved_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.health_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.medication_name_resolutions ENABLE ROW LEVEL SECURITY;
-- No browser policy or grant: both portals reach this through the API.
REVOKE ALL ON public.health_knowledge, public.medication_name_resolutions
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON public.health_knowledge, public.medication_name_resolutions
  TO service_role;

-- Conversations: every message belongs to one. Existing messages stay in 'default',
-- which the patient app lists as an earlier conversation.
ALTER TABLE public.chat_messages
  ADD COLUMN session_id text NOT NULL DEFAULT 'default'
    CHECK (char_length(session_id) BETWEEN 1 AND 120);

CREATE INDEX idx_chat_patient_session
  ON public.chat_messages (patient_id, session_id, created_at DESC);

-- A short label for the conversation list, taken from the patient's first message.
ALTER TABLE public.chat_conversation_states
  ADD COLUMN title text NOT NULL DEFAULT '' CHECK (char_length(title) <= 120);
