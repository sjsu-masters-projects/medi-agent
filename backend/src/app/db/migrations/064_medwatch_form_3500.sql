-- PV-001-C: MedWatch drafts become Form FDA 3500 (09/2025), with discard and a record of
-- a submission the clinician made outside MediAgent. Requires 063.
--
-- 048 labelled drafts 3500A, allowed one draft per assessment for ever, had no way to undo
-- a mistaken draft, and its CHECK `status = 'submitted' OR submitted_at IS NULL` did not
-- stop a row being marked submitted. Now:
--   * new drafts are Form 3500 (`form_version` fda-3500-2025-09) and carry a non-identifying
--     patient reference; 048 rows are relabelled `fda-3500-legacy-048` and upgraded on read;
--   * a draft can be discarded (three columns, not an enum value: a value added by
--     ALTER TYPE ... ADD VALUE cannot be used in the transaction that adds it), which
--     returns its assessment to review in the same transaction; one non-discarded draft
--     per assessment;
--   * a submission made outside MediAgent is an append-only row, corrected only by an
--     amendment row; `submitted` requires approval and that row (trigger, because a CHECK
--     cannot see another table); submitted and discarded drafts are frozen;
--   * every export records its format and, for a PDF, the template revision and SHA-256.
-- No code path, function or table here transmits anything to FDA.
--
-- Every 048 function keeps its signature and keeps working, so the backend deployed before
-- this change still runs after it. New patient references cascade on patient deletion (as
-- 063 does for ADR data); clinician references stay RESTRICT until D1 is decided.
-- Written for review; it is applied to a hosted project only on explicit authorization.

-- 1. Discard columns, the non-identifying patient reference and Form 3500 labels.
ALTER TABLE public.medwatch_drafts
  ADD COLUMN discarded_at timestamptz,
  ADD COLUMN discarded_by uuid REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  ADD COLUMN discard_reason text,
  ADD COLUMN patient_reference text,
  ADD CONSTRAINT medwatch_drafts_discard_reason_length
    CHECK (discard_reason IS NULL OR char_length(btrim(discard_reason)) BETWEEN 1 AND 2000),
  ADD CONSTRAINT medwatch_drafts_discard_complete
    CHECK (num_nonnulls(discarded_at, discarded_by, discard_reason) IN (0, 3)),
  ADD CONSTRAINT medwatch_drafts_discard_not_submitted
    CHECK (discarded_at IS NULL OR status <> 'submitted'),
  ADD CONSTRAINT medwatch_drafts_patient_reference_format
    CHECK (patient_reference IS NULL OR patient_reference ~ '^[A-Z]{2}-[A-Z2-7]{4}$');

ALTER TABLE public.medwatch_drafts
  ALTER COLUMN export_version SET DEFAULT 'fda-3500-2025-09';

UPDATE public.medwatch_drafts
SET export_version = 'fda-3500-legacy-048'
WHERE export_version = 'medwatch-3500a-draft-v1';

COMMENT ON COLUMN public.medwatch_drafts.form_data IS
  'Form FDA 3500 (09/2025) drug-report draft values (form_version fda-3500-2025-09). Rows '
  'labelled fda-3500-legacy-048 hold the 048 shape and are upgraded on read.';
COMMENT ON TABLE public.medwatch_drafts IS
  'Editable clinician-approved Form FDA 3500 drafts; not FDA submissions.';

-- The stored label always follows the stored shape, including rows a backend deployed
-- before this change creates with the 048 payload, and 048 drafts saved again as Form 3500.
CREATE FUNCTION private.medwatch_drafts_export_version() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  NEW.export_version := CASE
    WHEN NEW.form_data->>'form_version' = 'fda-3500-2025-09' THEN 'fda-3500-2025-09'
    ELSE 'fda-3500-legacy-048'
  END;
  RETURN NEW;
END;
$$;

CREATE TRIGGER medwatch_drafts_export_version
  BEFORE INSERT OR UPDATE OF form_data ON public.medwatch_drafts
  FOR EACH ROW EXECUTE FUNCTION private.medwatch_drafts_export_version();

-- 2. One non-discarded draft per assessment; a discarded draft no longer blocks a new one.
DROP INDEX public.idx_medwatch_one_draft_per_assessment;
CREATE UNIQUE INDEX idx_medwatch_one_draft_per_assessment
  ON public.medwatch_drafts(adr_assessment_id)
  WHERE discarded_at IS NULL;

-- 3. Submissions made outside MediAgent. Append only: the newest row that no other row
-- amends is the current record. Inserts happen only inside the RPCs below.
CREATE TABLE public.medwatch_external_submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  medwatch_draft_id uuid NOT NULL
    REFERENCES public.medwatch_drafts(id) ON DELETE CASCADE,
  adr_assessment_id uuid NOT NULL
    REFERENCES public.adr_assessments(id) ON DELETE CASCADE,
  patient_id uuid NOT NULL REFERENCES public.patients(id) ON DELETE CASCADE,
  recorded_by uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  submitted_on date NOT NULL,
  method text NOT NULL CHECK (method IN ('medwatch_online', 'fax', 'mail', 'other')),
  method_detail text
    CHECK (method_detail IS NULL OR char_length(btrim(method_detail)) BETWEEN 1 AND 500),
  fda_reference text
    CHECK (fda_reference IS NULL OR char_length(btrim(fda_reference)) BETWEEN 1 AND 100),
  attested boolean NOT NULL,
  amends_id uuid REFERENCES public.medwatch_external_submissions(id) ON DELETE CASCADE,
  amend_reason text
    CHECK (amend_reason IS NULL OR char_length(btrim(amend_reason)) BETWEEN 1 AND 2000),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT medwatch_external_submissions_attested CHECK (attested),
  CONSTRAINT medwatch_external_submissions_other_detail
    CHECK (method <> 'other' OR method_detail IS NOT NULL),
  CONSTRAINT medwatch_external_submissions_amendment_reason
    CHECK ((amends_id IS NULL) = (amend_reason IS NULL))
);

CREATE INDEX idx_medwatch_submissions_draft_created
  ON public.medwatch_external_submissions(medwatch_draft_id, created_at DESC);
CREATE UNIQUE INDEX idx_medwatch_submissions_one_original
  ON public.medwatch_external_submissions(medwatch_draft_id)
  WHERE amends_id IS NULL;
CREATE UNIQUE INDEX idx_medwatch_submissions_one_amendment_each
  ON public.medwatch_external_submissions(amends_id)
  WHERE amends_id IS NOT NULL;

ALTER TABLE public.medwatch_external_submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY medwatch_submissions_clinician_select
  ON public.medwatch_external_submissions FOR SELECT TO authenticated
  USING (
    private.is_clinician()
    AND private.is_assigned_clinician(patient_id)
  );

REVOKE ALL ON TABLE public.medwatch_external_submissions
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.medwatch_external_submissions TO authenticated, service_role;

-- History is never rewritten. DELETE is blocked by privilege, not a trigger, so the
-- patient cascade still removes these rows.
CREATE FUNCTION private.medwatch_submissions_append_only() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'MedWatch submission records are append only; record an amendment'
    USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER medwatch_submissions_append_only
  BEFORE UPDATE ON public.medwatch_external_submissions
  FOR EACH ROW EXECUTE FUNCTION private.medwatch_submissions_append_only();

COMMENT ON TABLE public.medwatch_external_submissions IS
  'Clinician-attested records of Form FDA 3500 submissions made outside MediAgent; '
  'append only, corrected by amendment rows. MediAgent never submits to FDA.';

-- 4. `submitted` only with approval and a submission record; submitted and discarded drafts
-- are frozen. Replaces 048's CHECK, which tied submitted_at to the status but did not stop
-- a submitted status, also for service_role.
ALTER TABLE public.medwatch_drafts
  DROP CONSTRAINT medwatch_drafts_not_submitted_by_app,
  ADD CONSTRAINT medwatch_drafts_submitted_at_matches_status
    CHECK ((status = 'submitted') = (submitted_at IS NOT NULL));

CREATE FUNCTION private.medwatch_drafts_submission_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status = 'submitted' THEN
      RAISE EXCEPTION 'A MedWatch draft is submitted only after approval and a submission record'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'submitted' OR OLD.discarded_at IS NOT NULL THEN
    IF NEW.form_data IS DISTINCT FROM OLD.form_data
      OR NEW.status IS DISTINCT FROM OLD.status
      OR NEW.revision IS DISTINCT FROM OLD.revision
      OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at
      OR NEW.approved_by IS DISTINCT FROM OLD.approved_by
      OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
      OR NEW.approval_note IS DISTINCT FROM OLD.approval_note
      OR NEW.discarded_at IS DISTINCT FROM OLD.discarded_at
      OR NEW.discarded_by IS DISTINCT FROM OLD.discarded_by
      OR NEW.discard_reason IS DISTINCT FROM OLD.discard_reason
    THEN
      RAISE EXCEPTION 'Submitted or discarded MedWatch drafts cannot be changed'
        USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
  END IF;
  -- Becoming submitted: only from an approved draft that has its submission record.
  IF NEW.status = 'submitted' AND (
    OLD.status <> 'reviewed'
    OR NEW.approved_by IS NULL
    OR NEW.approved_at IS NULL
    OR NOT EXISTS (
      SELECT 1 FROM public.medwatch_external_submissions s
      WHERE s.medwatch_draft_id = NEW.id AND s.amends_id IS NULL AND s.attested
    )
  ) THEN
    RAISE EXCEPTION 'A MedWatch draft is submitted only after approval and a submission record'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER medwatch_drafts_submission_guard
  BEFORE INSERT OR UPDATE ON public.medwatch_drafts
  FOR EACH ROW EXECUTE FUNCTION private.medwatch_drafts_submission_guard();

-- 5. Audit types. Both lists are supersets, so existing rows still validate.
ALTER TABLE public.medwatch_draft_audit_events
  DROP CONSTRAINT medwatch_draft_audit_events_event_type_check,
  ADD CONSTRAINT medwatch_draft_audit_events_event_type_check CHECK (event_type IN (
    'created', 'edited', 'approved', 'exported',
    'discarded', 'submission_recorded', 'submission_amended'));

ALTER TABLE public.adr_assessment_audit_events
  DROP CONSTRAINT adr_assessment_audit_events_event_type_check,
  ADD CONSTRAINT adr_assessment_audit_events_event_type_check CHECK (event_type IN (
    'marked_reviewed', 'dismissed', 'information_requested',
    'patient_information_provided', 'medwatch_draft_discarded'));

-- 6. RPCs. Each locks its row, re-checks the active care-team assignment and applies
-- the optimistic revision, as 048 does.

-- 048's create plus a caller-generated draft ID and the patient reference, which is the
-- Form 3500 A1 identifier stored in the same insert.
CREATE OR REPLACE FUNCTION public.create_medwatch_draft(
  p_assessment_id uuid,
  p_actor_id uuid,
  p_form_data jsonb,
  p_source_evidence jsonb,
  p_reportability_rationale text,
  p_draft_id uuid
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_draft public.medwatch_drafts%ROWTYPE;
  v_rationale text := NULLIF(btrim(COALESCE(p_reportability_rationale, '')), '');
  v_reference text := p_form_data #>> '{section_a,identifier}';
  v_now timestamptz := now();
BEGIN
  SELECT * INTO v_assessment
  FROM public.adr_assessments
  WHERE id = p_assessment_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ADR assessment not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_assessment.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_assessment.status <> 'draft' THEN
    RAISE EXCEPTION 'ADR assessment review has already been completed'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.medwatch_drafts
    WHERE adr_assessment_id = p_assessment_id AND discarded_at IS NULL
  ) THEN
    RAISE EXCEPTION 'A MedWatch draft already exists for this assessment'
      USING ERRCODE = '23514';
  END IF;
  IF v_rationale IS NULL THEN
    RAISE EXCEPTION 'A reportability rationale is required' USING ERRCODE = '22023';
  END IF;
  IF p_draft_id IS NULL
    OR jsonb_typeof(p_form_data) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_source_evidence) IS DISTINCT FROM 'array'
    OR p_form_data->>'form_version' IS DISTINCT FROM 'fda-3500-2025-09'
    OR v_reference IS NULL
    OR v_reference !~ '^[A-Z]{2}-[A-Z2-7]{4}$'
  THEN
    RAISE EXCEPTION 'Invalid Form 3500 draft payload' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.medwatch_drafts(
    id,
    adr_assessment_id,
    patient_id,
    form_data,
    source_evidence,
    patient_reference,
    created_by,
    created_at,
    updated_at
  ) VALUES (
    p_draft_id,
    p_assessment_id,
    v_assessment.patient_id,
    p_form_data,
    p_source_evidence,
    v_reference,
    p_actor_id,
    v_now,
    v_now
  ) RETURNING * INTO v_draft;

  UPDATE public.adr_assessments
  SET status = 'reviewed',
      reviewed_by = p_actor_id,
      reviewed_at = v_now,
      last_review_action = 'mark_reviewed',
      review_note = v_rationale,
      requested_information = '[]'::jsonb,
      updated_at = v_now
  WHERE id = p_assessment_id;

  UPDATE public.adr_information_requests
  SET status = 'cancelled', updated_at = v_now
  WHERE adr_assessment_id = p_assessment_id AND status = 'pending';

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    p_assessment_id,
    p_actor_id,
    'marked_reviewed',
    jsonb_build_object(
      'previous_status', v_assessment.status,
      'status', 'reviewed',
      'note', v_rationale,
      'medwatch_draft_id', v_draft.id
    )
  );

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    p_assessment_id,
    p_actor_id,
    'created',
    jsonb_build_object(
      'revision', v_draft.revision,
      'reportability_rationale', v_rationale,
      'form_version', 'fda-3500-2025-09'
    )
  );

  RETURN NEXT v_draft;
END;
$$;

-- 048's approve plus the attestation version, the non-serious attestation and the name
-- warnings the clinician acknowledged, all recorded in the approved event. A blank B4
-- (date of this report) becomes the approval date in America/Los_Angeles.
CREATE OR REPLACE FUNCTION public.approve_medwatch_draft(
  p_draft_id uuid,
  p_actor_id uuid,
  p_approval_note text,
  p_expected_revision integer,
  p_approval jsonb
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
  v_note text := NULLIF(btrim(COALESCE(p_approval_note, '')), '');
  v_form jsonb;
  v_report_date_set boolean := false;
  v_today text := to_char((now() AT TIME ZONE 'America/Los_Angeles')::date, 'YYYY-MM-DD');
BEGIN
  SELECT * INTO v_draft FROM public.medwatch_drafts
  WHERE id = p_draft_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_draft.discarded_at IS NOT NULL THEN
    RAISE EXCEPTION 'Discarded MedWatch drafts cannot be approved' USING ERRCODE = '23514';
  END IF;
  IF v_draft.status <> 'draft' THEN
    RAISE EXCEPTION 'MedWatch draft has already been approved' USING ERRCODE = '23514';
  END IF;
  IF v_draft.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'MedWatch draft changed; refresh before approval' USING ERRCODE = '40001';
  END IF;
  IF v_note IS NULL THEN
    RAISE EXCEPTION 'An approval note is required' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(p_approval) IS DISTINCT FROM 'object'
    OR p_approval->>'attestation_version' IS DISTINCT FROM 'medwatch-3500-approval-v1'
    OR jsonb_typeof(p_approval->'non_serious_attested') IS DISTINCT FROM 'boolean'
    OR jsonb_typeof(p_approval->'acknowledged_warnings') IS DISTINCT FROM 'array'
  THEN
    RAISE EXCEPTION 'Invalid MedWatch approval attestation' USING ERRCODE = '22023';
  END IF;

  v_form := v_draft.form_data;
  IF v_form->>'form_version' = 'fda-3500-2025-09'
    AND jsonb_typeof(v_form->'section_b') = 'object'
    AND COALESCE(v_form #>> '{section_b,report_date}', '') = ''
  THEN
    v_form := jsonb_set(v_form, '{section_b,report_date}', to_jsonb(v_today));
    v_report_date_set := true;
  END IF;

  UPDATE public.medwatch_drafts
  SET status = 'reviewed',
      form_data = v_form,
      approved_by = p_actor_id,
      approved_at = now(),
      approval_note = v_note,
      revision = revision + 1,
      updated_at = now()
  WHERE id = p_draft_id
  RETURNING * INTO v_draft;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'approved',
    jsonb_build_object(
      'revision', v_draft.revision,
      'approval_note', v_note,
      'attestation_version', p_approval->>'attestation_version',
      'non_serious_attested', p_approval->'non_serious_attested',
      'acknowledged_warnings', p_approval->'acknowledged_warnings',
      'report_date_set', v_report_date_set
    )
  );

  RETURN NEXT v_draft;
END;
$$;

-- Every export records its format; a PDF also records the template revision and SHA-256.
-- A recorded external submission keeps the draft exportable; a discarded draft is not.
CREATE OR REPLACE FUNCTION public.record_medwatch_draft_export(
  p_draft_id uuid,
  p_actor_id uuid,
  p_format text,
  p_template_revision text,
  p_template_sha256 text
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
BEGIN
  SELECT * INTO v_draft FROM public.medwatch_drafts
  WHERE id = p_draft_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_draft.discarded_at IS NOT NULL
    OR v_draft.approved_at IS NULL
    OR v_draft.status NOT IN ('reviewed', 'submitted')
  THEN
    RAISE EXCEPTION 'Only approved MedWatch drafts can be exported' USING ERRCODE = '23514';
  END IF;
  IF p_format IS NULL OR p_format NOT IN ('json', 'pdf')
    OR (p_format = 'pdf' AND (
      NULLIF(btrim(COALESCE(p_template_revision, '')), '') IS NULL
      OR COALESCE(p_template_sha256, '') !~ '^[0-9a-f]{64}$'
    ))
  THEN
    RAISE EXCEPTION 'Invalid MedWatch export format' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'exported',
    jsonb_build_object(
      'revision', v_draft.revision,
      'export_version', v_draft.export_version,
      'format', p_format
    ) || CASE WHEN p_format = 'pdf' THEN jsonb_build_object(
      'template_revision', p_template_revision,
      'template_sha256', p_template_sha256
    ) ELSE '{}'::jsonb END
  );

  RETURN NEXT v_draft;
END;
$$;

-- The 048 signature stays for callers deployed before this change: a JSON export.
CREATE OR REPLACE FUNCTION public.record_medwatch_draft_export(
  p_draft_id uuid,
  p_actor_id uuid
) RETURNS SETOF public.medwatch_drafts
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT * FROM public.record_medwatch_draft_export(p_draft_id, p_actor_id, 'json', NULL, NULL);
$$;

-- 7. Discard keeps the row, freezes it, and returns the assessment to review in the same
-- transaction. After 063 the assessment's own capture emits one clinician adr_review item
-- for the return to draft; no patient item becomes actionable (requests cancelled when the
-- draft was prepared stay cancelled) and adr_review maps to no email category.
CREATE OR REPLACE FUNCTION public.discard_medwatch_draft(
  p_draft_id uuid,
  p_actor_id uuid,
  p_reason text,
  p_expected_revision integer
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
  v_assessment public.adr_assessments%ROWTYPE;
  v_reason text := NULLIF(btrim(COALESCE(p_reason, '')), '');
  v_previous_status text;
  v_now timestamptz := now();
BEGIN
  -- Lock the assessment before the draft, in the same order as create.
  SELECT * INTO v_draft FROM public.medwatch_drafts WHERE id = p_draft_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  SELECT * INTO v_assessment FROM public.adr_assessments
  WHERE id = v_draft.adr_assessment_id FOR UPDATE;
  SELECT * INTO v_draft FROM public.medwatch_drafts
  WHERE id = p_draft_id FOR UPDATE;

  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_draft.discarded_at IS NOT NULL THEN
    RAISE EXCEPTION 'MedWatch draft has already been discarded' USING ERRCODE = '23514';
  END IF;
  IF v_draft.status = 'submitted' OR EXISTS (
    SELECT 1 FROM public.medwatch_external_submissions WHERE medwatch_draft_id = p_draft_id
  ) THEN
    RAISE EXCEPTION 'A submitted MedWatch draft cannot be discarded' USING ERRCODE = '23514';
  END IF;
  IF v_draft.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'MedWatch draft changed; refresh before discarding' USING ERRCODE = '40001';
  END IF;
  IF v_reason IS NULL OR char_length(v_reason) > 2000 THEN
    RAISE EXCEPTION 'A discard reason of 1 to 2000 characters is required'
      USING ERRCODE = '22023';
  END IF;

  v_previous_status := v_draft.status::text;
  UPDATE public.medwatch_drafts
  SET discarded_at = v_now,
      discarded_by = p_actor_id,
      discard_reason = v_reason,
      revision = revision + 1,
      updated_at = v_now
  WHERE id = p_draft_id
  RETURNING * INTO v_draft;

  UPDATE public.adr_assessments
  SET status = 'draft',
      last_review_action = NULL,
      reviewed_by = NULL,
      reviewed_at = NULL,
      updated_at = v_now
  WHERE id = v_draft.adr_assessment_id;

  INSERT INTO public.adr_assessment_audit_events(
    adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.adr_assessment_id,
    p_actor_id,
    'medwatch_draft_discarded',
    jsonb_build_object(
      'previous_status', v_assessment.status,
      'status', 'draft',
      'medwatch_draft_id', v_draft.id,
      'reason', v_reason
    )
  );

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'discarded',
    jsonb_build_object(
      'reason', v_reason,
      'previous_status', v_previous_status,
      'revision', v_draft.revision
    )
  );

  RETURN NEXT v_draft;
END;
$$;

-- Records that the clinician submitted the approved form to FDA themselves. The date is
-- not after today and not before the approval date (America/Los_Angeles).
CREATE OR REPLACE FUNCTION public.record_medwatch_external_submission(
  p_draft_id uuid,
  p_actor_id uuid,
  p_submitted_on date,
  p_method text,
  p_method_detail text,
  p_fda_reference text,
  p_attested boolean,
  p_expected_revision integer
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
  v_detail text := NULLIF(btrim(COALESCE(p_method_detail, '')), '');
  v_reference text := NULLIF(btrim(COALESCE(p_fda_reference, '')), '');
  v_today date := (now() AT TIME ZONE 'America/Los_Angeles')::date;
  v_submission_id uuid;
BEGIN
  SELECT * INTO v_draft FROM public.medwatch_drafts
  WHERE id = p_draft_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_draft.discarded_at IS NOT NULL
    OR v_draft.status <> 'reviewed'
    OR v_draft.approved_at IS NULL
    OR EXISTS (
      SELECT 1 FROM public.medwatch_external_submissions WHERE medwatch_draft_id = p_draft_id
    )
  THEN
    RAISE EXCEPTION 'Only an approved draft without a submission record can be recorded'
      USING ERRCODE = '23514';
  END IF;
  IF v_draft.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'MedWatch draft changed; refresh before recording' USING ERRCODE = '40001';
  END IF;
  IF p_attested IS NOT TRUE
    OR p_submitted_on IS NULL
    OR p_submitted_on > v_today
    OR p_submitted_on < (v_draft.approved_at AT TIME ZONE 'America/Los_Angeles')::date
    OR p_method IS NULL OR p_method NOT IN ('medwatch_online', 'fax', 'mail', 'other')
    OR (p_method = 'other' AND v_detail IS NULL)
    OR char_length(COALESCE(v_detail, '')) > 500
    OR char_length(COALESCE(v_reference, '')) > 100
  THEN
    RAISE EXCEPTION 'Invalid MedWatch submission record' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.medwatch_external_submissions(
    medwatch_draft_id, adr_assessment_id, patient_id, recorded_by, submitted_on, method,
    method_detail, fda_reference, attested
  ) VALUES (
    v_draft.id, v_draft.adr_assessment_id, v_draft.patient_id, p_actor_id, p_submitted_on,
    p_method, v_detail, v_reference, true
  ) RETURNING id INTO v_submission_id;

  UPDATE public.medwatch_drafts
  SET status = 'submitted',
      submitted_at = now(),
      revision = revision + 1,
      updated_at = now()
  WHERE id = p_draft_id
  RETURNING * INTO v_draft;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'submission_recorded',
    jsonb_build_object(
      'submission_id', v_submission_id,
      'submitted_on', p_submitted_on,
      'method', p_method,
      'revision', v_draft.revision
    )
  );

  RETURN NEXT v_draft;
END;
$$;

-- Corrects the current submission record with a new row; the original is kept. An
-- amendment carries forward the attestation of the submission it corrects.
CREATE OR REPLACE FUNCTION public.amend_medwatch_external_submission(
  p_draft_id uuid,
  p_actor_id uuid,
  p_amends_id uuid,
  p_submitted_on date,
  p_method text,
  p_method_detail text,
  p_fda_reference text,
  p_reason text
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
  v_current public.medwatch_external_submissions%ROWTYPE;
  v_detail text := NULLIF(btrim(COALESCE(p_method_detail, '')), '');
  v_reference text := NULLIF(btrim(COALESCE(p_fda_reference, '')), '');
  v_reason text := NULLIF(btrim(COALESCE(p_reason, '')), '');
  v_today date := (now() AT TIME ZONE 'America/Los_Angeles')::date;
  v_submission_id uuid;
BEGIN
  SELECT * INTO v_draft FROM public.medwatch_drafts
  WHERE id = p_draft_id FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'MedWatch draft not found' USING ERRCODE = 'P0002';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.care_teams
    WHERE clinician_id = p_actor_id
      AND patient_id = v_draft.patient_id
      AND status = 'active'
  ) THEN
    RAISE EXCEPTION 'Clinician is not assigned to this patient' USING ERRCODE = '42501';
  END IF;
  IF v_draft.status <> 'submitted' THEN
    RAISE EXCEPTION 'Only a recorded submission can be amended' USING ERRCODE = '23514';
  END IF;

  SELECT * INTO v_current FROM public.medwatch_external_submissions s
  WHERE s.medwatch_draft_id = p_draft_id
    AND NOT EXISTS (
      SELECT 1 FROM public.medwatch_external_submissions a WHERE a.amends_id = s.id
    );
  IF NOT FOUND OR v_current.id IS DISTINCT FROM p_amends_id THEN
    RAISE EXCEPTION 'The submission record changed; refresh before amending'
      USING ERRCODE = '40001';
  END IF;
  IF v_reason IS NULL OR char_length(v_reason) > 2000
    OR p_submitted_on IS NULL
    OR p_submitted_on > v_today
    OR p_submitted_on < (v_draft.approved_at AT TIME ZONE 'America/Los_Angeles')::date
    OR p_method IS NULL OR p_method NOT IN ('medwatch_online', 'fax', 'mail', 'other')
    OR (p_method = 'other' AND v_detail IS NULL)
    OR char_length(COALESCE(v_detail, '')) > 500
    OR char_length(COALESCE(v_reference, '')) > 100
  THEN
    RAISE EXCEPTION 'Invalid MedWatch submission amendment' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.medwatch_external_submissions(
    medwatch_draft_id, adr_assessment_id, patient_id, recorded_by, submitted_on, method,
    method_detail, fda_reference, attested, amends_id, amend_reason
  ) VALUES (
    v_draft.id, v_draft.adr_assessment_id, v_draft.patient_id, p_actor_id, p_submitted_on,
    p_method, v_detail, v_reference, v_current.attested, v_current.id, v_reason
  ) RETURNING id INTO v_submission_id;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'submission_amended',
    jsonb_build_object(
      'submission_id', v_submission_id,
      'amends_id', v_current.id,
      'reason', v_reason,
      'submitted_on', p_submitted_on,
      'method', p_method
    )
  );

  RETURN NEXT v_draft;
END;
$$;

-- 8. Grants: every MedWatch RPC is service_role only; no role deletes audit or
-- submission history.
REVOKE ALL ON FUNCTION
  public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid),
  public.approve_medwatch_draft(uuid, uuid, text, integer, jsonb),
  public.record_medwatch_draft_export(uuid, uuid, text, text, text),
  public.record_medwatch_draft_export(uuid, uuid),
  public.discard_medwatch_draft(uuid, uuid, text, integer),
  public.record_medwatch_external_submission(uuid, uuid, date, text, text, text, boolean, integer),
  public.amend_medwatch_external_submission(uuid, uuid, uuid, date, text, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text, uuid),
  public.approve_medwatch_draft(uuid, uuid, text, integer, jsonb),
  public.record_medwatch_draft_export(uuid, uuid, text, text, text),
  public.record_medwatch_draft_export(uuid, uuid),
  public.discard_medwatch_draft(uuid, uuid, text, integer),
  public.record_medwatch_external_submission(uuid, uuid, date, text, text, text, boolean, integer),
  public.amend_medwatch_external_submission(uuid, uuid, uuid, date, text, text, text, text)
  TO service_role;
REVOKE ALL ON FUNCTION
  private.medwatch_drafts_export_version(),
  private.medwatch_drafts_submission_guard(),
  private.medwatch_submissions_append_only()
  FROM PUBLIC, anon, authenticated, service_role;
REVOKE DELETE, TRUNCATE ON public.adr_assessment_audit_events,
  public.medwatch_draft_audit_events, public.medwatch_external_submissions
  FROM PUBLIC, anon, authenticated, service_role;

-- 9. Fail the migration rather than leave a draft per assessment for ever, an unguarded
-- submitted status, a browser role that can call a MedWatch RPC, writable submission
-- history, a new patient reference that blocks deletion, or a 048 export that records
-- no format.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_indexes
    WHERE schemaname = 'public' AND indexname = 'idx_medwatch_one_draft_per_assessment'
      AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%WHERE (discarded_at IS NULL)%'
  ) THEN
    RAISE EXCEPTION 'One non-discarded MedWatch draft per assessment is not enforced';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger
    WHERE tgrelid = 'public.medwatch_drafts'::regclass
      AND tgname = 'medwatch_drafts_submission_guard' AND NOT tgisinternal
  ) OR NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_trigger
    WHERE tgrelid = 'public.medwatch_external_submissions'::regclass
      AND tgname = 'medwatch_submissions_append_only' AND NOT tgisinternal
  ) THEN
    RAISE EXCEPTION 'The MedWatch submission guards are missing';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY[
      'public.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text)',
      'public.create_medwatch_draft(uuid,uuid,jsonb,jsonb,text,uuid)',
      'public.update_medwatch_draft(uuid,uuid,jsonb,jsonb,integer)',
      'public.approve_medwatch_draft(uuid,uuid,text,integer)',
      'public.approve_medwatch_draft(uuid,uuid,text,integer,jsonb)',
      'public.record_medwatch_draft_export(uuid,uuid)',
      'public.record_medwatch_draft_export(uuid,uuid,text,text,text)',
      'public.discard_medwatch_draft(uuid,uuid,text,integer)',
      'public.record_medwatch_external_submission(uuid,uuid,date,text,text,text,boolean,integer)',
      'public.amend_medwatch_external_submission(uuid,uuid,uuid,date,text,text,text,text)'
    ]) f(name)
    CROSS JOIN unnest(ARRAY['anon', 'authenticated']) r(role)
    WHERE pg_catalog.has_function_privilege(r.role, f.name, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'Browser roles may not call a MedWatch RPC';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(ARRAY['anon', 'authenticated', 'service_role']) r(role)
    WHERE pg_catalog.has_table_privilege(r.role, 'public.medwatch_external_submissions', 'UPDATE')
      OR pg_catalog.has_table_privilege(r.role, 'public.medwatch_external_submissions', 'DELETE')
      OR pg_catalog.has_table_privilege(r.role, 'public.medwatch_external_submissions', 'TRUNCATE')
      OR pg_catalog.has_table_privilege(r.role, 'public.medwatch_external_submissions', 'INSERT')
  ) THEN
    RAISE EXCEPTION 'No role may write MedWatch submission history directly';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint c
    WHERE c.contype = 'f' AND c.confdeltype <> 'c'
      AND c.conrelid = 'public.medwatch_external_submissions'::regclass
      AND c.confrelid IN ('public.patients'::regclass, 'public.adr_assessments'::regclass,
        'public.medwatch_drafts'::regclass, 'public.medwatch_external_submissions'::regclass)
  ) THEN
    RAISE EXCEPTION 'A MedWatch submission patient reference blocks patient deletion';
  END IF;
  IF position('public.record_medwatch_draft_export(p_draft_id, p_actor_id, ''json''' IN
    pg_catalog.pg_get_functiondef('public.record_medwatch_draft_export(uuid,uuid)'::regprocedure)) = 0
  THEN
    RAISE EXCEPTION 'The 048 export signature must record a JSON export through the new one';
  END IF;
END $$;
