"""Run the NORA-002 question set against Nora for one synthetic patient and score it.

Each case runs as its own fresh conversation through the same runtime the chat route uses,
including the route's symptom hand-off and its severity escalation, then checks the
classification, which sources the server cited, and required or forbidden wording.

    PYTHONPATH=src .venv/bin/python scripts/check_nora_answers.py --patient-id <uuid>

Use only a synthetic patient. The script reads that patient's record and the shared
reference cache, may fill the cache from the public NLM services, and writes nothing else:
no chat messages, symptom reports or alerts are stored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from app.adk.chat_runtime import CareCoordinatorRuntime
from app.clients.supabase import get_admin_client
from app.followup import analyse_symptom
from app.followup.service import EMERGENCY_THRESHOLD
from app.services.chat_service import ChatService

CASES = Path(__file__).resolve().parents[1] / "tests/fixtures/nora/grounded_answers.json"
SOURCE_NAMES = {"medlineplus": "MedlinePlus", "dailymed": "DailyMed"}


async def run_case(case: dict[str, Any], patient_id: str) -> dict[str, Any]:
    runtime = CareCoordinatorRuntime()
    started = time.monotonic()
    urgency, route, chunks, answer = "routine", "triage", [], ""
    stream = runtime.process_stream(
        patient_id=patient_id,
        user_id=patient_id,
        session_id=f"check-{uuid.uuid4().hex[:12]}",
        message=case["message"],
        language=case["locale"],
        earlier_messages=[],
    )
    async for event in stream:
        if event["type"] == "classification":
            urgency, route = str(event.get("urgency")), str(event.get("route"))
            if route == "symptom" and urgency != "emergency":
                await stream.aclose()  # the route hands symptoms to the follow-up worker
                break
        elif event["type"] == "chunk":
            chunks.append(str(event.get("content") or ""))
        elif event["type"] == "complete":
            answer = str(event.get("response_text") or "")
    if route == "symptom" and urgency != "emergency":
        context = await ChatService(get_admin_client()).get_context(patient_id=patient_id)
        result = await analyse_symptom(
            message=case["message"], language=case["locale"], patient_context=context
        )
        answer = result.response_text
        severity = int((result.symptom_report or {}).get("severity") or 0)
        if (severity >= EMERGENCY_THRESHOLD or result.flagged_for_adr) and urgency == "routine":
            urgency = "urgent"
    answer = answer or "".join(chunks)
    return {
        "urgency": urgency,
        "route": route,
        "answer": answer,
        "seconds": round(time.monotonic() - started, 1),
    }


def score(case: dict[str, Any], outcome: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    text = outcome["answer"].casefold()
    last_line = outcome["answer"].strip().splitlines()[-1] if outcome["answer"].strip() else ""
    cited = {key for key, name in SOURCE_NAMES.items() if name in last_line}
    missing = set(case.get("expect_sources") or []) - cited
    if missing:
        problems.append(f"missing source {sorted(missing)}")
    if case.get("expect_urgency") and outcome["urgency"] not in case["expect_urgency"]:
        problems.append(f"urgency {outcome['urgency']} not in {case['expect_urgency']}")
    wanted = case.get("must_include_any") or []
    if wanted and not any(item.casefold() in text for item in wanted):
        problems.append(f"none of {wanted}")
    for item in case.get("must_not_include") or []:
        if item.casefold() in text:
            problems.append(f"forbidden {item!r}")
    return problems


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--patient-id", required=True, help="A synthetic patient's id.")
    parser.add_argument("--only", nargs="*", help="Case ids to run.")
    parser.add_argument("--show", action="store_true", help="Print each answer.")
    args = parser.parse_args()
    patient_id = str(uuid.UUID(args.patient_id))
    cases = json.loads(CASES.read_text())["cases"]
    if args.only:
        cases = [case for case in cases if case["id"] in set(args.only)]

    failures = 0
    for case in cases:
        try:
            outcome = await run_case(case, patient_id)
            problems = score(case, outcome)
        except Exception as error:  # noqa: BLE001 - report the case and continue
            outcome, problems = {"seconds": 0, "urgency": "-", "answer": ""}, [repr(error)]
        failures += bool(problems)
        status = "FAIL" if problems else "pass"
        print(
            f"{status} {case['id']} {case['locale']} {outcome['urgency']:<9} {outcome['seconds']:>5}s  {'; '.join(problems)}"
        )
        if args.show or problems:
            print("     " + outcome["answer"].replace("\n", "\n     "))
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
