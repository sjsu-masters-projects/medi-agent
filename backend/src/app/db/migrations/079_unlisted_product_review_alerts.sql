-- MED-001: future explicit confirmations only. No historical notification backfill,
-- medication/ADR creation, auth-key change or replacement of clinic authorization.
ALTER TABLE public.notification_events
  DROP CONSTRAINT IF EXISTS notification_events_source_type_check;
ALTER TABLE public.notification_events ADD CONSTRAINT notification_events_source_type_check
  CHECK (source_type IN ('care_conversation_messages','appointments','notifications',
    'care_plan_versions','documents','adherence_logs','adr_assessments',
    'clinician_messages','adr_information_requests','symptom_reports'));

CREATE OR REPLACE FUNCTION private.notification_source(p_type text,p_id uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
  IF p_type NOT IN ('care_conversation_messages','appointments','notifications',
    'care_plan_versions','documents','adherence_logs','adr_assessments','clinician_messages',
    'adr_information_requests','symptom_reports') THEN RETURN NULL; END IF;
  EXECUTE format('SELECT to_jsonb(s) FROM public.%I s WHERE id=$1',p_type) INTO v USING p_id;
  RETURN v;
END;
$$;

-- Source insert and capture commit together. Only the existing confirmed-testimony
-- guard can admit a report; drafts, unknown/declined answers and linked products
-- do not create these review items. The event contains identifiers, not answers.
CREATE OR REPLACE FUNCTION private.capture_unlisted_product_review() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE product jsonb:=NEW.confirmed_content->'answers'->'product';
BEGIN
  IF NEW.confirmation_state='patient_confirmed' AND NEW.related_medication_id IS NULL
    AND product->>'state'='answered' AND product->'value'->'concern'='true'::jsonb
    AND jsonb_typeof(product->'value'->'name')='string'
    AND nullif(btrim(product->'value'->>'name'),'') IS NOT NULL THEN
    PERFORM private.notification_capture('symptom_reports',NEW.id,NEW.patient_id,
      'safety_flag','safety','shared',NULL,'{"review_kind":"unlisted_product"}'::jsonb,
      'unlisted_product:'||NEW.id::text,NEW.created_at);
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS symptom_report_unlisted_product_review ON public.symptom_reports;
CREATE TRIGGER symptom_report_unlisted_product_review AFTER INSERT ON public.symptom_reports
  FOR EACH ROW EXECUTE FUNCTION private.capture_unlisted_product_review();

REVOKE ALL ON FUNCTION private.capture_unlisted_product_review()
  FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION private.notification_source(text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION private.notification_source(text,uuid) TO service_role;

-- Fail closed under hosted default grants. Preserve the notification ledger's RLS
-- and backend-only writes; acknowledging records follow-up, never clinical approval.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN
    ('public.notification_events'::regclass,'public.notification_receipts'::regclass,
     'public.notification_read_audit'::regclass) AND NOT relrowsecurity) THEN
    RAISE EXCEPTION 'Notification ledger must have RLS enabled';
  END IF;
  IF EXISTS (SELECT 1 FROM (VALUES ('anon'),('authenticated')) r(name)
    CROSS JOIN (VALUES ('public.notification_events'),('public.notification_receipts'),
      ('public.notification_read_audit')) t(name)
    WHERE has_table_privilege(r.name,t.name,'INSERT,UPDATE,DELETE')
      OR has_function_privilege(r.name,'private.notification_source(text,uuid)','EXECUTE')
      OR has_function_privilege(r.name,'private.capture_unlisted_product_review()','EXECUTE')) THEN
    RAISE EXCEPTION 'Notification capture must not be accessible to browser roles';
  END IF;
END;
$$;
