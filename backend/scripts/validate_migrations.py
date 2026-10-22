"""Parse every committed PostgreSQL migration before it reaches deployment."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pglast import parse_sql
from pglast.parser import ParseError

MIGRATION_NAME = re.compile(r"^(?P<sequence>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "src" / "app" / "db" / "migrations"
# Preserve historical independent files already recorded by filename/checksum.
# New collisions must be fixed by renumbering the unapplied migration, not by
# extending this grandfathered list or changing applied migration bytes.
# Applied 067 filenames stay immutable. Only that exact historical pair is allowed;
# an additional file at 067 must still fail rather than silently changing history.
LEGACY_SHARED_SEQUENCES = frozenset({11, 38, 39, 40, 41, 42, 43, 47, 48, 51})
# 89 belongs to a sibling branch that is open at the same time as this one (88 has landed).
RESERVED_SEQUENCES = frozenset({89})
LEGACY_SHARED_FILENAME_GROUPS = frozenset(
    {
        frozenset(
            {
                "067_clinic_lists_and_roles.sql",
                "067_english_display_facts.sql",
            }
        ),
        frozenset(
            {
                "059_chat_safety_alerts.sql",
                "059_critical_result_alerts.sql",
            }
        ),
        frozenset(
            {
                "060_confirmed_symptom_intake.sql",
                "060_critical_result_open_work.sql",
            }
        ),
        frozenset(
            {
                "071_clinician_visit_management.sql",
                "071_confirmed_symptom_handoff.sql",
            }
        ),
    }
)


def validate_migrations() -> list[str]:
    """Return validation errors for the repository's ordered SQL migrations."""
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    errors: list[str] = []
    seen_names: set[str] = set()
    sequence_names: dict[int, set[str]] = {}

    if not migration_paths:
        return [f"No SQL migrations found in {MIGRATIONS_DIR}"]

    for migration_path in migration_paths:
        match = MIGRATION_NAME.fullmatch(migration_path.name)
        if match is None:
            errors.append(f"{migration_path.name}: expected NNN_descriptive_name.sql")
            continue

        if migration_path.name in seen_names:
            errors.append(f"{migration_path.name}: duplicate migration filename")
        seen_names.add(migration_path.name)
        sequence = int(match.group("sequence"))
        names = sequence_names.setdefault(sequence, set())
        if names and sequence not in LEGACY_SHARED_SEQUENCES:
            candidate_group = frozenset((*names, migration_path.name))
            if candidate_group not in LEGACY_SHARED_FILENAME_GROUPS:
                errors.append(f"{migration_path.name}: duplicate migration sequence {sequence:03d}")
        names.add(migration_path.name)

        source = migration_path.read_text(encoding="utf-8")
        if not source.strip():
            errors.append(f"{migration_path.name}: migration is empty")
            continue

        try:
            statements = parse_sql(source)
        except ParseError as error:
            errors.append(f"{migration_path.name}: PostgreSQL syntax error: {error}")
            continue

        if not statements:
            errors.append(f"{migration_path.name}: migration contains no SQL statements")

    sequences = set(sequence_names)
    expected_sequences = set(range(1, max(sequences, default=0) + 1))
    missing_sequences = sorted(expected_sequences - sequences - RESERVED_SEQUENCES)
    if missing_sequences:
        formatted = ", ".join(f"{sequence:03d}" for sequence in missing_sequences)
        errors.append(f"Missing migration sequence(s): {formatted}")

    return errors


def main() -> int:
    """Validate migration naming, ordering continuity, and PostgreSQL syntax."""
    errors = validate_migrations()
    if errors:
        print("Migration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    count = len(list(MIGRATIONS_DIR.glob("*.sql")))
    print(f"Validated {count} PostgreSQL migration files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
