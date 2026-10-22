"""The deploy workflow and the account setup script must agree on the jobs runtime account."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-backend.yml"
SCRIPT = ROOT / "scripts" / "setup-runtime-service-accounts.sh"
JOB_STEPS = ("Deploy document-ingestion job", "Deploy health-knowledge refresh job")


def _steps() -> dict[str, str]:
    """Return each workflow step's raw text keyed by its name (no YAML dependency)."""
    text = WORKFLOW.read_text()
    parts = re.split(r"^      - name: ", text, flags=re.MULTILINE)[1:]
    return {part.splitlines()[0].strip(): part for part in parts}


def test_job_steps_use_jobs_runtime_account_with_fallback() -> None:
    steps = _steps()
    for name in JOB_STEPS:
        step = steps[name]
        assert "CLOUD_RUN_JOBS_RUNTIME_SA: ${{ vars.CLOUD_RUN_JOBS_RUNTIME_SA }}" in step
        assert "--service-account ${CLOUD_RUN_JOBS_RUNTIME_SA:-${RUNTIME_SERVICE_ACCOUNT}}" in step


def test_jobs_account_variable_is_format_checked() -> None:
    check = _steps()["Check required runtime settings"]
    assert "CLOUD_RUN_JOBS_RUNTIME_SA: ${{ vars.CLOUD_RUN_JOBS_RUNTIME_SA }}" in check
    assert "CLOUD_RUN_JOBS_RUNTIME_SA; do" in check


def test_dry_run_creates_jobs_account_and_changes_nothing(tmp_path: Path) -> None:
    # A stand-in gcloud that knows no accounts, so the dry run never depends on whoever runs
    # the test being signed in to the real project (where the accounts may already exist).
    fake = tmp_path / "gcloud"
    fake.write_text("#!/usr/bin/env bash\nexit 1\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"}
    out = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, check=False, env=env
    ).stdout
    assert "MODE: DRY RUN" in out
    assert "service-accounts create mediagent-jobs-runtime" in out
    assert "--role roles/aiplatform.user" in out


def test_job_secrets_in_script_match_workflow() -> None:
    run = _steps()[JOB_STEPS[0]]
    script = SCRIPT.read_text()
    for secret in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
    ):
        assert f"{secret}={secret}:latest" in run
        assert secret in script.split("JOBS_SECRETS=(")[1].split(")")[0]
