-- Introduce first-class clinics and bind clinicians to canonical clinic identity.

-- ── Types ─────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'clinic_status_enum') THEN
        CREATE TYPE clinic_status_enum AS ENUM ('active', 'suspended');
    END IF;
END $$;

-- ── Helpers ───────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION normalize_clinic_name(input_name text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT lower(trim(regexp_replace(coalesce(input_name, ''), '\\s+', ' ', 'g')));
$$;

CREATE OR REPLACE FUNCTION generate_clinic_code()
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    generated text;
BEGIN
    generated := upper(substr(encode(gen_random_bytes(8), 'hex'), 1, 10));
    RETURN generated;
END;
$$;

-- ── Clinics ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clinics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE DEFAULT generate_clinic_code(),
    display_name text NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 200),
    canonical_name text NOT NULL,
    type2_npi text,
    status clinic_status_enum NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_clinics_canonical_name
    ON clinics (canonical_name);

CREATE INDEX IF NOT EXISTS idx_clinics_status
    ON clinics (status);

-- ── Clinician clinic binding ──────────────────────────────────────────────────
ALTER TABLE clinicians
    ADD COLUMN IF NOT EXISTS clinic_id uuid REFERENCES clinics(id),
    ADD COLUMN IF NOT EXISTS type1_npi text;

CREATE INDEX IF NOT EXISTS idx_clinicians_clinic_id
    ON clinicians (clinic_id);

-- Backfill type1_npi from legacy clinician npi_number when format already matches.
UPDATE clinicians
SET type1_npi = npi_number
WHERE type1_npi IS NULL
  AND npi_number ~ '^\\d{10}$';

-- Backfill clinics from existing clinician clinic_name values.
INSERT INTO clinics (display_name, canonical_name)
SELECT c.clinic_name, normalize_clinic_name(c.clinic_name)
FROM clinicians c
WHERE c.clinic_name IS NOT NULL
GROUP BY c.clinic_name
ON CONFLICT (canonical_name) DO NOTHING;

UPDATE clinicians c
SET clinic_id = cl.id
FROM clinics cl
WHERE c.clinic_id IS NULL
  AND cl.canonical_name = normalize_clinic_name(c.clinic_name);

COMMENT ON TABLE clinics IS 'Canonical clinic entity. Clinician signup/login flows should resolve clinic by code rather than free-text names.';
