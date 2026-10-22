-- LOC-003 item 9: referential integrity and a retention rule for message_translations.
--
-- The table is polymorphic (source_table is 'care_team_conversation_messages' or
-- 'chat_messages'), so one SQL foreign key cannot express it. Two things stand in for it:
--   * a delete trigger on each source table removes that message's translations, which is
--     the cascade a real foreign key would have given us; and
--   * a purge function sweeps rows the triggers could not have caught — messages deleted
--     before this migration, and stale failure markers, which are retry state rather than
--     a record of anything.
--
-- A translation is never the record of truth, so deleting one loses no clinical content:
-- the original message is the record, and safety checks only ever read the original.

-- Trigger function: delete the just-removed message's translations. The stored label is
-- passed as the trigger argument because the physical table name and the label differ
-- (care_conversation_messages rows are stored under 'care_team_conversation_messages').
CREATE OR REPLACE FUNCTION private.delete_message_translations()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
  DELETE FROM public.message_translations
  WHERE source_table = TG_ARGV[0] AND source_message_id = OLD.id;
  RETURN OLD;
END;
$$;

REVOKE ALL ON FUNCTION private.delete_message_translations() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS message_translations_cleanup ON public.care_conversation_messages;
CREATE TRIGGER message_translations_cleanup
  AFTER DELETE ON public.care_conversation_messages
  FOR EACH ROW EXECUTE FUNCTION private.delete_message_translations('care_team_conversation_messages');

DROP TRIGGER IF EXISTS message_translations_cleanup ON public.chat_messages;
CREATE TRIGGER message_translations_cleanup
  AFTER DELETE ON public.chat_messages
  FOR EACH ROW EXECUTE FUNCTION private.delete_message_translations('chat_messages');

-- Retention rule. Two classes of row are removed:
--   * orphans: no surviving source message (a message deleted before the triggers existed);
--   * expired failure markers: guard_failure_code = 'model_error' rows older than the given
--     age. The reader treats a marker younger than an hour as "do not call the model again";
--     past that it is dead weight, and removing it restores a clean retry.
-- A successful translation is kept for as long as its message lives: it is display state for
-- a message a clinician may reopen at any time, and re-translating would spend a model call
-- to reproduce text we already had.
CREATE OR REPLACE FUNCTION public.purge_message_translations(
  p_failure_marker_max_age interval DEFAULT interval '7 days'
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
  orphans integer;
  expired integer;
BEGIN
  WITH deleted AS (
    DELETE FROM public.message_translations mt
    WHERE (mt.source_table = 'care_team_conversation_messages'
           AND NOT EXISTS (SELECT 1 FROM public.care_conversation_messages m
                           WHERE m.id = mt.source_message_id))
       OR (mt.source_table = 'chat_messages'
           AND NOT EXISTS (SELECT 1 FROM public.chat_messages c
                           WHERE c.id = mt.source_message_id))
    RETURNING 1
  )
  SELECT count(*) INTO orphans FROM deleted;

  WITH deleted AS (
    DELETE FROM public.message_translations
    WHERE guard_failure_code = 'model_error'
      AND translated_at < clock_timestamp() - p_failure_marker_max_age
    RETURNING 1
  )
  SELECT count(*) INTO expired FROM deleted;

  RETURN jsonb_build_object(
    'orphans_removed', orphans,
    'expired_failure_markers_removed', expired
  );
END;
$$;

REVOKE ALL ON FUNCTION public.purge_message_translations(interval) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.purge_message_translations(interval) TO service_role;

COMMENT ON FUNCTION private.delete_message_translations() IS
  'LOC-003: removes a message''s stored translations when the source message is deleted. '
  'Stands in for the foreign key the polymorphic source_table cannot express.';
COMMENT ON FUNCTION public.purge_message_translations(interval) IS
  'LOC-003 retention rule: deletes message_translations with no surviving source message, '
  'and failure markers older than the given age. Returns the counts removed.';

-- Fail closed: the triggers must exist and no browser role may execute the purge.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger
    WHERE tgname = 'message_translations_cleanup'
      AND tgrelid = 'public.care_conversation_messages'::regclass
      AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'care_conversation_messages must clean up its message translations';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger
    WHERE tgname = 'message_translations_cleanup'
      AND tgrelid = 'public.chat_messages'::regclass
      AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'chat_messages must clean up its message translations';
  END IF;
  IF has_function_privilege('anon', 'public.purge_message_translations(interval)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.purge_message_translations(interval)', 'EXECUTE') THEN
    RAISE EXCEPTION 'Browser roles must not purge message translations';
  END IF;
END $$;
