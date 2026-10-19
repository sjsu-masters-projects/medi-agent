"""Applied historical names stay stable; new sequence collisions fail CI."""

from pathlib import Path

import pytest
from scripts import validate_migrations as validator


def migration(directory: Path, number: int, name: str) -> None:
    (directory / f"{number:03d}_{name}.sql").write_text("SELECT 1;\n")


@pytest.mark.parametrize("sequence", [71, 72, 73, 74])
def test_new_duplicate_prefixes_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sequence: int
):
    monkeypatch.setattr(validator, "MIGRATIONS_DIR", tmp_path)
    for number in range(1, sequence + 1):
        migration(tmp_path, number, "existing")
    migration(tmp_path, sequence, "new_collision")
    assert any(
        f"duplicate migration sequence {sequence:03d}" in error
        for error in validator.validate_migrations()
    )


def test_historical_shared_prefix_is_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(validator, "MIGRATIONS_DIR", tmp_path)
    for number in range(1, 49):
        migration(tmp_path, number, "existing")
    migration(tmp_path, 48, "independent_historical")
    assert validator.validate_migrations() == []


def test_gaps_are_still_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(validator, "MIGRATIONS_DIR", tmp_path)
    migration(tmp_path, 1, "first")
    migration(tmp_path, 3, "third")
    assert "Missing migration sequence(s): 002" in validator.validate_migrations()
