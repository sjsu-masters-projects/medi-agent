#!/usr/bin/env python
"""Produce and, after report review, apply safe FHIR candidate reprojections.

Examples:
    PYTHONPATH=src .venv/bin/python scripts/reproject_fhir_candidates.py --dry-run
    PYTHONPATH=src .venv/bin/python scripts/reproject_fhir_candidates.py \
      --apply --actor-id <assigned-clinician-id> --report-sha256 <dry-run-sha>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any
from uuid import UUID

from app.clients.supabase import get_admin_client
from app.services.fhir_candidate_reprojection_service import FhirCandidateReprojectionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", type=UUID, help="Limit the report to one local patient.")
    parser.add_argument("--dry-run", action="store_true", help="Print only the proposal report.")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the exact freshly generated report."
    )
    parser.add_argument(
        "--actor-id", type=UUID, help="Assigned clinician authorizing an apply run."
    )
    parser.add_argument(
        "--report-sha256",
        help="SHA-256 from a reviewed dry-run report; required with --apply.",
    )
    return parser.parse_args()


def report_payload(proposals: list[dict[str, Any]]) -> str:
    return json.dumps(proposals, sort_keys=True, separators=(",", ":"))


def main() -> int:
    args = parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("Choose exactly one of --dry-run or --apply.")
    if args.apply and (args.actor_id is None or not args.report_sha256):
        raise SystemExit("--apply requires --actor-id and --report-sha256 from a reviewed dry run.")

    service = FhirCandidateReprojectionService(get_admin_client())
    proposals = service.list_proposals(patient_id=args.patient_id)
    payload = [proposal.to_dict() for proposal in proposals]
    digest = hashlib.sha256(report_payload(payload).encode()).hexdigest()
    report = {"proposal_count": len(payload), "sha256": digest, "proposals": payload}
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.dry_run:
        return 0
    if args.report_sha256 != digest:
        raise SystemExit(
            "The reviewed report hash does not match the current eligible proposals; re-run dry-run."
        )

    for proposal in proposals:
        result = service.apply(proposal, actor_id=args.actor_id)
        print(json.dumps({"applied": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
