-- Phase 6.6: Enable Supabase Realtime publication for clinician dashboard tables.
--
-- This migration is idempotent:
-- - skips gracefully if publication does not exist
-- - adds each table only when missing from the publication

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication
    WHERE pubname = 'supabase_realtime'
  ) THEN
    RAISE NOTICE 'Publication supabase_realtime not found; skipping realtime publication changes.';
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication p
    JOIN pg_publication_rel pr ON pr.prpubid = p.oid
    JOIN pg_class c ON c.oid = pr.prrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE p.pubname = 'supabase_realtime'
      AND n.nspname = 'public'
      AND c.relname = 'adherence_logs'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.adherence_logs;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication p
    JOIN pg_publication_rel pr ON pr.prpubid = p.oid
    JOIN pg_class c ON c.oid = pr.prrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE p.pubname = 'supabase_realtime'
      AND n.nspname = 'public'
      AND c.relname = 'symptom_reports'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.symptom_reports;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_publication p
    JOIN pg_publication_rel pr ON pr.prpubid = p.oid
    JOIN pg_class c ON c.oid = pr.prrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE p.pubname = 'supabase_realtime'
      AND n.nspname = 'public'
      AND c.relname = 'adr_assessments'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.adr_assessments;
  END IF;
END;
$$;
