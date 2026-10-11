-- Deleting a patient or clinician account removes what belongs to that person.
--
-- 048 (care-team conversations) and 041 (appointment offer audit) declared their
-- references without a delete rule, so deleting an auth user, patient or clinician
-- who had ever messaged, read a thread or answered an offer failed. Each reference is
-- recreated below with an explicit rule. The requester's decision: a patient's data is
-- deleted with the patient's account. A clinician leaving does not erase the patient's
-- record of the conversation: the thread and messages stay, the clinician reference
-- becomes NULL and the stored sender_name keeps each message attributable.
--
-- Append-only history stays append-only. The offer audit trigger now rejects UPDATE
-- only (as 051 does for notification history), so cascades can remove rows; no role is
-- granted DELETE on any of these tables, so nothing else can.

-- A thread is the patient's: it goes with the patient.
ALTER TABLE public.care_conversations
  DROP CONSTRAINT care_conversations_patient_id_fkey,
  ADD CONSTRAINT care_conversations_patient_id_fkey FOREIGN KEY (patient_id)
    REFERENCES public.patients(id) ON DELETE CASCADE;
-- The clinician and the assignment are references to someone else. A deleted clinician
-- (whose care_teams rows cascade) leaves the patient's thread in place, unlinked. Only
-- an active assignment can read a thread, so an unlinked thread is retained, not served.
ALTER TABLE public.care_conversations
  ALTER COLUMN clinician_id DROP NOT NULL,
  ALTER COLUMN care_team_id DROP NOT NULL,
  DROP CONSTRAINT care_conversations_clinician_id_fkey,
  ADD CONSTRAINT care_conversations_clinician_id_fkey FOREIGN KEY (clinician_id)
    REFERENCES public.clinicians(id) ON DELETE SET NULL,
  DROP CONSTRAINT care_conversations_care_team_id_fkey,
  ADD CONSTRAINT care_conversations_care_team_id_fkey FOREIGN KEY (care_team_id)
    REFERENCES public.care_teams(id) ON DELETE SET NULL;
-- clinic_id is unchanged: a clinic is not a person and clinics are not deleted here.

-- Messages, read markers and audit rows are part of their thread.
ALTER TABLE public.care_conversation_messages
  DROP CONSTRAINT care_conversation_messages_conversation_id_fkey,
  ADD CONSTRAINT care_conversation_messages_conversation_id_fkey FOREIGN KEY (conversation_id)
    REFERENCES public.care_conversations(id) ON DELETE CASCADE;
-- A patient's own messages go with their thread (above). A deleted clinician's messages
-- stay in the patient's thread: sender_id becomes NULL, sender_role and sender_name stay.
ALTER TABLE public.care_conversation_messages
  ALTER COLUMN sender_id DROP NOT NULL,
  DROP CONSTRAINT care_conversation_messages_sender_id_fkey,
  ADD CONSTRAINT care_conversation_messages_sender_id_fkey FOREIGN KEY (sender_id)
    REFERENCES auth.users(id) ON DELETE SET NULL;

ALTER TABLE public.care_conversation_reads
  DROP CONSTRAINT care_conversation_reads_conversation_id_fkey,
  ADD CONSTRAINT care_conversation_reads_conversation_id_fkey FOREIGN KEY (conversation_id)
    REFERENCES public.care_conversations(id) ON DELETE CASCADE,
  -- A read marker is that person's own state.
  DROP CONSTRAINT care_conversation_reads_actor_id_fkey,
  ADD CONSTRAINT care_conversation_reads_actor_id_fkey FOREIGN KEY (actor_id)
    REFERENCES auth.users(id) ON DELETE CASCADE,
  -- Messages are removed only with their thread, which removes its markers too.
  DROP CONSTRAINT care_conversation_reads_last_message_id_fkey,
  ADD CONSTRAINT care_conversation_reads_last_message_id_fkey FOREIGN KEY (last_message_id)
    REFERENCES public.care_conversation_messages(id) ON DELETE CASCADE;

ALTER TABLE public.care_conversation_audit_events
  DROP CONSTRAINT care_conversation_audit_events_conversation_id_fkey,
  ADD CONSTRAINT care_conversation_audit_events_conversation_id_fkey FOREIGN KEY (conversation_id)
    REFERENCES public.care_conversations(id) ON DELETE CASCADE,
  DROP CONSTRAINT care_conversation_audit_events_message_id_fkey,
  ADD CONSTRAINT care_conversation_audit_events_message_id_fkey FOREIGN KEY (message_id)
    REFERENCES public.care_conversation_messages(id) ON DELETE CASCADE;
-- The audit trail of a retained thread stays complete when a clinician is deleted; the
-- actor becomes NULL like the sender of the messages it describes.
ALTER TABLE public.care_conversation_audit_events
  ALTER COLUMN actor_id DROP NOT NULL,
  DROP CONSTRAINT care_conversation_audit_events_actor_id_fkey,
  ADD CONSTRAINT care_conversation_audit_events_actor_id_fkey FOREIGN KEY (actor_id)
    REFERENCES auth.users(id) ON DELETE SET NULL;

-- Offer audit rows describe one appointment of one patient. Appointments already
-- cascade with the patient and with the care team (001), so their audit goes with them.
-- actor_id has no foreign key and is unchanged.
ALTER TABLE public.appointment_offer_events
  DROP CONSTRAINT appointment_offer_events_appointment_id_fkey,
  ADD CONSTRAINT appointment_offer_events_appointment_id_fkey FOREIGN KEY (appointment_id)
    REFERENCES public.appointments(id) ON DELETE CASCADE,
  DROP CONSTRAINT appointment_offer_events_patient_id_fkey,
  ADD CONSTRAINT appointment_offer_events_patient_id_fkey FOREIGN KEY (patient_id)
    REFERENCES public.patients(id) ON DELETE CASCADE;
-- Same trigger name and function, so existing verification keeps recognising it.
DROP TRIGGER appointment_offer_events_immutable ON public.appointment_offer_events;
CREATE TRIGGER appointment_offer_events_immutable
  BEFORE UPDATE ON public.appointment_offer_events
  FOR EACH ROW EXECUTE FUNCTION public.protect_appointment_offer_events();
-- The trigger no longer stops a direct DELETE, so no role may hold that privilege. 041
-- revoked only browser roles, and hosted default privileges can grant service_role ALL
-- on new tables; revoke explicitly. Repeating the revoke on 048 tables is harmless.
REVOKE DELETE, TRUNCATE ON public.appointment_offer_events, public.care_conversations,
  public.care_conversation_messages, public.care_conversation_reads,
  public.care_conversation_audit_events FROM PUBLIC, anon, authenticated, service_role;

-- Fail the migration rather than leave a reference that still blocks deletion, or a
-- role that could delete history directly.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
    WHERE c.contype = 'f' AND c.confdeltype NOT IN ('c', 'n')
      AND c.conrelid IN ('public.care_conversations'::regclass,
        'public.care_conversation_messages'::regclass, 'public.care_conversation_reads'::regclass,
        'public.care_conversation_audit_events'::regclass, 'public.appointment_offer_events'::regclass)
      AND c.confrelid <> 'public.clinics'::regclass
  ) THEN
    RAISE EXCEPTION 'A conversation or offer reference still has no delete rule';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['public.care_conversations', 'public.care_conversation_messages',
      'public.care_conversation_reads', 'public.care_conversation_audit_events',
      'public.appointment_offer_events']) t(name)
    CROSS JOIN unnest(ARRAY['anon', 'authenticated', 'service_role']) r(role)
    WHERE pg_catalog.has_table_privilege(r.role, t.name, 'DELETE')
  ) THEN
    RAISE EXCEPTION 'No role may delete conversation or offer history directly';
  END IF;
END $$;
