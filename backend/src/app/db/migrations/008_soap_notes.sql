-- Migration 008: Create soap_notes table
-- Phase 6.3 — Summarization Agent stores AI-generated SOAP notes here
-- Run this in Supabase SQL Editor before enabling the /soap-note endpoint

-- ── soap_notes table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS soap_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id      UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    clinician_id    UUID NOT NULL REFERENCES clinicians(id) ON DELETE CASCADE,
    subjective      TEXT NOT NULL DEFAULT '',
    objective       TEXT NOT NULL DEFAULT '',
    assessment      TEXT NOT NULL DEFAULT '',
    plan            TEXT NOT NULL DEFAULT '',
    model_used      TEXT NOT NULL DEFAULT 'gemini-3.1-pro-preview',
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by patient (most common query)
CREATE INDEX IF NOT EXISTS idx_soap_notes_patient_id
    ON soap_notes (patient_id, generated_at DESC);

-- ── RLS policies ─────────────────────────────────────────────────────────────
ALTER TABLE soap_notes ENABLE ROW LEVEL SECURITY;

-- Clinicians can only read SOAP notes for patients they are assigned to
CREATE POLICY "clinicians_read_own_soap_notes" ON soap_notes
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM care_teams ct
            WHERE ct.patient_id = soap_notes.patient_id
              AND ct.clinician_id = auth.uid()
              AND ct.status = 'active'
        )
    );

-- Only the backend service role can insert/update (agents run with service key)
CREATE POLICY "service_role_manage_soap_notes" ON soap_notes
    FOR ALL
    USING (auth.role() = 'service_role');

-- ── Columns added to documents table for Phase 6 ────────────────────────────
-- Add clinician_annotation column if not already present
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS clinician_annotation TEXT,
    ADD COLUMN IF NOT EXISTS annotation_by UUID REFERENCES clinicians(id);

-- ── Enable Realtime for dashboard live updates ───────────────────────────────
-- Run these manually in Supabase Dashboard → Database → Replication:
--   Enable Publication for: adherence_logs, symptom_reports, adr_assessments
-- Or run this SQL (requires superuser):
-- ALTER PUBLICATION supabase_realtime ADD TABLE adherence_logs;
-- ALTER PUBLICATION supabase_realtime ADD TABLE symptom_reports;
-- ALTER PUBLICATION supabase_realtime ADD TABLE adr_assessments;

COMMENT ON TABLE soap_notes IS 'AI-generated SOAP notes — created by Summarization Agent (Gemini 3.1 Pro). One row per note generation; multiple notes per patient are kept for history.';
