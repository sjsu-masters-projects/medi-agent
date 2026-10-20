-- LOC-003 items 8 and 11: cache the back-translation a clinician verifies against, and
-- record which deterministic guards passed at the moment the wording was marked verified.
--
-- Both columns live on care_plan_items, which already has row level security and the
-- grants the plan tables share, so no new table or grant is introduced here.

ALTER TABLE public.care_plan_items
  ADD COLUMN IF NOT EXISTS back_translation jsonb
    CHECK (back_translation IS NULL OR jsonb_typeof(back_translation) = 'object'),
  ADD COLUMN IF NOT EXISTS wording_verification jsonb
    CHECK (wording_verification IS NULL OR jsonb_typeof(wording_verification) = 'object');

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

-- A verified item must carry its guard outcome, and an unverified one must not keep a
-- stale record of a check that no longer describes the stored wording. Added NOT VALID so
-- rows approved before this migration are not rewritten; new writes are checked.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conrelid = 'public.care_plan_items'::regclass
      AND conname = 'care_plan_items_wording_verification_present'
  ) THEN
    ALTER TABLE public.care_plan_items
      ADD CONSTRAINT care_plan_items_wording_verification_present
      CHECK (NOT wording_verified OR wording_verification IS NOT NULL) NOT VALID;
  END IF;
END $$;
