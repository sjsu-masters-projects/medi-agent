-- The server-side synthetic fixture adapter uses the service role after its
-- migration-ledger preflight. These privileges do not apply to anon or
-- authenticated browser roles and do not alter RLS policies.
GRANT SELECT, INSERT, UPDATE ON TABLE
  public.clinics,
  public.clinicians,
  public.patients,
  public.care_teams,
  public.documents,
  public.medications,
  public.conditions,
  public.allergies,
  public.appointments,
  public.chat_messages,
  public.notifications
TO service_role;

-- The guarded reset removes only the two canonical synthetic clinics.
GRANT DELETE ON TABLE public.clinics TO service_role;
