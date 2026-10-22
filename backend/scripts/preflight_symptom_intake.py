"""Read-only symptom rollout preflight. Never applies SQL or publishes eligibility."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.intake.library import load_library

ROOT = Path(__file__).resolve().parents[1] / "src/app"
REQUIRED = (
    "059_chat_safety_alerts.sql",
    "060_confirmed_symptom_intake.sql",
    "065_clinic_memberships.sql",
    "071_confirmed_symptom_handoff.sql",
    "072_nora_turn_recovery.sql",
    "073_nora_turn_begin_validation.sql",
    "074_nora_late_completion.sql",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-target",
        action="store_true",
        help="Read the configured target ledger and eligibility; no mutations",
    )
    args = parser.parse_args()
    bundle = load_library()
    manifest = json.loads((ROOT / "intake/question_library/manifest.json").read_text())
    entry = manifest["bundles"][bundle.version]
    print("PACKAGED_LIBRARY_PASS", bundle.version, bundle.checksum)
    checks: dict[str, bool] = {}
    if args.check_target:
        from app.config import settings
        from app.db.connection import get_db

        checks["runtime_intake_enabled"] = settings.symptom_intake_enabled
        checks["runtime_retry_worker_enabled"] = settings.a2a_retry_worker_enabled
        try:
            db = get_db()
            rows = (
                db.table("schema_migrations")
                .select("filename,checksum")
                .in_("filename", list(REQUIRED))
                .execute()
                .data
            )
            if not isinstance(rows, list):
                raise ValueError("Invalid migration ledger response")
            ledger: dict[str, str] = {}
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Invalid migration ledger row")
                filename, checksum = row.get("filename"), row.get("checksum")
                if not isinstance(filename, str) or not isinstance(checksum, str):
                    raise ValueError("Invalid migration ledger identity")
                ledger[filename] = checksum
            for name in REQUIRED:
                expected = hashlib.sha256((ROOT / "db/migrations" / name).read_bytes()).hexdigest()
                print(
                    "TARGET_MIGRATION",
                    name,
                    "PASS" if ledger.get(name) == expected else "MISSING_OR_MISMATCH",
                )
            checks["target_migration_checksums"] = all(
                ledger.get(name)
                == hashlib.sha256((ROOT / "db/migrations" / name).read_bytes()).hexdigest()
                for name in REQUIRED
            )
            if checks["target_migration_checksums"]:
                result = (
                    db.rpc(
                        "symptom_intake_readiness",
                        {
                            "p_version": bundle.version,
                            "p_hash": bundle.checksum,
                            "p_approval": entry["approval"],
                        },
                    )
                    .execute()
                    .data
                )
                expected_keys = {
                    "eligibility_matches",
                    "browser_report_writes_denied",
                    "browser_task_writes_denied",
                    "handoff_trigger_present",
                }
                if (
                    not isinstance(result, dict)
                    or set(result) != expected_keys
                    or not all(isinstance(value, bool) for value in result.values())
                ):
                    raise ValueError("Invalid readiness response")
                checks.update({key: bool(value) for key, value in result.items()})
        except Exception as exc:
            print("TARGET_CHECK_FAILED", type(exc).__name__, getattr(exc, "code", "transport"))
            return 1
    else:
        for name in REQUIRED:
            print(
                "REQUIRED_MIGRATION",
                name,
                hashlib.sha256((ROOT / "db/migrations" / name).read_bytes()).hexdigest(),
            )
        print(
            "Target not contacted. Use --check-target in the intended runtime configuration before rollout."
        )
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL"), name)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
