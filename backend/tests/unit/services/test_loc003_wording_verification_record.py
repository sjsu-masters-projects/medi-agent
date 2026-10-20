"""LOC-003 item 11: the guard outcome is recorded with the wording verification.

The attestation says a clinician checked the Spanish through its English back-translation
and the guard results. Recording which deterministic checks ran and passed is what makes
that attestation auditable later; it is never a substitute for the checks themselves,
which publication re-runs against the stored wording.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.care_plan_service import CarePlanService
from app.services.care_plan_translation import (
    GUARD_CHECKS,
    guard_report,
    validate_draft,
    wording_fingerprint,
)

CLINICIAN_ID = UUID("00000000-0000-0000-0000-0000000002a1")

ENGLISH = {
    "title": "Metformin 500 mg",
    "instructions": "Take 1 tablet by mouth twice daily with meals.",
    "frequency": "twice daily",
}
SPANISH = {
    "title": "Metformin 500 mg",
    "instructions": "Toma 1 tableta por vía oral dos veces al día con las comidas.",
    "frequency": "dos veces al día",
}


def _item(**changes: Any) -> dict[str, Any]:
    return {
        "source_locale": "en-US",
        "wording": {"en-US": ENGLISH, "es-MX": SPANISH},
        "medication": {"name": "Metformin"},
        **changes,
    }


class TestGuardReport:
    def test_every_named_check_is_reported(self) -> None:
        report = guard_report(ENGLISH, SPANISH, _item())
        assert set(report) == set(GUARD_CHECKS)
        assert all(report.values())

    def test_each_failure_is_reported_separately(self) -> None:
        """A rejection names one reason; the record needs all of them."""
        broken = {**SPANISH, "title": "Metformin 250 mg", "frequency": ""}
        report = guard_report(ENGLISH, broken, _item())
        assert report["numbers_match"] is False
        assert report["fields_present"] is False
        assert report["negation_match"] is True

    def test_validate_draft_agrees_with_the_report(self) -> None:
        assert validate_draft(ENGLISH, SPANISH, _item()) is None
        broken = {**SPANISH, "instructions": SPANISH["instructions"].replace("Toma", "No tomes")}
        assert validate_draft(ENGLISH, broken, _item()) == "negation_changed"
        assert guard_report(ENGLISH, broken, _item())["negation_match"] is False


class TestWordingFingerprint:
    def test_same_wording_fingerprints_the_same(self) -> None:
        assert wording_fingerprint(ENGLISH) == wording_fingerprint(dict(ENGLISH))

    def test_surrounding_whitespace_is_not_a_change(self) -> None:
        padded = {key: f"  {value} " for key, value in ENGLISH.items()}
        assert wording_fingerprint(padded) == wording_fingerprint(ENGLISH)

    def test_changed_wording_changes_the_fingerprint(self) -> None:
        assert wording_fingerprint({**ENGLISH, "frequency": "once daily"}) != wording_fingerprint(
            ENGLISH
        )

    def test_missing_wording_is_fingerprintable(self) -> None:
        assert wording_fingerprint(None) == wording_fingerprint({})


class TestVerificationRecord:
    def test_records_who_checked_what_and_when(self) -> None:
        record = CarePlanService._wording_verification_record(_item(), CLINICIAN_ID)
        assert record["verified_by"] == str(CLINICIAN_ID)
        assert record["source_locale"] == "en-US"
        assert record["checks_passed"] is True
        assert set(record["checks"]) == set(GUARD_CHECKS)
        assert record["verified_at"]

    def test_records_the_fingerprints_of_both_languages(self) -> None:
        record = CarePlanService._wording_verification_record(_item(), CLINICIAN_ID)
        assert record["fingerprints"] == {
            "en-US": wording_fingerprint(ENGLISH),
            "es-MX": wording_fingerprint(SPANISH),
        }

    def test_a_record_does_not_describe_wording_that_has_since_changed(self) -> None:
        record = CarePlanService._wording_verification_record(_item(), CLINICIAN_ID)
        edited = {**SPANISH, "frequency": "una vez al día"}
        assert record["fingerprints"]["es-MX"] != wording_fingerprint(edited)

    def test_an_unknown_source_locale_records_no_claim_about_the_checks(self) -> None:
        record = CarePlanService._wording_verification_record(
            _item(source_locale=None), CLINICIAN_ID
        )
        assert record["checks"] == {}
        assert record["checks_passed"] is None


def test_redrafting_wording_drops_the_record_it_no_longer_describes() -> None:
    """A re-translation replaces the text, so the old check and cache must not survive it."""
    from unittest.mock import MagicMock

    db = MagicMock()
    service = CarePlanService(db)
    service._store_translation(
        {"id": "item-1", "plan_version_id": "plan-1", **ENGLISH},
        "en-US",
        "es-MX",
        SPANISH,
    )
    payload = db.table.return_value.update.call_args.args[0]
    assert payload["wording_verified"] is False
    assert payload["wording_verification"] is None
    assert payload["back_translation"] is None
