-- LOC-003 items 8 and 11: cache the back-translation a clinician verifies against, and
-- record which deterministic guards passed at the moment the wording was marked verified.
--
-- Both columns live on care_plan_items, which already has row level security and the
-- grants the plan tables share, so no new table or grant is introduced here.

ALTER TABLE public.care_plan_items
  ADD COLUMN IF NOT EXISTS back_translation jsonb
    CHECK (back_translation IS NULL OR jsonb_typeof(back_translation) = 'object'),
  ADD COLUMN IF NOT EXISTS wording_verification jsonb
    CHECK (wording_verification IS NULL OR jsonb_typeof(wording_verification) = 'object'),
  ADD COLUMN IF NOT EXISTS translation_model_id text
    CHECK (translation_model_id IS NULL OR char_length(translation_model_id) <= 200);

COMMENT ON COLUMN public.care_plan_items.back_translation IS
  'LOC-003 item 8: cached English back-translation of the Spanish wording, with the '
  'guard results, the model that produced it and a fingerprint of the Spanish it covers. '
  'Serving it only while the fingerprint matches the stored Spanish keeps a stale '
  'back-translation from ever standing in for wording that has since changed.';

COMMENT ON COLUMN public.care_plan_items.wording_verification IS
  'LOC-003 item 11: the deterministic guard outcome recorded with wording_verified — '
  'which checks ran (numbers with units, negation, medication name, field presence), '
  'whether they passed, the fingerprints of the wording checked, and when. Display and '
  'audit only: publication re-runs the guards and never trusts this record.';

COMMENT ON COLUMN public.care_plan_items.translation_model_id IS
  'LOC-003 item 5: the model that drafted the second language, shown to the clinician '
  'beside the translated wording so machine wording is never read as reviewed wording.';

-- A NOT VALID CHECK still rejects cache-only updates to old verified rows.
-- Require records for new/changed verification, retaining unchanged legacy approvals.
ALTER TABLE public.care_plan_items
  DROP CONSTRAINT IF EXISTS care_plan_items_wording_verification_present;
CREATE OR REPLACE FUNCTION private.require_wording_verification_record()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.wording_verified AND NEW.wording_verification IS NULL THEN
    IF TG_OP='INSERT' THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='Verified wording requires a verification record', CONSTRAINT='care_plan_items_wording_verification_present';
    ELSIF ROW(NEW.wording,NEW.wording_verified,NEW.wording_verification) IS DISTINCT FROM
          ROW(OLD.wording,OLD.wording_verified,OLD.wording_verification) THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='Verified wording requires a verification record', CONSTRAINT='care_plan_items_wording_verification_present';
    END IF;
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.require_wording_verification_record() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS care_plan_items_wording_verification_present ON public.care_plan_items;
CREATE TRIGGER care_plan_items_wording_verification_present
  BEFORE INSERT OR UPDATE ON public.care_plan_items
  FOR EACH ROW EXECUTE FUNCTION private.require_wording_verification_record();

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
      WHERE tgrelid='public.care_plan_items'::regclass
        AND tgname='care_plan_items_wording_verification_present' AND NOT tgisinternal)
     OR has_function_privilege('anon','private.require_wording_verification_record()','EXECUTE')
     OR has_function_privilege('authenticated','private.require_wording_verification_record()','EXECUTE') THEN
    RAISE EXCEPTION 'Wording verification guard must remain present and backend-only';
  END IF;
END $$;
