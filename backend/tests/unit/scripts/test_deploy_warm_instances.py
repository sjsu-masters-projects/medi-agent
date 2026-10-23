"""OPS-005: both services must keep one warm instance.

With min-instances 0 the first request after idle waited 9-45 s for a new instance; that
was the cause of the intermittent page failures (docs/evidence/ops-005-rca-2026-10.md).
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "deploy-backend.yml"


def _deploy_commands() -> list[str]:
    text = WORKFLOW.read_text()
    return re.findall(r"gcloud run deploy[^\n]*(?:\n[^\n]*\\)*\n[^\n]*", text)


def test_api_and_worker_deploys_keep_one_warm_instance() -> None:
    commands = _deploy_commands()
    assert len(commands) >= 2, "expected the API and the chat-worker deploy commands"
    for command in commands:
        assert re.search(r"--min-instances[ =]1\b", command), command.splitlines()[0]
