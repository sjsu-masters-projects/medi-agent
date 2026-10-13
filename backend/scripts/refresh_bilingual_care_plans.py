#!/usr/bin/env python
"""Report and, after review, start bilingual wording for existing care plans.

Nothing is approved or published: open drafts get their missing language drafted for
clinician review, and approved single-language plans get a normal generation request.
Run against a synthetic environment only, after migration 049 is applied.

Examples:
    PYTHONPATH=src .venv/bin/python scripts/refresh_bilingual_care_plans.py --dry-run
    PYTHONPATH=src .venv/bin/python scripts/refresh_bilingual_care_plans.py \
      --apply --report-sha256 <dry-run-sha>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from uuid import UUID

from app.clients.supabase import get_admin_client
from app.services.care_plan_bilingual_refresh import BilingualRefreshService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", type=UUID, help="Limit the report to one patient.")
    parser.add_argument("--dry-run", action="store_true", help="Print only the report.")
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed report.")
    parser.add_argument("--report-sha256", help="SHA-256 from a reviewed dry run.")
    args = parser.parse_args(argv)
    if args.dry_run == args.apply:
        parser.error("Choose exactly one of --dry-run or --apply.")
    if args.apply and not args.report_sha256:
        parser.error("--apply requires --report-sha256 from a reviewed dry run.")
    return args


async def run(args: argparse.Namespace) -> int:
    service = BilingualRefreshService(get_admin_client())
    proposals = service.proposals(patient_id=args.patient_id)
    payload = [proposal.to_dict() for proposal in proposals]
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    print(
        json.dumps(
            {"proposal_count": len(payload), "sha256": digest, "proposals": payload},
            indent=2,
            sort_keys=True,
        )
    )
    if args.dry_run:
        return 0
    if args.report_sha256 != digest:
        raise SystemExit("The reviewed report no longer matches current plans; re-run the dry run.")
    for proposal in proposals:
        print(json.dumps({"applied": await service.apply(proposal)}, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
