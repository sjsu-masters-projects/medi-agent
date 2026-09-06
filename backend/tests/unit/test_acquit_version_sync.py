"""Keep the Acquit package and GitHub Action release pins synchronized."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ACQUIT_VERSION = "0.2.0"
ACQUIT_ACTION_SHA = "b992c5820a0fd059ec8f8ef640f30cec7be29c55"


def test_acquit_canary_uses_the_verified_release_everywhere() -> None:
    requirements = (REPOSITORY_ROOT / "backend" / "requirements-dev.in").read_text()
    lock = (REPOSITORY_ROOT / "backend" / "requirements-dev.txt").read_text()
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert f"acquit=={ACQUIT_VERSION}" in requirements
    assert f"acquit=={ACQUIT_VERSION}" in lock
    assert f"rajeev-chaurasia/acquit@{ACQUIT_ACTION_SHA} # v{ACQUIT_VERSION}" in workflow
    assert f'acquit-version: "{ACQUIT_VERSION}"' in workflow
    assert "mode: canary" in workflow
