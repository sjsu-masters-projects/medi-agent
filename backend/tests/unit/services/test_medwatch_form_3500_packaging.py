"""The vendored Form 3500 template ships with the backend package and image (R15.2)."""

import fnmatch
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
ASSET_DIR = BACKEND / "src" / "app" / "assets" / "fda"


def test_asset_directory_holds_the_template_record_and_readme() -> None:
    names = {path.name for path in ASSET_DIR.iterdir()}
    assert {"form-3500-2025-09.pdf", "TEMPLATE.json", "README.md"} <= names


def test_package_data_glob_covers_every_asset_file() -> None:
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    globs = config["tool"]["setuptools"]["package-data"]["app"]
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    for path in ASSET_DIR.iterdir():
        relative = path.relative_to(BACKEND / "src" / "app").as_posix()
        assert any(fnmatch.fnmatch(relative, pattern) for pattern in globs), relative


def test_docker_image_copies_the_source_tree_with_the_assets() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    copies = [line.split() for line in dockerfile.splitlines() if line.startswith("COPY ")]
    assert ["COPY", "src/", "./src/"] in copies
    assert "ENV PYTHONPATH=/app/src" in dockerfile
    ignore = BACKEND / ".dockerignore"
    if ignore.exists():
        patterns = [
            line.strip()
            for line in ignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        for path in (
            "src/app/assets/fda/form-3500-2025-09.pdf",
            "src/app/assets/fda/TEMPLATE.json",
        ):
            assert not any(fnmatch.fnmatch(path, pattern) for pattern in patterns), path
