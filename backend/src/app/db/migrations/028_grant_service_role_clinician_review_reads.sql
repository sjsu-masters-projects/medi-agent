-- Permit only the server-side clinician-review queries that follow care-team authorization.
-- Browser roles retain no direct access to these tables.

GRANT SELECT ON TABLE public.soap_notes, public.adr_assessments TO service_role;
