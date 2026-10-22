-- Exact clinician-confirmed wording and its human message commit together.
-- 067 owns the already-applied English fact fields; no duplicate migration of them.
ALTER TABLE public.message_translations
  ADD COLUMN IF NOT EXISTS clinician_confirmed boolean NOT NULL DEFAULT false;

-- Background translation retries must not replace a human-approved delivery decision.
CREATE OR REPLACE FUNCTION private.protect_message_delivery_wording()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF OLD.clinician_confirmed OR OLD.guard_failure_code='original_only' THEN
    RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Message delivery wording is immutable';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_message_delivery_wording() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS message_delivery_wording_immutable ON public.message_translations;
CREATE TRIGGER message_delivery_wording_immutable BEFORE UPDATE ON public.message_translations
  FOR EACH ROW EXECUTE FUNCTION private.protect_message_delivery_wording();

CREATE OR REPLACE FUNCTION public.care_conversation_confirmed_operation(
  p_actor_id uuid, p_actor_role text, p_action text, p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_confirmation jsonb := p_payload->'confirmed_translation';
  v_result jsonb;
  v_existing uuid;
  v_translation public.message_translations;
  v_locale text;
  v_original_only boolean := p_payload->'confirmed_translation' IS NULL;
BEGIN
  IF p_actor_role IS DISTINCT FROM 'clinician' THEN
    RAISE EXCEPTION USING ERRCODE='42501', MESSAGE='Conversation unavailable';
  END IF;
  IF v_original_only THEN
    IF (p_payload->>'original_source_locale' IN ('en-US','es-MX')) IS NOT TRUE THEN
      RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid original wording locale';
    END IF;
    v_confirmation := jsonb_build_object(
      'text','-','source_locale',p_payload->>'original_source_locale',
      'locale',CASE WHEN p_payload->>'original_source_locale'='en-US' THEN 'es-MX' ELSE 'en-US' END);
  END IF;
  IF p_action IS DISTINCT FROM 'send'
     OR jsonb_typeof(v_confirmation) IS DISTINCT FROM 'object'
     OR p_payload->>'care_plan_item_id' IS NOT NULL
     OR coalesce(char_length(v_confirmation->>'text'),0) NOT BETWEEN 1 AND 8000
     OR (v_confirmation->>'locale' IN ('en-US','es-MX')) IS NOT TRUE
     OR (v_confirmation->>'source_locale' IN ('en-US','es-MX')) IS NOT TRUE
     OR v_confirmation->>'locale' = v_confirmation->>'source_locale'
     OR coalesce(char_length(v_confirmation->>'model_id'),0) > 200
     OR v_confirmation->>'model_id' = 'offline-translation-stub' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Invalid confirmed wording';
  END IF;

  -- Same key and lock order as the existing authoritative send operation.
  PERFORM pg_advisory_xact_lock(hashtextextended(
    p_actor_id::text || ':' || (p_payload->>'client_message_id')::uuid::text,0));
  SELECT id INTO v_existing FROM public.care_conversation_messages
    WHERE sender_id=p_actor_id AND client_message_id=(p_payload->>'client_message_id')::uuid;
  -- Only patients attach activities. This clinician-only send retains the core
  -- private-thread/clinic authorization without introducing another review action.
  v_result := public.care_conversation_operation(
    p_actor_id,p_actor_role,'send',p_payload - 'confirmed_translation');

  -- Recheck the preference in the same transaction and prevent a concurrent change.
  SELECT p.preferred_language INTO v_locale FROM public.patients p
    JOIN public.care_conversations c ON c.patient_id=p.id
    WHERE c.id=(p_payload->>'conversation_id')::uuid FOR SHARE OF p;
  IF NOT v_original_only AND v_locale IS DISTINCT FROM v_confirmation->>'locale' THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='Patient language changed; preview again';
  END IF;

  IF v_existing IS NULL THEN
    INSERT INTO public.message_translations(
      source_table,source_message_id,source_locale,target_locale,translated_text,
      guard_passed,guard_failure_code,model_id,clinician_confirmed
    ) VALUES (
      'care_team_conversation_messages',(v_result->>'id')::uuid,
      v_confirmation->>'source_locale',v_confirmation->>'locale',v_confirmation->>'text',
      NOT v_original_only,CASE WHEN v_original_only THEN 'original_only' END,
      v_confirmation->>'model_id',NOT v_original_only
    );
  END IF;
  SELECT * INTO v_translation FROM public.message_translations
    WHERE source_table='care_team_conversation_messages'
      AND source_message_id=(v_result->>'id')::uuid
      AND target_locale=v_confirmation->>'locale';
  IF NOT FOUND OR v_translation.clinician_confirmed IS DISTINCT FROM NOT v_original_only
     OR (v_original_only AND v_translation.guard_failure_code IS DISTINCT FROM 'original_only')
     OR v_translation.translated_text IS DISTINCT FROM v_confirmation->>'text'
     OR v_translation.source_locale IS DISTINCT FROM v_confirmation->>'source_locale'
     OR v_translation.model_id IS DISTINCT FROM v_confirmation->>'model_id' THEN
    RAISE EXCEPTION USING ERRCODE='23505', MESSAGE='Confirmed wording retry mismatch';
  END IF;
  IF v_original_only THEN RETURN v_result; END IF;
  RETURN v_result || jsonb_build_object(
    'translation',v_translation.translated_text,'translation_locale',v_translation.target_locale,
    'translation_guard_passed',true,'translation_model_id',v_translation.model_id);
END $$;

REVOKE ALL ON FUNCTION public.care_conversation_confirmed_operation(uuid,text,text,jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.care_conversation_confirmed_operation(uuid,text,text,jsonb)
  TO service_role;

DO $$
BEGIN
  IF NOT (SELECT relrowsecurity FROM pg_catalog.pg_class
          WHERE oid='public.message_translations'::regclass)
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger
       WHERE tgrelid='public.message_translations'::regclass AND tgname='message_delivery_wording_immutable'
       AND NOT tgisinternal)
     OR has_table_privilege('anon','public.message_translations','SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated','public.message_translations','SELECT,INSERT,UPDATE,DELETE')
     OR has_function_privilege('anon','public.care_conversation_confirmed_operation(uuid,text,text,jsonb)','EXECUTE')
     OR has_function_privilege('authenticated','public.care_conversation_confirmed_operation(uuid,text,text,jsonb)','EXECUTE') THEN
    RAISE EXCEPTION 'Confirmed wording must remain backend-only with RLS';
  END IF;
END $$;
