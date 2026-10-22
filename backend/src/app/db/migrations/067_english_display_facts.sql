-- LOC-003: Store English display fields alongside the original language for
-- facts extracted from Spanish documents. Clinicians see English; the original
-- stays as evidence. Values, units, ranges and dates are never translated.

ALTER TABLE public.clinical_facts
  ADD COLUMN IF NOT EXISTS display_locale text
    CHECK (display_locale IS NULL OR display_locale IN ('en-US', 'es-MX')),
  ADD COLUMN IF NOT EXISTS display_value jsonb
    CHECK (display_value IS NULL OR jsonb_typeof(display_value) = 'object');

COMMENT ON COLUMN public.clinical_facts.display_locale IS
  'Language the fact values are displayed in for the clinician portal (LOC-003).';
COMMENT ON COLUMN public.clinical_facts.display_value IS
  'English display fields when the source is Spanish. Keys mirror value; only '
  'translatable fields (name, instructions, description, frequency, test_name) '
  'are present. Values/units/dates are never included here.';
