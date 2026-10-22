"""Read-only LOC-003 acceptance preflight. Never applies SQL, publishes or sends anything.

Two jobs:

``--self-check`` (no network, no database, no model)
    Runs every LOC-003 translation path against the offline stub and asserts the properties
    the feature actually rests on: numbers, doses, medication names and negations survive a
    translation; a translation that changes one is rejected; proper names are never sent to
    the model; a gloss is addressed by its own text. This is the environment-independent
    acceptance the task row asks for — the paths can be checked where Vertex AI is
    unreachable, which is exactly where they used to be uncheckable.

``--check-target`` (read-only reads of the configured project)
    Reports whether migrations 080-082 and 088 are recorded in the target's ledger with the
    checksums this working tree holds, and whether the columns and labels they add are
    actually present. Run this before the deployed acceptance journeys; the journeys
    themselves are recorded in docs/evidence/deployed-recheck-2026-10-11.md.

Nothing here mutates a remote environment. Applying migrations stays a separate, explicitly
authorized step (scripts/apply-supabase-migrations.sh).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "src/app"

#: The migrations LOC-003's clinician surfaces need in the target.
REQUIRED = (
    "080_message_translation_integrity.sql",
    "081_care_plan_wording_verification.sql",
    "082_loc003_display_provenance.sql",
    "088_confirmed_message_translation.sql",
)

#: Wording that exercises every guard at once: a dose with a unit, a thousands separator, a
#: decimal, a medication name and a negation.
GUARDED = (
    "Take 1 tablet of Metformin 500 mg twice daily with meals. "
    "Do not take 1,000 mg or 2.5 mL without water."
)
GUARDED_ES = (
    "Toma 1 tableta de Metformin 500 mg dos veces al día con las comidas. "
    "No tomes 1,000 mg ni 2.5 mL sin agua."
)


def _checksum(name: str) -> str:
    return hashlib.sha256((ROOT / "db/migrations" / name).read_bytes()).hexdigest()


def _report(label: str, *values: Any, passed: bool) -> bool:
    print(label, *values, "PASS" if passed else "FAIL")
    return passed


async def _self_check() -> bool:
    """Exercise every translation path offline and assert the safety properties."""
    from app.config import settings

    settings.translation_stub_enabled = True
    if settings.is_production:
        print("SELF_CHECK production FAIL (the stub is ignored in production by design)")
        return False

    from app.services.care_plan_translation import (
        back_translate_spanish,
        draft_translations,
        guard_report,
        validate_draft,
        wording_fingerprint,
    )
    from app.services.evidence_gloss import excerpt_id, gloss_excerpt, needs_gloss
    from app.services.fact_display_translation import (
        translatable_fields,
        translate_facts_to_english,
    )
    from app.services.message_translation import back_translate_message, translate_message
    from app.services.translation_guards import guard_failure
    from app.services.translation_stub import STUB_MODEL_ID, translate_text

    checks: list[bool] = []

    # ── The guards themselves, both directions ───────────────────────────
    for locale, text in (("es-MX", GUARDED), ("en-US", GUARDED_ES)):
        translated = translate_text(text, locale)
        checks.append(
            _report(
                "GUARD_SURVIVES_TRANSLATION",
                locale,
                passed=guard_failure(text, translated, ["Metformin"]) is None,
            )
        )
    checks.append(
        _report(
            "GUARD_REJECTS_CHANGED_DOSE",
            passed=guard_failure(GUARDED, GUARDED.replace("500 mg", "250 mg")) is not None,
        )
    )
    checks.append(
        _report(
            "GUARD_REJECTS_LOST_NEGATION",
            passed=guard_failure(
                GUARDED, GUARDED.replace("Do not take", "take").replace("without", "with")
            )
            is not None,
        )
    )
    checks.append(
        _report(
            "GUARD_REJECTS_ADDED_NEGATION",
            passed=guard_failure("Take 1 tablet with water", "Do not take 1 tablet with water")
            is not None,
        )
    )
    # A known limitation, reported every run rather than left to be rediscovered: the guard
    # compares whether a negation is PRESENT, not how many there are, because the two
    # languages do not use the same number of negative words ("Never take" is idiomatically
    # "No tomes nunca"). So dropping one of two negations while another survives is not
    # caught. See the LOC-003 spec's follow-up; changing it is an LOC-001 guard decision.
    print(
        "KNOWN_GAP negation_count_not_compared",
        "cross-language presence checks are not semantic proof; English back-translations additionally compare counts",
        "PASS"
        if guard_failure(GUARDED, GUARDED.replace("Do not take", "Take")) is None
        else "CLOSED",
    )
    checks.append(
        _report(
            "GUARD_REJECTS_THOUSANDS_SEPARATOR_SWAP",
            passed=guard_failure(GUARDED, GUARDED.replace("1,000 mg", "1.000 mg")) is not None,
        )
    )
    checks.append(
        _report(
            "GUARD_REJECTS_CHANGED_MEDICATION_NAME",
            passed=guard_failure(GUARDED, GUARDED.replace("Metformin", "Metformina"), ["Metformin"])
            is not None,
        )
    )

    # ── Care-plan second-language drafting, both source languages ────────
    item = {
        "id": "preflight-item",
        "title": "Metformin 500 mg",
        "instructions": "Take 1 tablet by mouth twice daily with meals.",
        "frequency": "twice daily",
        "medication": {"name": "Metformin"},
    }
    drafts, diagnostics = await draft_translations([item], record_telemetry=False)
    draft = drafts.get("preflight-item")
    checks.append(
        _report(
            "CARE_PLAN_DRAFT_EN_TO_ES",
            diagnostics.get("translation_drafted_count"),
            passed=draft is not None
            and draft.target_locale == "es-MX"
            and draft.model_id == STUB_MODEL_ID
            and "500 mg" in draft.wording.title,
        )
    )
    spanish_item = {**item, "instructions": GUARDED_ES, "frequency": "dos veces al día"}
    es_drafts, _ = await draft_translations([spanish_item], record_telemetry=False)
    es_draft = es_drafts.get("preflight-item")
    checks.append(
        _report(
            "CARE_PLAN_DRAFT_ES_TO_EN",
            passed=es_draft is not None and es_draft.target_locale == "en-US",
        )
    )

    # ── Back-translation and the attestation's guard report ─────────────
    english = {key: str(item[key]) for key in ("title", "instructions", "frequency")}
    spanish = (
        draft.wording.model_dump() if draft else {"title": "", "instructions": "", "frequency": ""}
    )
    back = await back_translate_spanish(spanish, english, item)
    checks.append(
        _report(
            "BACK_TRANSLATION_GUARDS",
            passed=back.numbers_match and back.medication_names_match and bool(back.title),
        )
    )
    report = guard_report(english, spanish, item)
    checks.append(_report("WORDING_GUARD_REPORT", sorted(report), passed=all(report.values())))
    checks.append(
        _report(
            "WORDING_FINGERPRINT_TRACKS_EDITS",
            passed=wording_fingerprint(english)
            != wording_fingerprint({**english, "frequency": "once daily"})
            and wording_fingerprint(english) == wording_fingerprint({**english}),
        )
    )
    checks.append(
        _report(
            "WORDING_GUARD_BLOCKS_BAD_VERIFICATION",
            passed=validate_draft(english, {**spanish, "title": "Metformin 250 mg"}, item)
            == "numbers_changed",
        )
    )

    # ── Fact display fields, including the proper-name rule ─────────────
    translated_facts = await translate_facts_to_english(
        [
            ("preflight-fact", "obligation", {"description": GUARDED_ES, "frequency": "cada día"}),
            (
                "preflight-med",
                "medication",
                {"name": "Losartán", "instructions": "Toma 1 tableta cada día"},
            ),
        ]
    )
    accepted = translated_facts.get("preflight-fact")
    checks.append(
        _report(
            "FACT_TRANSLATION",
            passed=accepted is not None
            and accepted.model_id == STUB_MODEL_ID
            and "500 mg" in accepted.fields["description"],
        )
    )
    checks.append(
        _report(
            "PROPER_NAMES_NEVER_SENT",
            passed="name" not in translatable_fields("medication", {"name": "Losartán"})
            and "allergen" not in translatable_fields("allergy", {"allergen": "Penicilina"})
            and "vaccine" not in translatable_fields("immunization", {"vaccine": "Influenza"}),
        )
    )

    # ── Messages, both directions, and the reply back-translation ───────
    text, passed, failure, model = await translate_message(
        GUARDED_ES, "es-MX", "en-US", ["Metformin"]
    )
    checks.append(
        _report(
            "MESSAGE_TRANSLATION_ES_TO_EN",
            model,
            passed=passed and failure is None and model == STUB_MODEL_ID and "500 mg" in text,
        )
    )
    reply, reply_passed, _failure, _model = await translate_message(
        GUARDED, "en-US", "es-MX", ["Metformin"]
    )
    reply_back = await back_translate_message(reply, "es-MX", "en-US", ["Metformin"])
    checks.append(
        _report(
            "REPLY_PREVIEW_ROUND_TRIP",
            passed=reply_passed
            and guard_failure(GUARDED, reply, ["Metformin"]) is None
            and guard_failure(reply, reply_back, ["Metformin"]) is None,
        )
    )

    # ── Evidence glosses and their addressing ──────────────────────────
    gloss, gloss_passed, gloss_model = await gloss_excerpt(GUARDED_ES, ["Metformin"])
    checks.append(
        _report(
            "EVIDENCE_GLOSS",
            gloss_model,
            passed=gloss_passed and bool(gloss) and gloss_model == STUB_MODEL_ID,
        )
    )
    checks.append(
        _report(
            "GLOSS_ADDRESS_IS_ITS_TEXT",
            passed=excerpt_id(GUARDED_ES) == excerpt_id(f"  {GUARDED_ES}  ")
            and excerpt_id(GUARDED_ES) != excerpt_id(GUARDED_ES.replace("500", "850"))
            and needs_gloss(GUARDED_ES)
            and not needs_gloss(GUARDED),
        )
    )

    print("SELF_CHECK", "PASS" if all(checks) else "FAIL", f"{sum(checks)}/{len(checks)}")
    return all(checks)


def _check_target() -> bool:
    """Read the target's migration ledger and the schema LOC-003 needs. Read-only."""
    from app.db.connection import get_db

    db = get_db()
    rows = (
        db.table("schema_migrations")
        .select("filename,checksum")
        .in_("filename", list(REQUIRED))
        .execute()
        .data
    )
    if not isinstance(rows, list):
        raise ValueError("Invalid migration ledger response")
    ledger = {
        row["filename"]: row["checksum"]
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("filename"), str)
        and isinstance(row.get("checksum"), str)
    }
    checks = [
        _report("TARGET_MIGRATION", name, passed=ledger.get(name) == _checksum(name))
        for name in REQUIRED
    ]

    # The ledger is authoritative for "applied", but the columns are what the code needs.
    for table, column in (
        ("clinical_facts", "display_model_id"),
        ("care_plan_items", "back_translation"),
        ("care_plan_items", "wording_verification"),
        ("care_plan_items", "translation_model_id"),
        ("message_translations", "clinician_confirmed"),
    ):
        try:
            db.table(table).select(column).limit(1).execute()
            checks.append(_report("TARGET_COLUMN", f"{table}.{column}", passed=True))
        except Exception as error:  # noqa: BLE001 - the reason is the result here
            checks.append(
                _report("TARGET_COLUMN", f"{table}.{column}", type(error).__name__, passed=False)
            )

    print("CHECK_TARGET", "PASS" if all(checks) else "FAIL", f"{sum(checks)}/{len(checks)}")
    return all(checks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run every translation path offline against the stub; no network or database",
    )
    parser.add_argument(
        "--check-target",
        action="store_true",
        help="Read the configured project's ledger and columns; no mutations",
    )
    args = parser.parse_args()
    if not (args.self_check or args.check_target):
        parser.error("choose --self-check, --check-target, or both")

    for name in REQUIRED:
        print("REPO_MIGRATION", name, _checksum(name))

    passed = True
    if args.self_check:
        passed = asyncio.run(_self_check()) and passed
    if args.check_target:
        passed = _check_target() and passed
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
