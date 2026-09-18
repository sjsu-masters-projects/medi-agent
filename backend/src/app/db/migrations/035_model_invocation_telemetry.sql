-- Record what every model call actually cost and how it ended.
--
-- Today this is measured only by the offline evaluation harness, and discarded entirely
-- in production: `ModelRouter.generate_text` returns `response.text` and drops the
-- `GenerationTelemetry` beside it. So nothing answers the questions that decide whether
-- the routing table is still correct — which workload is slow, which model is being
-- fallen back to, how often an answer is truncated, and what any of it costs. Those are
-- exactly the figures the routing decision was made on, and after deployment we stopped
-- collecting them.
--
-- Truncation is the one worth naming. `finish_reason = 'MAX_TOKENS'` means a budget we
-- chose cut an answer off. The client now regenerates once at a larger budget, but if
-- that is happening routinely the per-workload budgets in `app/adk/registry.py` are
-- wrong, and without this table that is invisible.
--
-- **No patient data, ever.** No `patient_id`, no prompt, no response text, no tool
-- arguments. This table is about the model and the budget, and it is read for operations
-- rather than care, so a row here must never become another place a record leaks from.
-- `workload` is the routing key, not the subject of the request.

CREATE TABLE IF NOT EXISTS model_invocation_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Routing: which workload asked, and what answered it.
  workload text NOT NULL CHECK (char_length(workload) BETWEEN 1 AND 60),
  provider text NOT NULL CHECK (char_length(provider) BETWEEN 1 AND 60),
  model text NOT NULL CHECK (char_length(model) BETWEEN 1 AND 120),

  -- Outcome. `finish_reason` is the provider's own word, kept verbatim; inferring
  -- truncation from unparseable output charges a budget we set to the model as though it
  -- were a content mistake.
  succeeded boolean NOT NULL,
  finish_reason text CHECK (finish_reason IS NULL OR char_length(finish_reason) BETWEEN 1 AND 40),
  error_code text CHECK (error_code IS NULL OR char_length(error_code) BETWEEN 1 AND 40),

  -- Cost and latency. Thought tokens are billed inside the completion total, so a
  -- reasoning model given the same budget as a plain one has less of it for the answer;
  -- `reasoning_tokens` is recorded separately so that is visible rather than inferred.
  latency_ms integer NOT NULL CHECK (latency_ms >= 0),
  input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
  reasoning_tokens integer CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0),

  -- Resilience. `retries` counts attempts beyond the first; latency already includes the
  -- waits, so a retried call is slow in the numbers the way it was slow for the person.
  -- `fallback_path` records which providers were tried and in what order.
  retries integer NOT NULL DEFAULT 0 CHECK (retries >= 0),
  fallback_path text[] NOT NULL DEFAULT '{}',

  created_at timestamptz NOT NULL DEFAULT now()
);

-- "Is this workload still inside its latency budget, and what is it costing?"
CREATE INDEX IF NOT EXISTS idx_model_invocation_events_workload
  ON model_invocation_events(workload, created_at DESC);
-- "Which model served this, and did a retirement or a swap change the numbers?"
CREATE INDEX IF NOT EXISTS idx_model_invocation_events_model
  ON model_invocation_events(model, created_at DESC);
-- "How often are we truncating or failing?" — the alerting read, and the reason the
-- partial index exists: healthy calls are the overwhelming majority and indexing them
-- here would cost write throughput for a query that never wants them.
CREATE INDEX IF NOT EXISTS idx_model_invocation_events_unhealthy
  ON model_invocation_events(finish_reason, created_at DESC)
  WHERE succeeded = false OR finish_reason = 'MAX_TOKENS';

-- Server-only, matching `authorization_denial_events`. RLS is enabled with no policy, so
-- `anon` and `authenticated` reach no row even if a grant is added later by mistake, and
-- the table is append-only for the trusted backend: no UPDATE or DELETE grant is issued
-- to any role. Telemetry that can be edited after the fact is not telemetry.
ALTER TABLE model_invocation_events ENABLE ROW LEVEL SECURITY;

GRANT INSERT, SELECT ON TABLE public.model_invocation_events TO service_role;
