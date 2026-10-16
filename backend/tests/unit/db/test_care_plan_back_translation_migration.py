"""Text-level guarantees of the back-translation migration (LOC-003, migration 066)."""

from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "src/app/db/migrations"
MIGRATION = (MIGRATIONS / "066_care_plan_wording_back_translation.sql").read_text()
CODE = "\n".join(line.split("--", 1)[0] for line in MIGRATION.splitlines())


def test_it_is_the_one_back_translation_migration_and_needs_only_049() -> None:
    assert [p.name for p in MIGRATIONS.glob("066_*.sql")] == [
        "066_care_plan_wording_back_translation.sql"
    ]
    assert (MIGRATIONS / "049_bilingual_care_plan_wording.sql").exists()
    header = MIGRATION.split("\n\n")[0]
    assert "Requires 049." in header
    assert "Independent of 065" in header
    assert "applied to a hosted project only on explicit authorization" in header.lower()


def test_it_adds_one_review_column_and_leaves_patient_wording_alone() -> None:
    assert CODE.count("ALTER TABLE") == 1
    assert "ADD COLUMN wording_back_translation jsonb NOT NULL DEFAULT '{}'::jsonb" in CODE
    # The patient-facing contract, the projections and the functions are unchanged.
    for untouched in ("FUNCTION", "patient_wording", "public.medications", "public.obligations"):
        assert untouched not in CODE
    assert "DROP" not in CODE and "UPDATE " not in CODE


def test_the_stored_shape_is_closed_and_bounded() -> None:
    for key in ("status", "method", "wording_sha256", "text", "reason", "model", "drafted_at"):
        assert f"'{key}'" in CODE
    assert "IN ('drafted', 'rejected')" in CODE
    assert "IN ('back_translation', 'forward_translation')" in CODE
    assert "'^[0-9a-f]{64}$'" in CODE
    assert "- 'title' - 'instructions' - 'frequency') = '{}'::jsonb" in CODE
    for field, limit in (("title", 300), ("instructions", 2000), ("frequency", 200)):
        assert f"{{text,{field}}}', '')) <= {limit}" in CODE
