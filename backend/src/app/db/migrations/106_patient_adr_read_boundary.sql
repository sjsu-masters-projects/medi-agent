-- SAFE-003: patients receive follow-up questions and receipts, not clinical assessments.
-- Retain existing clinician assignment policies and backend service-role access.
DROP POLICY IF EXISTS adr_patient_select ON public.adr_assessments;
