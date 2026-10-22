"""Review inventory reads static source and preserves wording, never imports it."""

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
        'COPY = {"en-US": {"label": "Hello"}, "es-MX": {"label": "Hola"}}\n'
    )
    monkeypatch.setattr(pack, "ROOT", tmp_path)
    assert pack.python_rows("copy.py")[0]["es"] == "Hola"


def test_missing_english_counterpart_fails_instead_of_inventing_copy(tmp_path, monkeypatch):
    (tmp_path / "copy.py").write_text('COPY = {"en-US": {}, "es-MX": {"label": "Hola"}}')
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
        pack.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(check=True)
    )
    assert pack.main() == 1
    pack.DESTINATION.write_text("old\n")
    assert pack.main() == 1
    pack.DESTINATION.write_text("expected\n")
    assert pack.main() == 0
