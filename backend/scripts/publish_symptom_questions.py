"""Release the active symptom question version to a database.

The manifest chooses the active version; the database must approve that same version and
hash before an intake can start. This is the one command that keeps them in step. It prints
what it would do unless --apply is passed, is safe to repeat, and refuses to change an
already published version. See src/app/intake/question_library/README.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.intake.library import load_library

MANIFEST = Path(__file__).resolve().parents[1] / "src/app/intake/question_library/manifest.json"


def active_release() -> dict[str, Any]:
    """The active version, validated by the same loader the running service uses."""
    bundle = load_library()
    entry = json.loads(MANIFEST.read_text())["bundles"][bundle.version]
    return {"version": bundle.version, "hash": bundle.checksum, "approval": entry["approval"]}


def is_published(db: Any, release: dict[str, Any]) -> bool:
    result = (
        db.rpc(
            "symptom_intake_readiness",
            {
                "p_version": release["version"],
                "p_hash": release["hash"],
                "p_approval": release["approval"],
            },
        )
        .execute()
        .data
    )
    matches = result.get("eligibility_matches") if isinstance(result, dict) else None
    if not isinstance(matches, bool):
        raise ValueError("Invalid readiness response")
    return matches


def publish(db: Any, release: dict[str, Any]) -> None:
    db.rpc(
        "set_symptom_question_eligibility",
        {
            "p_version": release["version"],
            "p_hash": release["hash"],
            "p_status": "approved",
            "p_approval": release["approval"],
        },
    ).execute()


def run(db: Any, release: dict[str, Any], *, apply: bool) -> int:
    print("ACTIVE_VERSION", release["version"], release["hash"])
    if is_published(db, release):
        print("ALREADY_PUBLISHED nothing to do")
        return 0
    if not apply:
        print("NOT_PUBLISHED dry run: pass --apply to publish this version")
        return 0
    publish(db, release)
    if not is_published(db, release):
        print("PUBLISH_FAILED the database does not report this version as approved")
        return 1
    print("PUBLISHED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Publish; otherwise only report")
    args = parser.parse_args()

    from app.config import settings
    from app.db.connection import get_db

    print("TARGET", urlparse(settings.supabase_url).hostname)
    try:
        return run(get_db(), active_release(), apply=args.apply)
    except Exception as exc:
        # Type and code only: never print settings, keys or response bodies.
        print("PUBLISH_ERROR", type(exc).__name__, getattr(exc, "code", "transport"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
