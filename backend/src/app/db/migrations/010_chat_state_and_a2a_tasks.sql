-- Add persistent chat conversation state and A2A task lifecycle tracking.

-- ── chat_conversation_states ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS chat_conversation_states (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id       uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  session_id       text NOT NULL DEFAULT 'default',
  language         language_enum NOT NULL DEFAULT 'en-US',
  status           text NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'closed', 'archived')),
  turn_count       integer NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
  last_intent      text NOT NULL DEFAULT 'general',
  last_urgency     text NOT NULL DEFAULT 'routine',
  last_route       text NOT NULL DEFAULT 'triage',
  summary          text NOT NULL DEFAULT '',
  state_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
  document_context jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),

  UNIQUE (patient_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_state_patient_updated
  ON chat_conversation_states(patient_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_state_status
  ON chat_conversation_states(status);

CREATE TRIGGER chat_conversation_states_updated_at
  BEFORE UPDATE ON chat_conversation_states
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── a2a_tasks ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS a2a_tasks (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id               uuid NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  symptom_event_id         uuid REFERENCES symptom_reports(id) ON DELETE SET NULL,
  idempotency_key          text NOT NULL,
  conversation_session_id  text NOT NULL DEFAULT 'default',
  source_agent             text NOT NULL,
  target_agent             text NOT NULL,
  task_type                text NOT NULL,
  status                   text NOT NULL DEFAULT 'submitted'
                           CHECK (
                             status IN (
                               'submitted',
                               'working',
                               'retrying',
                               'completed',
                               'failed',
                               'dead_letter'
                             )
                           ),
  input_payload            jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_payload           jsonb,
  worker_payload           jsonb,
  error_message            text,
  retry_attempt            integer NOT NULL DEFAULT 0 CHECK (retry_attempt >= 0),
  max_retries              integer NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
  next_retry_at            timestamptz,
  dead_lettered_at         timestamptz,
  created_at               timestamptz NOT NULL DEFAULT now(),
  started_at               timestamptz,
  completed_at             timestamptz,
  updated_at               timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE a2a_tasks
  ADD COLUMN IF NOT EXISTS symptom_event_id uuid REFERENCES symptom_reports(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS idempotency_key text,
  ADD COLUMN IF NOT EXISTS retry_attempt integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_retries integer NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS next_retry_at timestamptz,
  ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;

ALTER TABLE a2a_tasks
  DROP CONSTRAINT IF EXISTS a2a_tasks_status_check;

ALTER TABLE a2a_tasks
  ADD CONSTRAINT a2a_tasks_status_check
  CHECK (
    status IN ('submitted', 'working', 'retrying', 'completed', 'failed', 'dead_letter')
  );

UPDATE a2a_tasks
SET idempotency_key = 'legacy:' || id::text
WHERE idempotency_key IS NULL;

ALTER TABLE a2a_tasks
  ALTER COLUMN idempotency_key SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_patient_status
  ON a2a_tasks(patient_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_target_status
  ON a2a_tasks(target_agent, status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_a2a_tasks_patient_idempotency
  ON a2a_tasks(patient_id, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_patient_session
  ON a2a_tasks(patient_id, conversation_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_next_retry
  ON a2a_tasks(status, next_retry_at)
  WHERE status = 'retrying';

CREATE TRIGGER a2a_tasks_updated_at
  BEFORE UPDATE ON a2a_tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ── RLS ───────────────────────────────────────────────────────────────────

ALTER TABLE chat_conversation_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE a2a_tasks ENABLE ROW LEVEL SECURITY;

-- Chat conversation state access
CREATE POLICY conv_state_patient_select ON chat_conversation_states
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY conv_state_patient_insert ON chat_conversation_states
  FOR INSERT WITH CHECK (patient_id = auth.uid());

CREATE POLICY conv_state_patient_update ON chat_conversation_states
  FOR UPDATE USING (patient_id = auth.uid());

CREATE POLICY conv_state_clinician_select ON chat_conversation_states
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

-- A2A task lifecycle visibility
CREATE POLICY a2a_tasks_patient_select ON a2a_tasks
  FOR SELECT USING (patient_id = auth.uid());

CREATE POLICY a2a_tasks_patient_insert ON a2a_tasks
  FOR INSERT WITH CHECK (patient_id = auth.uid());

CREATE POLICY a2a_tasks_clinician_select ON a2a_tasks
  FOR SELECT USING (is_clinician() AND is_assigned_clinician(patient_id));

CREATE POLICY a2a_tasks_clinician_insert ON a2a_tasks
  FOR INSERT WITH CHECK (is_clinician() AND is_assigned_clinician(patient_id));
