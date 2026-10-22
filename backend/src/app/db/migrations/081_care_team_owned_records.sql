-- PLAN-002 / CLN-003 slice G: shared clinical core and care-team-owned records.
--
-- Shared with every care team of the patient, with the recording team and clinic:
--   medications, allergies, and conditions the patient has not marked sensitive.
-- Visible only to the recording care team: conditions the patient marks sensitive. Other
--   clinicians are told that some conditions are private; they never see a quietly shorter
--   list. A sensitive condition with no recorded team is visible to no clinician.
-- Owned by one care team: documents (and the facts extracted from them), the plan, SOAP
--   notes, reviewed ADR assessments and their MedWatch drafts, FHIR imports.
--
-- A patient upload either names a care team or says "Not sure". A "Not sure" document is
-- listed for every active care team of the patient until one clinician claims the whole
-- document; the claim is atomic, audited and has exactly one winner.
--
-- Every browser role is revoked from new objects; the final block fails the migration if a
-- grant or RLS setting is wrong. Nothing here rewrites an existing id or removes data.

-- ── 1. Access helpers ─────────────────────────────────────────────────────────────────────

-- The active links a clinician holds to a patient. This is the read gate: a clinician sees
-- a patient only through a link of their own (CLN-003 slice A).
CREATE FUNCTION private.clinician_patient_links(p_clinician_id uuid, p_patient_id uuid)
RETURNS uuid[] LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT COALESCE(array_agg(t.id ORDER BY t.id), ARRAY[]::uuid[])
    FROM public.care_teams t
   WHERE t.clinician_id = p_clinician_id AND t.patient_id = p_patient_id
     AND t.status = 'active';
$$;

-- A routed document belongs to its link. An unrouted one is in every active team's queue.
CREATE FUNCTION private.document_visible_to_links(
  p_routing_state text, p_care_team_id uuid, p_links uuid[]
) RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
  SELECT COALESCE(cardinality(p_links), 0) > 0
     AND (p_routing_state = 'unrouted' OR p_care_team_id = ANY (p_links));
$$;

-- ── 2. Documents: owner, routing state and audit ──────────────────────────────────────────

ALTER TABLE public.documents
  ADD COLUMN care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  ADD COLUMN routing_state text NOT NULL DEFAULT 'routed'
    CHECK (routing_state IN ('routed', 'unrouted')),
  ADD COLUMN claimed_by uuid,
  ADD COLUMN claimed_at timestamptz,
  ADD CONSTRAINT documents_unrouted_has_no_owner
    CHECK (routing_state = 'routed' OR care_team_id IS NULL);
CREATE INDEX documents_care_team ON public.documents(care_team_id) WHERE care_team_id IS NOT NULL;
CREATE INDEX documents_unrouted ON public.documents(patient_id) WHERE routing_state = 'unrouted';

-- Plain uuid columns and no cascades: the routing trail survives account deletion.
CREATE TABLE public.document_routing_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL,
  document_id uuid NOT NULL,
  actor_id uuid,
  from_care_team_id uuid,
  to_care_team_id uuid,
  event_type text NOT NULL CHECK (event_type IN (
    'routed_on_upload', 'left_unrouted', 'claimed', 'backfill_routed', 'backfill_unrouted')),
  event_data jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(event_data) = 'object'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX document_routing_events_document
  ON public.document_routing_events(document_id, created_at);
CREATE TRIGGER document_routing_events_append_only
  BEFORE UPDATE OR DELETE ON public.document_routing_events
  FOR EACH ROW EXECUTE FUNCTION private.care_plan_append_only();
CREATE TRIGGER document_routing_events_no_truncate
  BEFORE TRUNCATE ON public.document_routing_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_plan_append_only();

-- Backfill: a document goes to its owner only when that is unambiguous. A clinician's
-- upload goes to that clinician's only link to the patient; a patient's upload goes to the
-- patient's only care team. Anything else becomes "unrouted", which is exactly what every
-- team could already see, and which any of them can claim.
DO $backfill$
DECLARE
  v_doc record;
  v_team uuid;
  v_count integer;
BEGIN
  PERFORM set_config('mediagent.document_routing', '1', true);
  FOR v_doc IN SELECT id, patient_id, uploaded_by, uploaded_by_role FROM public.documents ORDER BY id LOOP
    v_team := NULL;
    IF v_doc.uploaded_by_role = 'clinician' THEN
      SELECT count(*), (array_agg(id))[1] INTO v_count, v_team FROM public.care_teams
        WHERE patient_id = v_doc.patient_id AND clinician_id = v_doc.uploaded_by;
    ELSE
      SELECT count(*), (array_agg(id))[1] INTO v_count, v_team FROM public.care_teams
        WHERE patient_id = v_doc.patient_id;
    END IF;
    IF v_count = 1 THEN
      UPDATE public.documents SET care_team_id = v_team, routing_state = 'routed'
        WHERE id = v_doc.id;
      INSERT INTO public.document_routing_events(patient_id, document_id, to_care_team_id,
        event_type, event_data)
      VALUES (v_doc.patient_id, v_doc.id, v_team, 'backfill_routed',
        jsonb_build_object('basis', CASE WHEN v_doc.uploaded_by_role = 'clinician'
          THEN 'uploader_single_link' ELSE 'patient_single_care_team' END));
    ELSE
      UPDATE public.documents SET care_team_id = NULL, routing_state = 'unrouted'
        WHERE id = v_doc.id;
      INSERT INTO public.document_routing_events(patient_id, document_id, event_type, event_data)
      VALUES (v_doc.patient_id, v_doc.id, 'backfill_unrouted',
        jsonb_build_object('reason', 'owner_not_determinable'));
    END IF;
  END LOOP;
END;
$backfill$;

-- Routing is decided at upload and changed only by the claim function below.
CREATE FUNCTION private.document_routing_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_link public.care_teams%ROWTYPE;
  v_links uuid[];
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.care_team_id IS NOT DISTINCT FROM OLD.care_team_id
       AND NEW.routing_state IS NOT DISTINCT FROM OLD.routing_state
       AND NEW.claimed_by IS NOT DISTINCT FROM OLD.claimed_by THEN
      RETURN NEW;
    END IF;
    -- The foreign key clearing a deleted link leaves the document with no owner at all:
    -- it stays routed, so no other team can see it.
    IF NEW.routing_state = 'routed' AND NEW.care_team_id IS NULL AND OLD.care_team_id IS NOT NULL
       AND OLD.routing_state = 'routed' AND NEW.claimed_by IS NOT DISTINCT FROM OLD.claimed_by THEN
      RETURN NEW;
    END IF;
    IF COALESCE(current_setting('mediagent.document_routing', true), '') <> '1' THEN
      RAISE EXCEPTION 'document routing changes only through routing or claiming'
        USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  END IF;
  -- INSERT: a named team must be a live link of this patient (and of the clinician who
  -- uploads). No name means "work it out", which stays unambiguous or becomes unrouted.
  IF NEW.care_team_id IS NOT NULL THEN
    SELECT * INTO v_link FROM public.care_teams WHERE id = NEW.care_team_id;
    IF NOT FOUND OR v_link.patient_id IS DISTINCT FROM NEW.patient_id OR v_link.status <> 'active'
       OR (NEW.uploaded_by_role = 'clinician' AND v_link.clinician_id <> NEW.uploaded_by) THEN
      RAISE EXCEPTION 'choose one of your own care teams for this document'
        USING ERRCODE = '42501';
    END IF;
    NEW.routing_state := 'routed';
    RETURN NEW;
  END IF;
  IF NEW.routing_state = 'unrouted' THEN
    IF NEW.uploaded_by_role = 'clinician' THEN
      RAISE EXCEPTION 'a clinician upload belongs to the clinician''s own care team'
        USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
  END IF;
  IF NEW.uploaded_by_role = 'clinician' THEN
    v_links := private.clinician_patient_links(NEW.uploaded_by, NEW.patient_id);
  ELSE
    SELECT COALESCE(array_agg(id), ARRAY[]::uuid[]) INTO v_links FROM public.care_teams
      WHERE patient_id = NEW.patient_id AND status = 'active';
  END IF;
  IF cardinality(v_links) = 1 THEN
    NEW.care_team_id := v_links[1];
    NEW.routing_state := 'routed';
  ELSIF NEW.uploaded_by_role = 'clinician' THEN
    RAISE EXCEPTION 'choose which care team this document belongs to' USING ERRCODE = '22023';
  ELSE
    NEW.care_team_id := NULL;
    NEW.routing_state := 'unrouted';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER documents_routing_guard
  BEFORE INSERT OR UPDATE OF care_team_id, routing_state, claimed_by ON public.documents
  FOR EACH ROW EXECUTE FUNCTION private.document_routing_guard();

CREATE FUNCTION private.log_document_routing_on_upload() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  INSERT INTO public.document_routing_events(patient_id, document_id, actor_id,
    to_care_team_id, event_type, event_data)
  VALUES (NEW.patient_id, NEW.id, NEW.uploaded_by, NEW.care_team_id,
    CASE WHEN NEW.routing_state = 'routed' THEN 'routed_on_upload' ELSE 'left_unrouted' END,
    jsonb_build_object('uploaded_by_role', NEW.uploaded_by_role));
  RETURN NEW;
END;
$$;
CREATE TRIGGER documents_log_routing
  AFTER INSERT ON public.documents
  FOR EACH ROW EXECUTE FUNCTION private.log_document_routing_on_upload();

-- True when an accepted document has medication or activity evidence worth drafting.
CREATE FUNCTION private.document_ready_for_drafting(p_document_id uuid) RETURNS boolean
LANGUAGE sql SET search_path = '' AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.documents d
    JOIN public.source_provenances p ON p.document_id = d.id AND p.withdrawn_at IS NULL
    JOIN public.evidence_citations c ON c.provenance_id = p.id
    JOIN public.clinical_facts f ON f.id = c.fact_id
    WHERE d.id = p_document_id AND d.parse_status = 'completed'
      AND (d.uploaded_by_role = 'clinician'
        OR (d.uploaded_by_role = 'patient' AND d.review_status = 'approved'))
      AND f.patient_id = d.patient_id AND f.fact_type IN ('medication', 'obligation')
      AND private.care_plan_fact_is_eligible(d.patient_id, f.id));
$$;

-- Claim a "Not sure" document for one care team. Authorization first, then the patient
-- fence, then the document row. One caller wins; a repeat by the winner is a success.
CREATE FUNCTION public.claim_document(
  p_document_id uuid, p_actor_id uuid, p_care_team_id uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_doc public.documents%ROWTYPE;
  v_patient uuid;
BEGIN
  SELECT patient_id INTO v_patient FROM public.documents WHERE id = p_document_id;
  IF NOT FOUND OR NOT private.clinician_holds_link(p_actor_id, p_care_team_id)
     OR NOT EXISTS (SELECT 1 FROM public.care_teams
       WHERE id = p_care_team_id AND patient_id = v_patient) THEN
    RAISE EXCEPTION 'document unavailable' USING ERRCODE = '42501';
  END IF;
  PERFORM private.lock_care_plan_evidence(v_patient, true);
  SELECT * INTO v_doc FROM public.documents WHERE id = p_document_id FOR UPDATE;
  IF NOT private.clinician_holds_link(p_actor_id, p_care_team_id) THEN
    RAISE EXCEPTION 'document unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_doc.routing_state <> 'unrouted' THEN
    IF v_doc.care_team_id = p_care_team_id AND v_doc.claimed_by = p_actor_id THEN
      RETURN jsonb_build_object('document_id', v_doc.id, 'care_team_id', p_care_team_id,
        'status', 'claimed', 'replayed', true);
    END IF;
    RAISE EXCEPTION 'document was claimed by someone else' USING ERRCODE = '40001';
  END IF;
  PERFORM set_config('mediagent.document_routing', '1', true);
  UPDATE public.documents
     SET care_team_id = p_care_team_id, routing_state = 'routed',
         claimed_by = p_actor_id, claimed_at = clock_timestamp()
   WHERE id = v_doc.id;
  INSERT INTO public.document_routing_events(patient_id, document_id, actor_id,
    to_care_team_id, event_type, event_data)
  VALUES (v_doc.patient_id, v_doc.id, p_actor_id, p_care_team_id, 'claimed',
    jsonb_build_object('whole_document', true));
  -- Drafting follows the document: the claiming team's plan, never another team's.
  IF private.document_ready_for_drafting(v_doc.id) THEN
    PERFORM public.request_care_plan_generation_for_plan(
      private.ensure_care_plan(p_care_team_id), clock_timestamp());
  END IF;
  RETURN jsonb_build_object('document_id', v_doc.id, 'care_team_id', p_care_team_id,
    'status', 'claimed', 'replayed', false);
END;
$$;

-- Approving an accepted upload wakes drafting for the document's own plan only (048 woke
-- the patient's one plan). An unrouted document wakes nothing until it is claimed.
CREATE OR REPLACE FUNCTION public.queue_accepted_document_care_plan() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.uploaded_by_role = 'patient' AND NEW.review_status = 'approved'
    AND OLD.review_status IS DISTINCT FROM 'approved' AND NEW.parse_status = 'completed'
    AND NEW.routing_state = 'routed' AND NEW.care_team_id IS NOT NULL
    AND private.document_ready_for_drafting(NEW.id) THEN
    PERFORM public.request_care_plan_generation_for_plan(
      private.ensure_care_plan(NEW.care_team_id), clock_timestamp());
  END IF;
  RETURN NEW;
END;
$$;

-- Drafting after ingestion completes: the plan of the document's team (Python calls this).
CREATE FUNCTION public.request_care_plan_generation_for_document(
  p_document_id uuid, p_source_watermark timestamptz
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_doc public.documents%ROWTYPE;
BEGIN
  SELECT * INTO v_doc FROM public.documents WHERE id = p_document_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'document not found'; END IF;
  IF v_doc.routing_state <> 'routed' OR v_doc.care_team_id IS NULL THEN
    RETURN jsonb_build_object('request_id', NULL, 'status', 'document_unrouted');
  END IF;
  RETURN public.request_care_plan_generation_for_plan(
    private.ensure_care_plan(v_doc.care_team_id), p_source_watermark);
END;
$$;

-- ── 3. Facts inherit the owner of their sources ───────────────────────────────────────────
-- A fact extracted from a routed document belongs to that document's team. A fact from
-- anything else (a clinician entry, an import) carries its own team on the provenance row;
-- no team there means "as shared as it was before this migration".

ALTER TABLE public.source_provenances
  ADD COLUMN care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL;
ALTER TABLE public.fhir_imports
  ADD COLUMN care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL;

-- Imports and clinician entries belong to the importing clinician's only link to the patient.
UPDATE public.fhir_imports i SET care_team_id = (
  SELECT t.id FROM public.care_teams t
   WHERE t.patient_id = i.patient_id AND t.clinician_id = i.clinician_id)
 WHERE (SELECT count(*) FROM public.care_teams t
   WHERE t.patient_id = i.patient_id AND t.clinician_id = i.clinician_id) = 1;
UPDATE public.source_provenances p SET care_team_id = i.care_team_id
  FROM public.fhir_import_resources r, public.fhir_imports i
 WHERE p.artifact_type = 'fhir_resource' AND p.care_team_id IS NULL
   AND i.id = r.import_id AND i.care_team_id IS NOT NULL
   AND p.source_reference = 'fhir_import_resources/' || r.id::text;
UPDATE public.source_provenances p SET care_team_id = (
  SELECT t.id FROM public.care_teams t
   WHERE t.clinician_id = NULLIF(split_part(p.source_reference, ':', 2), '')::uuid
     AND t.patient_id = (SELECT f.patient_id FROM public.evidence_citations c
       JOIN public.clinical_facts f ON f.id = c.fact_id WHERE c.provenance_id = p.id LIMIT 1))
 WHERE p.artifact_type = 'clinician_entry' AND p.care_team_id IS NULL
   AND p.source_reference ~ '^clinician:[0-9a-f-]{36}:'
   AND (SELECT count(*) FROM public.care_teams t
     WHERE t.clinician_id = NULLIF(split_part(p.source_reference, ':', 2), '')::uuid
       AND t.patient_id = (SELECT f.patient_id FROM public.evidence_citations c
         JOIN public.clinical_facts f ON f.id = c.fact_id WHERE c.provenance_id = p.id LIMIT 1)) = 1;

-- Every source row behind a fact must be visible to the clinician, or the fact is hidden.
CREATE FUNCTION private.fact_visible_to_links(p_fact_id uuid, p_links uuid[])
RETURNS boolean LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT COALESCE(cardinality(p_links), 0) > 0 AND NOT EXISTS (
    SELECT 1 FROM public.evidence_citations c
    JOIN public.source_provenances p ON p.id = c.provenance_id
    LEFT JOIN public.documents d ON d.id = p.document_id
    WHERE c.fact_id = p_fact_id
      AND NOT CASE WHEN p.document_id IS NOT NULL THEN
        d.id IS NOT NULL AND private.document_visible_to_links(d.routing_state, d.care_team_id, p_links)
      ELSE p.care_team_id IS NULL OR p.care_team_id = ANY (p_links) END);
$$;

-- The facts a plan may draft from: sources routed to the plan's own team only, plus the
-- eligibility rules of 048. Adopted and unassigned plans draft nothing.
CREATE FUNCTION public.care_plan_source_fact_ids(p_care_plan_id uuid)
RETURNS SETOF uuid LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_plan public.care_plans%ROWTYPE;
BEGIN
  SELECT * INTO v_plan FROM public.care_plans WHERE id = p_care_plan_id;
  IF NOT FOUND OR v_plan.ownership_state <> 'owned' OR v_plan.origin <> 'native'
     OR v_plan.care_team_id IS DISTINCT FROM v_plan.origin_care_team_id THEN
    RETURN;
  END IF;
  RETURN QUERY
    SELECT f.id FROM public.clinical_facts f
    WHERE f.patient_id = v_plan.patient_id AND f.fact_type IN ('medication', 'obligation')
      AND f.review_state IN ('pending_review', 'approved')
      AND private.care_plan_fact_is_eligible(f.patient_id, f.id)
      AND EXISTS (SELECT 1 FROM public.evidence_citations c WHERE c.fact_id = f.id)
      AND NOT EXISTS (
        SELECT 1 FROM public.evidence_citations c
        JOIN public.source_provenances p ON p.id = c.provenance_id
        LEFT JOIN public.documents d ON d.id = p.document_id
        WHERE c.fact_id = f.id AND p.withdrawn_at IS NULL
          AND NOT CASE WHEN p.document_id IS NOT NULL THEN
            d.routing_state = 'routed' AND d.care_team_id = v_plan.care_team_id
          ELSE p.care_team_id = v_plan.care_team_id END);
END;
$$;

-- ── 4. Owned clinical records: SOAP, ADR review, MedWatch, imports ────────────────────────

ALTER TABLE public.soap_notes
  ADD COLUMN care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL;
UPDATE public.soap_notes s SET care_team_id = (
  SELECT t.id FROM public.care_teams t
   WHERE t.patient_id = s.patient_id AND t.clinician_id = s.clinician_id)
 WHERE (SELECT count(*) FROM public.care_teams t
   WHERE t.patient_id = s.patient_id AND t.clinician_id = s.clinician_id) = 1;

ALTER TABLE public.adr_assessments
  ADD COLUMN reviewed_by_care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL;
UPDATE public.adr_assessments a SET reviewed_by_care_team_id = (
  SELECT t.id FROM public.care_teams t
   WHERE t.patient_id = a.patient_id AND t.clinician_id = a.reviewed_by)
 WHERE a.reviewed_by IS NOT NULL
   AND (SELECT count(*) FROM public.care_teams t
     WHERE t.patient_id = a.patient_id AND t.clinician_id = a.reviewed_by) = 1;

ALTER TABLE public.medwatch_drafts
  ADD COLUMN care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL;
UPDATE public.medwatch_drafts m SET care_team_id = a.reviewed_by_care_team_id
  FROM public.adr_assessments a
 WHERE a.id = m.adr_assessment_id AND a.reviewed_by_care_team_id IS NOT NULL;

-- ── 5. Shared core: recording team, patient-controlled sensitivity ────────────────────────

ALTER TABLE public.conditions
  ADD COLUMN is_sensitive boolean NOT NULL DEFAULT false,
  ADD COLUMN sensitivity_changed_at timestamptz,
  ADD COLUMN recorded_by_care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  ADD COLUMN recorded_by jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(recorded_by) = 'object');
ALTER TABLE public.allergies
  ADD COLUMN recorded_by_care_team_id uuid REFERENCES public.care_teams(id) ON DELETE SET NULL,
  ADD COLUMN recorded_by jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(recorded_by) = 'object');
ALTER TABLE public.medications
  ADD COLUMN recorded_by jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(recorded_by) = 'object');

-- Recording team backfill: the patient's only care team, else unknown. An unknown recorder
-- is never guessed; a sensitive condition without one is visible to no clinician.
UPDATE public.conditions c SET recorded_by_care_team_id = (
  SELECT t.id FROM public.care_teams t WHERE t.patient_id = c.patient_id)
 WHERE (SELECT count(*) FROM public.care_teams t WHERE t.patient_id = c.patient_id) = 1;
UPDATE public.allergies a SET recorded_by_care_team_id = (
  SELECT t.id FROM public.care_teams t WHERE t.patient_id = a.patient_id)
 WHERE (SELECT count(*) FROM public.care_teams t WHERE t.patient_id = a.patient_id) = 1;
UPDATE public.medications m SET prescribed_by_care_team_id = (
  SELECT t.id FROM public.care_teams t WHERE t.patient_id = m.patient_id)
 WHERE m.prescribed_by_care_team_id IS NULL
   AND (SELECT count(*) FROM public.care_teams t WHERE t.patient_id = m.patient_id) = 1;
UPDATE public.conditions SET recorded_by = private.care_team_display(recorded_by_care_team_id)
 WHERE recorded_by_care_team_id IS NOT NULL;
UPDATE public.allergies SET recorded_by = private.care_team_display(recorded_by_care_team_id)
 WHERE recorded_by_care_team_id IS NOT NULL;
UPDATE public.medications SET recorded_by = private.care_team_display(prescribed_by_care_team_id)
 WHERE prescribed_by_care_team_id IS NOT NULL;

-- The recording team is stamped when a record is written inside a reconciliation or a plan
-- publication (they set mediagent.recording_care_team), and its display is snapshotted so
-- the label survives a link that later ends.
CREATE FUNCTION private.stamp_recording_team() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_team uuid;
  v_setting text := NULLIF(current_setting('mediagent.recording_care_team', true), '');
BEGIN
  IF TG_TABLE_NAME = 'medications' THEN
    IF TG_OP = 'INSERT' AND NEW.prescribed_by_care_team_id IS NULL AND v_setting IS NOT NULL THEN
      NEW.prescribed_by_care_team_id := v_setting::uuid;
    END IF;
    v_team := NEW.prescribed_by_care_team_id;
    IF v_team IS NOT NULL AND (TG_OP = 'INSERT'
        OR NEW.prescribed_by_care_team_id IS DISTINCT FROM OLD.prescribed_by_care_team_id) THEN
      NEW.recorded_by := private.care_team_display(v_team);
    END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'INSERT' AND NEW.recorded_by_care_team_id IS NULL AND v_setting IS NOT NULL THEN
    NEW.recorded_by_care_team_id := v_setting::uuid;
  END IF;
  IF NEW.recorded_by_care_team_id IS NOT NULL AND (TG_OP = 'INSERT'
      OR NEW.recorded_by_care_team_id IS DISTINCT FROM OLD.recorded_by_care_team_id) THEN
    NEW.recorded_by := private.care_team_display(NEW.recorded_by_care_team_id);
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER conditions_stamp_recording_team
  BEFORE INSERT OR UPDATE OF recorded_by_care_team_id ON public.conditions
  FOR EACH ROW EXECUTE FUNCTION private.stamp_recording_team();
CREATE TRIGGER allergies_stamp_recording_team
  BEFORE INSERT OR UPDATE OF recorded_by_care_team_id ON public.allergies
  FOR EACH ROW EXECUTE FUNCTION private.stamp_recording_team();
CREATE TRIGGER medications_stamp_recording_team
  BEFORE INSERT OR UPDATE OF prescribed_by_care_team_id ON public.medications
  FOR EACH ROW EXECUTE FUNCTION private.stamp_recording_team();

-- The team a reconciliation records for: the actor's link that owns the fact's sources,
-- else the actor's only link to the patient, else nobody (never a guess).
CREATE FUNCTION private.reconciling_care_team(p_fact_id uuid, p_actor_id uuid) RETURNS uuid
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE
  v_patient uuid;
  v_links uuid[];
  v_owned uuid[];
BEGIN
  SELECT patient_id INTO v_patient FROM public.clinical_facts WHERE id = p_fact_id;
  v_links := private.clinician_patient_links(p_actor_id, v_patient);
  IF cardinality(v_links) = 1 THEN RETURN v_links[1]; END IF;
  SELECT array_agg(DISTINCT team) INTO v_owned FROM (
    SELECT d.care_team_id AS team FROM public.evidence_citations c
      JOIN public.source_provenances p ON p.id = c.provenance_id
      JOIN public.documents d ON d.id = p.document_id
      WHERE c.fact_id = p_fact_id AND d.routing_state = 'routed'
    UNION ALL
    SELECT p.care_team_id FROM public.evidence_citations c
      JOIN public.source_provenances p ON p.id = c.provenance_id
      WHERE c.fact_id = p_fact_id AND p.document_id IS NULL) owners
    WHERE team = ANY (v_links);
  IF cardinality(v_owned) = 1 THEN RETURN v_owned[1]; END IF;
  RETURN NULL;
END;
$$;

-- Wrap the reconciliation (029): same signature, same behaviour, plus the recording team.
ALTER FUNCTION public.apply_clinical_fact_reconciliation(
  uuid, uuid, text, uuid, jsonb, jsonb, text, uuid) SET SCHEMA private;
CREATE FUNCTION public.apply_clinical_fact_reconciliation(
  p_fact_id uuid, p_actor_id uuid, p_decision text, p_target_id uuid, p_patch jsonb,
  p_selected_fields jsonb, p_note text, p_idempotency_key uuid
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  PERFORM set_config('mediagent.recording_care_team',
    COALESCE(private.reconciling_care_team(p_fact_id, p_actor_id)::text, ''), true);
  RETURN private.apply_clinical_fact_reconciliation(p_fact_id, p_actor_id, p_decision,
    p_target_id, p_patch, p_selected_fields, p_note, p_idempotency_key);
END;
$$;

-- Patient-controlled sensitivity of one of the patient's own conditions. No condition name
-- is written to the audit row.
CREATE TABLE public.condition_sensitivity_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL,
  condition_id uuid NOT NULL,
  is_sensitive boolean NOT NULL,
  actor_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX condition_sensitivity_events_condition
  ON public.condition_sensitivity_events(condition_id, created_at);
CREATE TRIGGER condition_sensitivity_events_append_only
  BEFORE UPDATE OR DELETE ON public.condition_sensitivity_events
  FOR EACH ROW EXECUTE FUNCTION private.care_plan_append_only();
CREATE TRIGGER condition_sensitivity_events_no_truncate
  BEFORE TRUNCATE ON public.condition_sensitivity_events
  FOR EACH STATEMENT EXECUTE FUNCTION private.care_plan_append_only();

CREATE FUNCTION public.set_condition_sensitivity(
  p_patient_id uuid, p_condition_id uuid, p_is_sensitive boolean
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE v_condition public.conditions%ROWTYPE;
BEGIN
  SELECT * INTO v_condition FROM public.conditions
    WHERE id = p_condition_id AND patient_id = p_patient_id FOR UPDATE;
  IF NOT FOUND THEN
    -- The same answer for a missing condition and another patient's: nothing to probe.
    RAISE EXCEPTION 'condition unavailable' USING ERRCODE = '42501';
  END IF;
  IF v_condition.is_sensitive IS DISTINCT FROM p_is_sensitive THEN
    UPDATE public.conditions SET is_sensitive = p_is_sensitive,
      sensitivity_changed_at = clock_timestamp() WHERE id = v_condition.id;
    INSERT INTO public.condition_sensitivity_events(patient_id, condition_id, is_sensitive, actor_id)
    VALUES (p_patient_id, p_condition_id, p_is_sensitive, p_patient_id);
  END IF;
  RETURN jsonb_build_object('condition_id', p_condition_id, 'is_sensitive', p_is_sensitive,
    'changed', v_condition.is_sensitive IS DISTINCT FROM p_is_sensitive);
END;
$$;

-- The shared clinical summary a clinician sees: one answer from one place, so no reader can
-- show a partial list without saying so.
CREATE FUNCTION public.shared_clinical_summary(p_clinician_id uuid, p_patient_id uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_links uuid[] := private.clinician_patient_links(p_clinician_id, p_patient_id);
BEGIN
  IF cardinality(v_links) = 0 THEN
    RAISE EXCEPTION 'patient unavailable' USING ERRCODE = '42501';
  END IF;
  RETURN jsonb_build_object(
    'medications', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'id', m.id, 'name', m.name, 'dosage', m.dosage, 'frequency', m.frequency,
        'route', m.route, 'instructions', m.instructions,
        'recorded_by', m.recorded_by,
        'recorded_by_care_team_id', m.prescribed_by_care_team_id) ORDER BY m.name, m.id)
      FROM public.medications m WHERE m.patient_id = p_patient_id AND m.is_active), '[]'),
    'allergies', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'id', a.id, 'allergen', a.allergen, 'reaction', a.reaction, 'severity', a.severity,
        'recorded_by', a.recorded_by,
        'recorded_by_care_team_id', a.recorded_by_care_team_id) ORDER BY a.allergen, a.id)
      FROM public.allergies a WHERE a.patient_id = p_patient_id), '[]'),
    'conditions', COALESCE((SELECT jsonb_agg(jsonb_build_object(
        'id', c.id, 'name', c.name, 'icd10_code', c.icd10_code, 'status', c.status,
        'recorded_by', c.recorded_by,
        'recorded_by_care_team_id', c.recorded_by_care_team_id) ORDER BY c.name, c.id)
      FROM public.conditions c
      WHERE c.patient_id = p_patient_id AND c.status = 'active'
        AND (NOT c.is_sensitive
          OR COALESCE(c.recorded_by_care_team_id = ANY (v_links), false))), '[]'),
    'some_conditions_private', EXISTS (
      SELECT 1 FROM public.conditions c
      WHERE c.patient_id = p_patient_id AND c.status = 'active' AND c.is_sensitive
        AND NOT COALESCE(c.recorded_by_care_team_id = ANY (v_links), false)),
    'care_teams', COALESCE((SELECT jsonb_agg(private.care_team_display(t.id)
        || jsonb_build_object('is_mine', t.id = ANY (v_links),
          'plan', (SELECT jsonb_build_object('care_plan_id', p.id,
              'ownership_state', p.ownership_state,
              'approved_at', (SELECT max(v.approved_at) FROM public.care_plan_versions v
                 WHERE v.care_plan_id = p.id AND v.status = 'approved'))
            FROM public.care_plans p WHERE p.care_team_id = t.id
            ORDER BY p.created_at LIMIT 1))
        ORDER BY t.created_at, t.id)
      FROM public.care_teams t WHERE t.patient_id = p_patient_id AND t.status = 'active'), '[]'));
END;
$$;

-- ── 6. Storage: a clinician reads a stored file only if its document is theirs ────────────
-- The old policy let any clinician assigned to the patient read the patient's whole folder.

CREATE FUNCTION private.clinician_reads_stored_file(p_name text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = 'pg_catalog' AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.documents d
    WHERE (d.file_path = p_name OR d.preview_path = p_name)
      AND private.document_visible_to_links(d.routing_state, d.care_team_id,
        private.clinician_patient_links(auth.uid(), d.patient_id)));
$$;
ALTER POLICY documents_read_clinician ON storage.objects
  USING (bucket_id = 'documents' AND private.clinician_reads_stored_file(name));

-- ── 6b. Row-level security: a signed-in clinician's own session follows the same rules ───
-- The backend enforces ownership in services, but a clinician's session token also reaches
-- PostgREST. These policies keep their old predicates and add the ownership rule; they call
-- wrappers that take only row identifiers and read the caller from the session, so a caller
-- cannot ask about anyone else.

CREATE FUNCTION private.rls_links(p_patient_id uuid) RETURNS uuid[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = 'pg_catalog' AS $$
  SELECT private.clinician_patient_links(auth.uid(), p_patient_id);
$$;
CREATE FUNCTION private.rls_document_visible(
  p_routing_state text, p_care_team_id uuid, p_patient_id uuid
) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = 'pg_catalog' AS $$
  SELECT private.document_visible_to_links(p_routing_state, p_care_team_id,
    private.clinician_patient_links(auth.uid(), p_patient_id));
$$;
CREATE FUNCTION private.rls_fact_visible(p_fact_id uuid, p_patient_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = 'pg_catalog' AS $$
  SELECT private.fact_visible_to_links(p_fact_id,
    private.clinician_patient_links(auth.uid(), p_patient_id));
$$;
-- The wrapper reads sources the caller's own policies might hide, so it must bypass RLS.
ALTER FUNCTION private.fact_visible_to_links(uuid, uuid[]) SECURITY DEFINER;
ALTER FUNCTION private.clinician_patient_links(uuid, uuid) SECURITY DEFINER;
ALTER FUNCTION private.document_visible_to_links(text, uuid, uuid[]) SECURITY DEFINER;

ALTER POLICY documents_clinician_select ON public.documents USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND private.rls_document_visible(routing_state, care_team_id, patient_id)
  AND ((visibility = 'all_providers'::public.document_visibility_enum)
    OR (uploaded_by = auth.uid())));
ALTER POLICY clinical_facts_clinician_select ON public.clinical_facts USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND private.rls_fact_visible(id, patient_id));
ALTER POLICY evidence_citations_clinician_select ON public.evidence_citations USING (EXISTS (
  SELECT 1 FROM public.clinical_facts f
  WHERE f.id = evidence_citations.fact_id AND private.is_clinician()
    AND private.is_assigned_clinician(f.patient_id) AND private.rls_fact_visible(f.id, f.patient_id)));
ALTER POLICY source_provenances_clinician_select ON public.source_provenances USING (EXISTS (
  SELECT 1 FROM public.evidence_citations c
  JOIN public.clinical_facts f ON f.id = c.fact_id
  WHERE c.provenance_id = source_provenances.id AND private.is_clinician()
    AND private.is_assigned_clinician(f.patient_id) AND private.rls_fact_visible(f.id, f.patient_id)));
ALTER POLICY clinical_fact_audit_events_clinician_select ON public.clinical_fact_audit_events
  USING (EXISTS (
    SELECT 1 FROM public.clinical_facts f
    WHERE f.id = clinical_fact_audit_events.fact_id AND private.is_clinician()
      AND private.is_assigned_clinician(f.patient_id) AND private.rls_fact_visible(f.id, f.patient_id)));
-- A note is its team's. One written before teams existed, with no determinable team, stays
-- with its author.
ALTER POLICY clinicians_read_own_soap_notes ON public.soap_notes USING (
  private.is_clinician() AND (
    care_team_id = ANY (private.rls_links(patient_id))
    OR (care_team_id IS NULL AND clinician_id = auth.uid()
      AND cardinality(private.rls_links(patient_id)) > 0)));
ALTER POLICY conditions_clinician_select ON public.conditions USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (NOT is_sensitive
    OR COALESCE(recorded_by_care_team_id = ANY (private.rls_links(patient_id)), false)));
-- A pending assessment is a safety item every team may see; a reviewed one is its
-- reviewing team's (or, for a review with no determinable team, its reviewer's).
ALTER POLICY adr_clinician_select ON public.adr_assessments USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (reviewed_by IS NULL
    OR reviewed_by_care_team_id = ANY (private.rls_links(patient_id))
    OR (reviewed_by_care_team_id IS NULL AND reviewed_by = auth.uid())));
ALTER POLICY adr_clinician_update ON public.adr_assessments USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (reviewed_by IS NULL
    OR reviewed_by_care_team_id = ANY (private.rls_links(patient_id))
    OR (reviewed_by_care_team_id IS NULL AND reviewed_by = auth.uid())));
ALTER POLICY medwatch_clinician_select ON public.medwatch_drafts USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND (care_team_id IS NULL OR care_team_id = ANY (private.rls_links(patient_id))));
ALTER POLICY medwatch_audit_clinician_select ON public.medwatch_draft_audit_events USING (EXISTS (
  SELECT 1 FROM public.medwatch_drafts draft
  WHERE draft.id = medwatch_draft_audit_events.medwatch_draft_id AND private.is_clinician()
    AND private.is_assigned_clinician(draft.patient_id)
    AND (draft.care_team_id IS NULL OR draft.care_team_id = ANY (private.rls_links(draft.patient_id)))));
ALTER POLICY medwatch_submissions_clinician_select ON public.medwatch_external_submissions USING (
  private.is_clinician() AND private.is_assigned_clinician(patient_id)
  AND EXISTS (SELECT 1 FROM public.medwatch_drafts draft
    WHERE draft.id = medwatch_external_submissions.medwatch_draft_id
      AND (draft.care_team_id IS NULL OR draft.care_team_id = ANY (private.rls_links(draft.patient_id)))));

-- The shared-core tables are written by the reconciliation and publication functions only;
-- the recording team and the patient's sensitivity flag are not for a session to set.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.conditions, public.allergies
  FROM anon, authenticated;

-- ── 7. Grants ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.document_routing_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.condition_sensitivity_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.document_routing_events, public.condition_sensitivity_events
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON public.document_routing_events, public.condition_sensitivity_events
  TO service_role;

REVOKE ALL ON FUNCTION
  private.clinician_patient_links(uuid, uuid), private.document_visible_to_links(text, uuid, uuid[]),
  private.document_routing_guard(), private.log_document_routing_on_upload(),
  private.document_ready_for_drafting(uuid), private.fact_visible_to_links(uuid, uuid[]),
  private.stamp_recording_team(), private.reconciling_care_team(uuid, uuid),
  private.clinician_reads_stored_file(text),
  private.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid),
  public.claim_document(uuid, uuid, uuid), public.queue_accepted_document_care_plan(),
  public.request_care_plan_generation_for_document(uuid, timestamptz),
  public.care_plan_source_fact_ids(uuid), public.set_condition_sensitivity(uuid, uuid, boolean),
  public.shared_clinical_summary(uuid, uuid),
  public.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION
  private.clinician_patient_links(uuid, uuid), private.document_visible_to_links(text, uuid, uuid[]),
  private.document_routing_guard(), private.log_document_routing_on_upload(),
  private.document_ready_for_drafting(uuid), private.fact_visible_to_links(uuid, uuid[]),
  private.stamp_recording_team(), private.reconciling_care_team(uuid, uuid),
  private.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid),
  public.claim_document(uuid, uuid, uuid), public.queue_accepted_document_care_plan(),
  public.request_care_plan_generation_for_document(uuid, timestamptz),
  public.care_plan_source_fact_ids(uuid), public.set_condition_sensitivity(uuid, uuid, boolean),
  public.shared_clinical_summary(uuid, uuid),
  public.apply_clinical_fact_reconciliation(uuid, uuid, text, uuid, jsonb, jsonb, text, uuid)
  TO service_role;
-- The storage policy runs as the signed-in clinician.
GRANT EXECUTE ON FUNCTION private.clinician_reads_stored_file(text) TO authenticated, service_role;
REVOKE ALL ON FUNCTION private.rls_links(uuid), private.rls_document_visible(text, uuid, uuid),
  private.rls_fact_visible(uuid, uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.rls_links(uuid), private.rls_document_visible(text, uuid, uuid),
  private.rls_fact_visible(uuid, uuid) TO authenticated, service_role;

-- ── 8. Verification ───────────────────────────────────────────────────────────────────────

DO $verify$
DECLARE v_function text;
BEGIN
  IF EXISTS (SELECT 1 FROM public.documents
      WHERE routing_state = 'routed' AND care_team_id IS NULL) THEN
    RAISE EXCEPTION 'PLAN-002 verification: a document is routed to nobody';
  END IF;
  IF EXISTS (SELECT 1 FROM public.documents
      WHERE routing_state = 'unrouted' AND care_team_id IS NOT NULL) THEN
    RAISE EXCEPTION 'PLAN-002 verification: an unrouted document has an owner';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.document_routing_events'::regclass)
     OR NOT (SELECT relrowsecurity FROM pg_class
       WHERE oid = 'public.condition_sensitivity_events'::regclass) THEN
    RAISE EXCEPTION 'PLAN-002 verification: RLS is off on a new table';
  END IF;
  IF has_table_privilege('anon', 'public.document_routing_events', 'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.document_routing_events',
       'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('anon', 'public.condition_sensitivity_events',
       'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated', 'public.condition_sensitivity_events',
       'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('service_role', 'public.document_routing_events', 'UPDATE')
     OR has_table_privilege('service_role', 'public.condition_sensitivity_events', 'DELETE') THEN
    RAISE EXCEPTION 'PLAN-002 verification: wrong grants on a trail table';
  END IF;
  FOREACH v_function IN ARRAY ARRAY[
    'public.claim_document(uuid,uuid,uuid)',
    'public.set_condition_sensitivity(uuid,uuid,boolean)',
    'public.shared_clinical_summary(uuid,uuid)',
    'public.care_plan_source_fact_ids(uuid)',
    'public.request_care_plan_generation_for_document(uuid,timestamptz)',
    'public.apply_clinical_fact_reconciliation(uuid,uuid,text,uuid,jsonb,jsonb,text,uuid)',
    'private.apply_clinical_fact_reconciliation(uuid,uuid,text,uuid,jsonb,jsonb,text,uuid)'] LOOP
    IF has_function_privilege('anon', v_function, 'EXECUTE')
       OR has_function_privilege('authenticated', v_function, 'EXECUTE')
       OR NOT has_function_privilege('service_role', v_function, 'EXECUTE') THEN
      RAISE EXCEPTION 'PLAN-002 verification: wrong execute grants on %', v_function;
    END IF;
  END LOOP;
END;
$verify$;
