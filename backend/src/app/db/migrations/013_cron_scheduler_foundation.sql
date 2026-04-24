-- ============================================================
-- MediAgent — 013 Cron Scheduler Foundation
-- Adds idempotent reminder metadata and cron job run tracking.
-- ============================================================

ALTER TABLE notifications
  ADD COLUMN IF NOT EXISTS dedupe_key text;

ALTER TABLE notifications
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe_key
  ON notifications(dedupe_key)
  WHERE dedupe_key IS NOT NULL;


CREATE TABLE IF NOT EXISTS cron_job_runs (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_name     text NOT NULL CHECK (char_length(job_name) BETWEEN 1 AND 100),
  status       text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  triggered_by text NOT NULL DEFAULT 'scheduler',
  metadata     jsonb NOT NULL DEFAULT '{}'::jsonb,
  summary      jsonb NOT NULL DEFAULT '{}'::jsonb,
  error        text,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz
);

CREATE INDEX IF NOT EXISTS idx_cron_job_runs_job_started
  ON cron_job_runs(job_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_cron_job_runs_running
  ON cron_job_runs(job_name, status)
  WHERE status = 'running';
