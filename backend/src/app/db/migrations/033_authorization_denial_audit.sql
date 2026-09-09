-- Record every refused access attempt.
--
-- Enforcement already denies these requests; without a record the denial cannot be
-- counted, alerted on, or investigated, so an attacker may probe care-team boundaries
-- indefinitely and leave no trace. `negative_access_cases` in the canonical synthetic
-- fixture declares expected_audit_entry = true for all eight cases; this table is where
-- those entries land.
--
-- Actor and target are stored as plain uuid rather than foreign keys on purpose: a
-- denial is often an attempt against an identifier that does not exist, or by an actor
-- whose profile row is not visible from the denial path. A reference would drop exactly
-- the probe attempts most worth keeping.

CREATE TABLE IF NOT EXISTS authorization_denial_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reason_code text NOT NULL CHECK (char_length(reason_code) BETWEEN 1 AND 100),
  actor_id uuid,
  actor_role text CHECK (actor_role IS NULL OR char_length(actor_role) BETWEEN 1 AND 50),
  target_type text CHECK (target_type IS NULL OR char_length(target_type) BETWEEN 1 AND 50),
  target_id uuid,
  request_method text CHECK (request_method IS NULL OR char_length(request_method) BETWEEN 1 AND 10),
  request_path text CHECK (request_path IS NULL OR char_length(request_path) BETWEEN 1 AND 2000),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Investigation reads: "what did this actor try", and "who tried to reach this record".
CREATE INDEX IF NOT EXISTS idx_authorization_denial_events_actor
  ON authorization_denial_events(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_authorization_denial_events_target
  ON authorization_denial_events(target_type, target_id, created_at DESC);
-- Alerting reads: recent denials by classification.
CREATE INDEX IF NOT EXISTS idx_authorization_denial_events_reason
  ON authorization_denial_events(reason_code, created_at DESC);

-- Server-only. RLS is enabled with no policy, so `anon` and `authenticated` can reach
-- no row even if a grant is added later by mistake. The table is append-only for the
-- trusted backend: no UPDATE or DELETE grant is issued to any role.
ALTER TABLE authorization_denial_events ENABLE ROW LEVEL SECURITY;

GRANT INSERT, SELECT ON TABLE public.authorization_denial_events TO service_role;
