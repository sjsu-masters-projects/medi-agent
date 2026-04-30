#!/usr/bin/env python
"""Ingest curated DailyMed labels into the medication RAG knowledge table.

Examples:
    PYTHONPATH=src .venv/bin/python scripts/ingest_dailymed_rag.py \
      --drug metformin --drug lisinopril --dry-run

    PYTHONPATH=src .venv/bin/python scripts/ingest_dailymed_rag.py \
      --label metformin=00000000-0000-0000-0000-000000000000
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import Any, cast

import httpx
from supabase import Client

from app.clients.supabase import get_admin_client
from app.services.dailymed_service import BASE_URL, get_drug_label
from app.services.drug_knowledge_service import DrugKnowledgeService

DEFAULT_CURATED_DRUGS = (
    "metformin",
    "lisinopril",
    "atorvastatin",
    "furosemide",
    "aspirin",
    "clopidogrel",
    "empagliflozin",
    "insulin glargine",
)


@dataclass(frozen=True)
class LabelTarget:
    drug_name: str
    setid: str | None = None
    rxcui: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest curated DailyMed labels into drug_knowledge_chunks."
    )
    parser.add_argument(
        "--drug",
        action="append",
        default=[],
        help="Drug name to resolve through DailyMed /spls. May be repeated.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        help=(
            "Pinned label as drug_name=setid or drug_name=setid:rxcui. "
            "Use this for repeatable curated production ingestion."
        ),
    )
    parser.add_argument(
        "--default-curated",
        action="store_true",
        help="Ingest the repo's first curated medication set.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve labels and build chunks without writing to Supabase.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    targets = _build_targets(args)
    if not targets:
        print("No labels requested. Pass --drug, --label, or --default-curated.")
        return 2

    db = cast(Client, object()) if args.dry_run else get_admin_client()
    service = DrugKnowledgeService(db)
    total_chunks = 0
    failures: list[str] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for target in targets:
            resolved_setid = target.setid or await _resolve_latest_setid(client, target.drug_name)
            if not resolved_setid:
                failures.append(f"{target.drug_name}: no DailyMed SPL found")
                continue

            label = await get_drug_label(resolved_setid)
            if label.get("error"):
                failures.append(f"{target.drug_name}: {label['error']}")
                continue

            chunks = service.build_dailymed_label_chunks(
                label,
                drug_name=target.drug_name,
                rxcui=target.rxcui,
            )
            if args.dry_run:
                print(f"[dry-run] {target.drug_name}: setid={resolved_setid}, chunks={len(chunks)}")
                total_chunks += len(chunks)
                continue

            count = await service.ingest_dailymed_label(
                label,
                drug_name=target.drug_name,
                rxcui=target.rxcui,
            )
            print(f"ingested {target.drug_name}: setid={resolved_setid}, chunks={count}")
            total_chunks += count

    if failures:
        print("Failures:")
        for failure in failures:
            print(f"- {failure}")

    print(f"Total chunks {'resolved' if args.dry_run else 'ingested'}: {total_chunks}")
    return 1 if failures else 0


def _build_targets(args: argparse.Namespace) -> list[LabelTarget]:
    targets: list[LabelTarget] = []
    if args.default_curated:
        targets.extend(LabelTarget(drug_name=name) for name in DEFAULT_CURATED_DRUGS)

    targets.extend(LabelTarget(drug_name=drug.strip()) for drug in args.drug if drug.strip())
    targets.extend(_parse_label_target(item) for item in args.label)
    return _dedupe_targets(targets)


def _parse_label_target(value: str) -> LabelTarget:
    if "=" not in value:
        raise SystemExit(f"Invalid --label value '{value}'. Expected drug_name=setid[:rxcui].")

    drug_name, raw_label = value.split("=", maxsplit=1)
    setid, _, raw_rxcui = raw_label.partition(":")
    drug_name = drug_name.strip()
    setid = setid.strip()
    rxcui = raw_rxcui.strip() or None
    if not drug_name or not setid:
        raise SystemExit(f"Invalid --label value '{value}'. Drug name and setid are required.")
    return LabelTarget(drug_name=drug_name, setid=setid, rxcui=rxcui)


def _dedupe_targets(targets: list[LabelTarget]) -> list[LabelTarget]:
    deduped: list[LabelTarget] = []
    seen: set[tuple[str, str | None]] = set()
    for target in targets:
        key = (target.drug_name.lower(), target.setid)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


async def _resolve_latest_setid(client: httpx.AsyncClient, drug_name: str) -> str | None:
    response = await client.get(
        f"{BASE_URL}/spls.json",
        params={
            "drug_name": drug_name,
            "name_type": "both",
            "pagesize": 1,
            "page": 1,
        },
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    data: dict[str, Any] = response.json()
    rows = data.get("data") or []
    if not rows:
        return None

    first = rows[0]
    if not isinstance(first, dict):
        return None
    setid = first.get("setid")
    return str(setid).strip() if setid else None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
