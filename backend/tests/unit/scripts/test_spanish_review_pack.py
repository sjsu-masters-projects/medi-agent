"""Review inventory reads static source and preserves wording, never imports it."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from scripts import build_spanish_review_pack as pack


def test_python_inventory_pairs_event_titles_and_explanations():
    rows = pack.python_rows("backend/src/app/services/notification_centre_presentation.py")
    keyed = {row["key"]: row for row in rows}
    assert keyed["_COPY.legacy_update.0"]["en"] == "Earlier notification"
    assert keyed["_COPY.legacy_update.0"]["es"] == "Notificación anterior"
    assert keyed["_COPY.legacy_update.1"]["en"] == "From the previous inbox; not a new task."


def test_calendar_labels_and_email_subject_drafts_are_included():
    calendar = pack.python_rows("backend/src/app/services/appointment_calendar.py")
    assert any(row["en"] == "Clinic" and row["es"] == "Clínica" for row in calendar)
    email = pack.python_rows("backend/src/app/services/email_service.py")
    assert any(
        row["en"] == "Appointment cancelled" and row["es"] == "Cita cancelada" for row in email
    )


def test_inventory_does_not_execute_copy(tmp_path, monkeypatch):
    (tmp_path / "copy.py").write_text(
        'raise RuntimeError("must not execute")\n'
        '_COPY = {"en-US": {"label": "Hello"}, "es-MX": {"label": "Hola"}}\n'
    )
    monkeypatch.setattr(pack, "ROOT", tmp_path)
    assert pack.python_rows("copy.py")[0]["es"] == "Hola"


def test_missing_english_counterpart_fails_instead_of_inventing_copy(tmp_path, monkeypatch):
    (tmp_path / "copy.py").write_text('_COPY = {"en-US": {}, "es-MX": {"label": "Hola"}}')
    monkeypatch.setattr(pack, "ROOT", tmp_path)
    with pytest.raises(KeyError):
        pack.python_rows("copy.py")


def test_table_cells_escape_markup_and_pipes():
    assert pack.cell("<text> & value|next\nline") == "&lt;text&gt; &amp; value&#124;next line"


def test_build_calls_static_extractor_and_propagates_errors(monkeypatch):
    def fail(*args, **kwargs):
        assert args[0][0:2] == ["node", "scripts/extract-spanish-review.mjs"]
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(pack.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        pack.build()


def test_freshness_check_rejects_missing_or_stale_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "DESTINATION", tmp_path / "pack.md")
    monkeypatch.setattr(pack, "build", lambda: "expected\n")
    monkeypatch.setattr(
        pack.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(check=True, require_reviewed=False),
    )
    assert pack.main() == 1
    pack.DESTINATION.write_text("old\n")
    assert pack.main() == 1
    pack.DESTINATION.write_text("expected\n")
    assert pack.main() == 0


def test_english_clinician_title_description_tuples_are_not_spanish():
    rows = pack.python_rows("backend/src/app/services/notification_centre_presentation.py")
    assert not any(
        str(row["key"]).startswith(("_REVIEW_COPY.", "_CLINIC_REVIEW_COPY.")) for row in rows
    )


def test_acceptance_requires_exact_reviewed_snapshot(tmp_path, monkeypatch):
    receipt = tmp_path / "review.json"
    monkeypatch.setattr(pack, "REVIEW_RECEIPT", receipt)
    monkeypatch.setattr(pack, "snapshot", lambda rows: {"pairs": rows})
    reviewed = [{"file": "copy.ts", "key": "label", "en": "Hello", "es": "Hola"}]
    assert not pack.accepted(reviewed)
    receipt.write_text(
        json.dumps(
            {
                "status": "accepted_for_synthetic_project_interface_use",
                "snapshot": {"pairs": reviewed},
            }
        )
    )
    assert pack.accepted(reviewed)
    assert not pack.accepted([{**reviewed[0], "es": "changed"}])
    assert not pack.accepted([*reviewed, {**reviewed[0], "key": "new"}])
    receipt.write_text("not json")
    assert not pack.accepted(reviewed)


def test_source_edit_invalidates_snapshot_even_when_pairs_match(tmp_path, monkeypatch):
    (tmp_path / "copy.ts").write_text("original source")
    monkeypatch.setattr(pack, "ROOT", tmp_path)
    monkeypatch.setattr(pack, "TS_FILES", ("copy.ts",))
    monkeypatch.setattr(pack, "PY_FILES", ())
    rows = [{"file": "copy.ts", "key": "label", "en": "Hello", "es": "Hola"}]
    original = pack.snapshot(rows)
    (tmp_path / "copy.ts").write_text("new source")
    assert original["pairs_sha256"] == pack.snapshot(rows)["pairs_sha256"]
    assert original != pack.snapshot(rows)


def test_required_review_fails_before_pack_can_be_refreshed(monkeypatch):
    monkeypatch.setattr(
        pack.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(check=True, require_reviewed=True),
    )
    monkeypatch.setattr(pack, "load_rows", lambda: [])
    monkeypatch.setattr(pack, "accepted", lambda rows: False)
    monkeypatch.setattr(
        pack, "build", lambda: pytest.fail("must not treat regeneration as acceptance")
    )
    assert pack.main() == 1
