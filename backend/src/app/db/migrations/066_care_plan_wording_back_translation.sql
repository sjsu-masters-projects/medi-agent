-- LOC-003: English-first clinician review of Spanish wording. Requires 049.
-- Independent of 065 (numbered after it only because 065 is reserved by another change).
-- Applied to a hosted project only on explicit authorization.
--
-- An English-only clinician verifies an item's Spanish through an English reading of it.
-- That reading is generated once (after generation, after a re-translation, or on request)
-- and stored with the item, so it is not re-drafted on every view. It is a review aid:
-- approval never requires it, it is never projected to medications or obligations, and
-- the patient-facing `wording` column and its shape check are unchanged.
--
-- Shape: {} when none is stored, otherwise
--   {"status": "drafted" | "rejected",
--    "method": "back_translation" | "forward_translation",
--    "wording_sha256": <hash of the es-MX wording it reads>,
--    "text": {"title", "instructions", "frequency"},      -- when drafted
--    "reason": <guard rejection code>,                      -- when rejected
--    "model": <model id or null>, "drafted_at": <timestamp>}
-- A changed Spanish wording no longer matches wording_sha256, so the reading shows as stale.
-- New draft rows (including carried-forward approved items) start empty and are filled by
-- the service after generation; the generation and approval functions are not changed.

ALTER TABLE public.care_plan_items
  ADD COLUMN wording_back_translation jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(wording_back_translation) = 'object'
      AND (wording_back_translation - 'status' - 'method' - 'wording_sha256' - 'text'
        - 'reason' - 'model' - 'drafted_at') = '{}'::jsonb
      AND (wording_back_translation = '{}'::jsonb
        OR (wording_back_translation->>'status' IN ('drafted', 'rejected')
          AND wording_back_translation->>'method' IN ('back_translation', 'forward_translation')
          AND COALESCE(wording_back_translation->>'wording_sha256', '') ~ '^[0-9a-f]{64}$'))
      AND COALESCE(jsonb_typeof(wording_back_translation->'text'), 'object') = 'object'
      AND (COALESCE(wording_back_translation->'text', '{}'::jsonb)
        - 'title' - 'instructions' - 'frequency') = '{}'::jsonb
      AND char_length(COALESCE(wording_back_translation #>> '{text,title}', '')) <= 300
      AND char_length(COALESCE(wording_back_translation #>> '{text,instructions}', '')) <= 2000
      AND char_length(COALESCE(wording_back_translation #>> '{text,frequency}', '')) <= 200
      AND char_length(COALESCE(wording_back_translation->>'reason', '')) <= 100
      AND char_length(COALESCE(wording_back_translation->>'model', '')) <= 200);

COMMENT ON COLUMN public.care_plan_items.wording_back_translation IS
  'LOC-003 review aid: English reading of the es-MX wording, keyed by its hash. Never patient-facing or required for approval.';
