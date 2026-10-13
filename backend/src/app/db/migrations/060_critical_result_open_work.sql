-- AI-005 follow-up to 059_critical_result_alerts.sql: a critical-result alert is open work.
--
-- 059 records the alert and makes it actionable, but the clinician Alerts "Needs attention"
-- list is built by notification_open_work, which names each kind of open work. Without
-- this, the alert appeared only under History. It now stays in "Needs attention" until a
-- clinician acknowledges it, unless its document was rejected as not this patient's.
-- Same signature as 054, so its grants still apply.
-- Shares the 060 prefix with the parallel confirmed-symptom-intake branch; the ledger keys on
-- the full filename, and the two touch different objects.

CREATE OR REPLACE FUNCTION private.notification_open_work(p_actor uuid,p_role text,p_patients uuid[])
RETURNS SETOF public.notification_receipts
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 -- OFFSET 0 keeps each lookup a per-row index probe from the open source, so the plan
 -- cannot turn around and scan all of this person's receipts or all events.
 WITH open_events AS MATERIALIZED (
   SELECT x.id FROM public.documents d CROSS JOIN LATERAL (SELECT e.id FROM public.notification_events e
       WHERE e.source_type='documents' AND e.source_id=d.id
         AND ((e.event_type='document_review' AND d.review_status='pending') OR (e.event_type='document_failed'
           AND d.parse_status IN ('failed','needs_ocr','needs_evidence_review'))) OFFSET 0) x
     WHERE d.patient_id=ANY(p_patients)
       AND (d.review_status='pending' OR d.parse_status IN ('failed','needs_ocr','needs_evidence_review'))
   UNION ALL SELECT x.id FROM public.care_plan_versions v CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='care_plan_versions' AND e.source_id=v.id
         AND e.event_type='care_plan_draft' OFFSET 0) x
     WHERE v.patient_id=ANY(p_patients) AND v.status='draft'
   UNION ALL SELECT x.id FROM public.adr_assessments a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='adr_assessments' AND e.source_id=a.id
         AND e.event_type='adr_review' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status='draft'
   UNION ALL SELECT x.id FROM public.adherence_logs a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='adherence_logs' AND e.source_id=a.id
         AND e.event_type='barrier_reported' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status='skipped' AND a.barrier_code IS NOT NULL
   UNION ALL SELECT x.id FROM public.appointments a CROSS JOIN LATERAL (SELECT e.id
       FROM public.notification_events e WHERE e.source_type='appointments' AND e.source_id=a.id
         AND e.event_type='appointment_response' OFFSET 0) x
     WHERE a.patient_id=ANY(p_patients) AND a.status IN ('declined','alternative_requested','cancelled')
   UNION ALL SELECT e.id FROM public.notification_events e
     WHERE e.event_type='safety_flag' AND e.patient_id=ANY(p_patients)
   UNION ALL SELECT e.id FROM public.notification_events e
     WHERE e.event_type='critical_result' AND e.patient_id=ANY(p_patients)
       AND NOT EXISTS(SELECT 1 FROM public.documents d
         WHERE d.id=e.source_id AND d.review_status='rejected')
 )
 SELECT r.* FROM open_events o CROSS JOIN LATERAL (SELECT n.* FROM public.notification_receipts n
   WHERE n.event_id=o.id AND n.recipient_id=p_actor AND n.recipient_role=p_role
     AND n.acknowledged_at IS NULL OFFSET 0) r
 WHERE p_role='clinician'
$$;
