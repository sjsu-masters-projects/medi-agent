-- The trusted backend aggregates symptom reports for a locally authorized
-- clinician's patient deep-dive view. Browser roles receive no new privilege.
GRANT SELECT ON TABLE public.symptom_reports TO service_role;
