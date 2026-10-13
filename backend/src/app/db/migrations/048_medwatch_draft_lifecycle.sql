-- Clinician-controlled MedWatch draft preparation, approval, and export.
-- This migration deliberately does not create an FDA submission operation.

ALTER TABLE public.medwatch_drafts
  ADD COLUMN IF NOT EXISTS source_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS clinician_edited_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS approved_by uuid REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS approved_at timestamptz,
  ADD COLUMN IF NOT EXISTS approval_note text,
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS export_version text NOT NULL DEFAULT 'medwatch-3500a-draft-v1';

ALTER TABLE public.medwatch_drafts
  DROP CONSTRAINT IF EXISTS medwatch_drafts_form_data_object,
  DROP CONSTRAINT IF EXISTS medwatch_drafts_source_evidence_array,
  DROP CONSTRAINT IF EXISTS medwatch_drafts_edited_fields_array,
  DROP CONSTRAINT IF EXISTS medwatch_drafts_revision_positive,
  DROP CONSTRAINT IF EXISTS medwatch_drafts_approval_consistency,
  DROP CONSTRAINT IF EXISTS medwatch_drafts_not_submitted_by_app;

ALTER TABLE public.medwatch_drafts
  ADD CONSTRAINT medwatch_drafts_form_data_object
    CHECK (jsonb_typeof(form_data) = 'object'),
  ADD CONSTRAINT medwatch_drafts_source_evidence_array
    CHECK (jsonb_typeof(source_evidence) = 'array'),
  ADD CONSTRAINT medwatch_drafts_edited_fields_array
    CHECK (jsonb_typeof(clinician_edited_fields) = 'array'),
  ADD CONSTRAINT medwatch_drafts_revision_positive CHECK (revision > 0),
  ADD CONSTRAINT medwatch_drafts_approval_consistency CHECK (
    status = 'submitted'
    OR (status = 'draft' AND approved_by IS NULL AND approved_at IS NULL)
    OR (status = 'reviewed' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
  ) NOT VALID,
  ADD CONSTRAINT medwatch_drafts_not_submitted_by_app CHECK (
    status = 'submitted' OR submitted_at IS NULL
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_medwatch_one_draft_per_assessment
  ON public.medwatch_drafts(adr_assessment_id);
CREATE INDEX IF NOT EXISTS idx_medwatch_patient_created
  ON public.medwatch_drafts(patient_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.medwatch_draft_audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  medwatch_draft_id uuid NOT NULL
    REFERENCES public.medwatch_drafts(id) ON DELETE CASCADE,
  adr_assessment_id uuid NOT NULL
    REFERENCES public.adr_assessments(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES public.clinicians(id) ON DELETE RESTRICT,
  event_type text NOT NULL
    CHECK (event_type IN ('created', 'edited', 'approved', 'exported')),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(event_data) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_medwatch_audit_draft_created
  ON public.medwatch_draft_audit_events(medwatch_draft_id, created_at ASC);

ALTER TABLE public.medwatch_draft_audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS medwatch_clinician_update ON public.medwatch_drafts;
DROP POLICY IF EXISTS medwatch_clinician_select ON public.medwatch_drafts;
CREATE POLICY medwatch_clinician_select
  ON public.medwatch_drafts FOR SELECT TO authenticated
  USING (
    private.is_clinician()
    AND private.is_assigned_clinician(patient_id)
  );

DROP POLICY IF EXISTS medwatch_audit_clinician_select
  ON public.medwatch_draft_audit_events;
CREATE POLICY medwatch_audit_clinician_select
  ON public.medwatch_draft_audit_events FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM public.medwatch_drafts draft
      WHERE draft.id = medwatch_draft_audit_events.medwatch_draft_id
        AND private.is_clinician()
        AND private.is_assigned_clinician(draft.patient_id)
    )
  );

REVOKE ALL ON TABLE public.medwatch_drafts FROM anon, authenticated;
GRANT SELECT ON TABLE public.medwatch_drafts TO authenticated;
GRANT ALL ON TABLE public.medwatch_drafts TO service_role;
REVOKE ALL ON TABLE public.medwatch_draft_audit_events FROM anon, authenticated;
GRANT SELECT ON TABLE public.medwatch_draft_audit_events TO authenticated;
GRANT ALL ON TABLE public.medwatch_draft_audit_events TO service_role;

CREATE OR REPLACE FUNCTION public.create_medwatch_draft(
  p_assessment_id uuid,
  p_actor_id uuid,
  p_form_data jsonb,
  p_source_evidence jsonb,
  p_reportability_rationale text
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_assessment public.adr_assessments%ROWTYPE;
  v_draft public.medwatch_drafts%ROWTYPE;
  v_rationale text := NULLIF(btrim(COALESCE(p_reportability_rationale, '')), '');
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
  IF v_rationale IS NULL THEN
    RAISE EXCEPTION 'A reportability rationale is required' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(p_form_data) <> 'object'
    OR jsonb_typeof(p_source_evidence) <> 'array'
  THEN
    RAISE EXCEPTION 'Invalid MedWatch draft payload' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.medwatch_drafts(
    adr_assessment_id,
    patient_id,
    form_data,
    source_evidence,
    created_by,
    created_at,
    updated_at
  ) VALUES (
    p_assessment_id,
    v_assessment.patient_id,
    p_form_data,
    p_source_evidence,
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
      'reportability_rationale', v_rationale
    )
  );

  RETURN NEXT v_draft;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_medwatch_draft(
  p_draft_id uuid,
  p_actor_id uuid,
  p_form_data jsonb,
  p_changed_fields jsonb,
  p_expected_revision integer
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
  IF v_draft.status <> 'draft' THEN
    RAISE EXCEPTION 'Approved MedWatch drafts cannot be edited' USING ERRCODE = '23514';
  END IF;
  IF v_draft.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'MedWatch draft changed; refresh before saving' USING ERRCODE = '40001';
  END IF;
  IF jsonb_typeof(p_form_data) <> 'object'
    OR jsonb_typeof(p_changed_fields) <> 'array'
  THEN
    RAISE EXCEPTION 'Invalid MedWatch draft update payload' USING ERRCODE = '22023';
  END IF;

  UPDATE public.medwatch_drafts
  SET form_data = p_form_data,
      clinician_edited_fields = (
        SELECT COALESCE(jsonb_agg(DISTINCT item.value), '[]'::jsonb)
        FROM jsonb_array_elements(clinician_edited_fields || p_changed_fields) AS item(value)
      ),
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
    'edited',
    jsonb_build_object('revision', v_draft.revision, 'changed_fields', p_changed_fields)
  );

  RETURN NEXT v_draft;
END;
$$;

CREATE OR REPLACE FUNCTION public.approve_medwatch_draft(
  p_draft_id uuid,
  p_actor_id uuid,
  p_approval_note text,
  p_expected_revision integer
) RETURNS SETOF public.medwatch_drafts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_draft public.medwatch_drafts%ROWTYPE;
  v_note text := NULLIF(btrim(COALESCE(p_approval_note, '')), '');
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
  IF v_draft.status <> 'draft' THEN
    RAISE EXCEPTION 'MedWatch draft has already been approved' USING ERRCODE = '23514';
  END IF;
  IF v_draft.revision <> p_expected_revision THEN
    RAISE EXCEPTION 'MedWatch draft changed; refresh before approval' USING ERRCODE = '40001';
  END IF;
  IF v_note IS NULL THEN
    RAISE EXCEPTION 'An approval note is required' USING ERRCODE = '22023';
  END IF;

  UPDATE public.medwatch_drafts
  SET status = 'reviewed',
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
    jsonb_build_object('revision', v_draft.revision, 'approval_note', v_note)
  );

  RETURN NEXT v_draft;
END;
$$;

CREATE OR REPLACE FUNCTION public.record_medwatch_draft_export(
  p_draft_id uuid,
  p_actor_id uuid
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
  IF v_draft.status <> 'reviewed' OR v_draft.approved_at IS NULL THEN
    RAISE EXCEPTION 'Only approved MedWatch drafts can be exported' USING ERRCODE = '23514';
  END IF;

  INSERT INTO public.medwatch_draft_audit_events(
    medwatch_draft_id, adr_assessment_id, actor_id, event_type, event_data
  ) VALUES (
    v_draft.id,
    v_draft.adr_assessment_id,
    p_actor_id,
    'exported',
    jsonb_build_object('revision', v_draft.revision, 'export_version', v_draft.export_version)
  );

  RETURN NEXT v_draft;
END;
$$;

REVOKE ALL ON FUNCTION public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.update_medwatch_draft(uuid, uuid, jsonb, jsonb, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.approve_medwatch_draft(uuid, uuid, text, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_medwatch_draft_export(uuid, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_medwatch_draft(uuid, uuid, jsonb, jsonb, text)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.update_medwatch_draft(uuid, uuid, jsonb, jsonb, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.approve_medwatch_draft(uuid, uuid, text, integer)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.record_medwatch_draft_export(uuid, uuid)
  TO service_role;

COMMENT ON TABLE public.medwatch_drafts IS
  'Editable clinician-approved MedWatch-compatible artifacts; not FDA submissions.';
COMMENT ON TABLE public.medwatch_draft_audit_events IS
  'Immutable creation, edit, approval, and export history for MedWatch drafts.';
