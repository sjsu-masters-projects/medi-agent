-- Repair policies created after 020 without reopening public helper RPCs.
-- Clinical writes and publication remain behind the authorized backend.
ALTER POLICY care_plan_versions_patient_select ON public.care_plan_versions
  TO authenticated;
ALTER POLICY care_plan_versions_clinician_select ON public.care_plan_versions
  TO authenticated USING (
    private.is_clinician() AND private.is_assigned_clinician(patient_id)
  );
ALTER POLICY care_plan_items_patient_select ON public.care_plan_items
  TO authenticated;
ALTER POLICY care_plan_items_clinician_select ON public.care_plan_items
  TO authenticated USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_items.plan_version_id
      AND private.is_clinician() AND private.is_assigned_clinician(v.patient_id)
  ));
ALTER POLICY care_plan_generation_requests_clinician_select
  ON public.care_plan_generation_requests
  TO authenticated USING (
    private.is_clinician() AND private.is_assigned_clinician(patient_id)
  );
ALTER POLICY care_plan_audit_events_clinician_select ON public.care_plan_audit_events
  TO authenticated USING (EXISTS (
    SELECT 1 FROM public.care_plan_versions v
    WHERE v.id = care_plan_audit_events.plan_version_id
      AND private.is_clinician() AND private.is_assigned_clinician(v.patient_id)
  ));

REVOKE ALL ON public.care_plan_versions, public.care_plan_items,
  public.care_plan_generation_requests, public.care_plan_audit_events
  FROM PUBLIC, anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON public.care_plan_versions, public.care_plan_items,
  public.care_plan_generation_requests, public.care_plan_audit_events
  FROM authenticated;
GRANT SELECT ON public.care_plan_versions, public.care_plan_items,
  public.care_plan_generation_requests, public.care_plan_audit_events
  TO authenticated;
