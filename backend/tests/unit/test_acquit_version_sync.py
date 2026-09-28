"""Keep the Acquit package and GitHub Action release pins synchronized."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ACQUIT_VERSION = "0.3.0"
ACQUIT_ACTION_SHA = "ca647e83986768b62b50343ec7b23dff87921293"


def test_acquit_canary_uses_the_verified_release_everywhere() -> None:
    requirements = (REPOSITORY_ROOT / "backend" / "requirements-dev.in").read_text()
    lock = (REPOSITORY_ROOT / "backend" / "requirements-dev.txt").read_text()
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert f"acquit=={ACQUIT_VERSION}" in requirements
    assert f"acquit=={ACQUIT_VERSION}" in lock
    assert f"rajeev-chaurasia/acquit@{ACQUIT_ACTION_SHA} # v{ACQUIT_VERSION}" in workflow
    assert f'acquit-version: "{ACQUIT_VERSION}"' in workflow
    assert "mode: canary" in workflow
