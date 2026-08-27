-- SMART launch and import processing runs only in the trusted backend after
-- local clinician and care-team authorization. Browser roles receive no new
-- privileges, and the backend has no delete capability for these records.

GRANT SELECT, INSERT, UPDATE ON TABLE
  public.smart_launch_sessions,
  public.fhir_imports,
  public.smart_portal_handoffs,
  public.clinical_facts
TO service_role;

GRANT SELECT, INSERT ON TABLE
  public.fhir_import_resources,
  public.source_provenances,
  public.evidence_citations,
  public.clinical_fact_audit_events
TO service_role;
