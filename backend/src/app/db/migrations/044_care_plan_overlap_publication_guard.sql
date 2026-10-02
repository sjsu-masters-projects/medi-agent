-- Review may retain every candidate, but duplicate activities cannot be published.
-- Item edits take the parent version lock (migration 043), serializing this check
-- with concurrent review. An exception rolls back projection/supersession writes.
CREATE FUNCTION public.guard_care_plan_overlap_publication() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' THEN
    IF EXISTS (
      SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = NEW.id AND NOT is_removed AND category <> 'medication'
        AND btrim(instructions) <> '' AND btrim(frequency) <> ''
      GROUP BY category,
        lower(regexp_replace(btrim(instructions), '\s+', ' ', 'g')), schedule
      HAVING count(*) > 1
    ) OR EXISTS (
      SELECT 1 FROM public.care_plan_items
      WHERE plan_version_id = NEW.id AND NOT is_removed AND category = 'medication'
        AND btrim(COALESCE(medication->>'name', '')) <> ''
      GROUP BY lower(regexp_replace(btrim(medication->>'name'), '\s+', ' ', 'g'))
      HAVING count(*) > 1
    ) OR EXISTS (
      -- The same structured evidence can have a translated carried heading.
      -- Different display text does not make that evidence a second activity.
      SELECT 1 FROM public.care_plan_items i
      JOIN public.clinical_facts f ON f.id = i.source_fact_id
      WHERE i.plan_version_id = NEW.id AND NOT i.is_removed AND f.patient_id = NEW.patient_id
        AND ((f.fact_type = 'medication' AND btrim(COALESCE(f.value->>'name', '')) <> '')
          OR (f.fact_type = 'obligation' AND btrim(COALESCE(f.value->>'description', '')) <> ''))
      GROUP BY f.fact_type, f.value HAVING count(*) > 1
    ) THEN
      RAISE EXCEPTION 'resolve overlapping plan items before publication';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER care_plan_overlap_publication_guard BEFORE UPDATE ON public.care_plan_versions
  FOR EACH ROW EXECUTE FUNCTION public.guard_care_plan_overlap_publication();
REVOKE ALL ON FUNCTION public.guard_care_plan_overlap_publication() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_care_plan_overlap_publication() TO service_role;
