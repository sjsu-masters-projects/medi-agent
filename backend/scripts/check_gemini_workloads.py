"""Evaluate synthetic fixtures with explicit workload thinking and token budgets.

This is a text-only model check, not portal/OCR acceptance or clinical adjudication.
Triage uses the classifier proxy; it does not execute the coordinator's tools.
Reports retain synthetic final answers for review, never hidden reasoning or credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from google import genai
from google.genai import types

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "src"))

from app.adk.registry import Workload, route_for  # noqa: E402
from app.config import settings  # noqa: E402
from app.followup.models import SymptomExtractionResult  # noqa: E402
from app.models.ai_evaluation import EvalScenario  # noqa: E402
from app.models.generation import (  # noqa: E402
    GenerationErrorCode,
    GenerationTelemetry,
    ProviderTrial,
)
from app.services.ai_evaluation import (  # noqa: E402
    build_request,
    load_scenario_sets,
    score_trial,
)

WORKLOADS = {
    "triage_classification": Workload.TRIAGE,
    "document_extraction": Workload.EXTRACTION,
    "medication_discrepancy": Workload.DISCREPANCY,
    "adr_extraction": Workload.ADR_EXTRACTION,
    "patient_explanation": Workload.EXPLANATION,
}


async def run(args: argparse.Namespace) -> int:
    cases = [
        case
        for suite in load_scenario_sets(BACKEND / "tests/fixtures/eval")
        for case in suite.scenarios
        if not args.workload or case.workload.value in args.workload
    ]
    if args.case:
        cases = [case for case in cases if case.scenario_id in args.case]
    if not cases:
        raise ValueError("No synthetic cases selected")
    if getattr(args, "chat", False) and (args.model or args.thinking or args.fallback):
        raise ValueError(
            "Chat mode uses registry settings; model/thinking/fallback overrides are not supported"
        )
    if args.dry_run:
        print(f"Validated {len(cases)} synthetic cases; no provider calls")
        return 0
    if getattr(args, "chat", False):
        if any(case.workload.value != "triage_classification" for case in cases):
            raise ValueError("Chat mode requires --workload triage_classification")
        return await run_chat(args, cases)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    client = genai.Client(
        vertexai=True,
        project=settings.google_project_id,
        location="global",
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1), timeout=60000
        ),
    )
    rows = []
    try:
        for case in cases:
            route = route_for(WORKLOADS[case.workload.value])
            spec = route.fallback if args.fallback else route.primary
            if spec is None:
                continue
            production_contract = getattr(args, "production_contract", False)
            request = build_request(
                case, variant="production" if production_contract else "candidate"
            )
            if production_contract and case.workload.value == "adr_extraction":
                request.response_schema = SymptomExtractionResult.model_json_schema()
            model = args.model or spec.model_id
            thinking = args.thinking or route.thinking_level
            deadline = route.budget_seconds or 60.0
            started = time.monotonic()
            row = {
                "case": case.scenario_id,
                "locale": case.locale,
                "workload": case.workload.value,
                "model": model,
                "thinking": thinking,
                "max_output_tokens": route.max_output_tokens,
                "deadline_seconds": deadline,
                "endpoint": "global",
                "retries": 0,
                "fallback": False,
                "prompt_variant": "production" if production_contract else "candidate",
            }
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model,
                        contents=request.prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=request.system_instruction,
                            max_output_tokens=route.max_output_tokens,
                            thinking_config=types.ThinkingConfig(thinking_level=thinking),
                            response_mime_type=(
                                "application/json" if request.response_schema else None
                            ),
                            response_schema=request.response_schema,
                        ),
                    ),
                    timeout=deadline,
                )
                text = "".join(
                    part.text or ""
                    for candidate in response.candidates or []
                    for part in candidate.content.parts or []
                    if not part.thought
                )
                if production_contract and case.workload.value == "adr_extraction":
                    SymptomExtractionResult.model_validate_json(text)
                latency_ms = round((time.monotonic() - started) * 1000)
                finish_reason = (
                    str(response.candidates[0].finish_reason) if response.candidates else None
                )
                truncated = finish_reason == "FinishReason.MAX_TOKENS"
                trial = ProviderTrial(
                    provider="vertex_genai",
                    model=model,
                    ok=bool(text) and not truncated,
                    text=text,
                    error_code=GenerationErrorCode.TRUNCATED if truncated else None,
                    latency_ms=latency_ms,
                    telemetry=GenerationTelemetry(
                        provider="vertex_genai", model=model, latency_ms=latency_ms
                    ),
                )
                row.update(
                    ok=trial.ok,
                    text=text,
                    score=score_trial(case, trial).model_dump(mode="json"),
                    finish_reason=finish_reason,
                )
            except Exception as exc:
                # Exception messages can include request details; retain only safe fields.
                row.update(
                    ok=False, error_type=type(exc).__name__, status=str(getattr(exc, "code", ""))
                )
            row["latency_ms"] = round((time.monotonic() - started) * 1000)
            rows.append(row)
            args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                json.dumps({k: row[k] for k in ("case", "model", "thinking", "ok", "latency_ms")}),
                flush=True,
            )
            await asyncio.sleep(0.6)
    finally:
        await client.aio.aclose()
    return 0 if all(row["ok"] for row in rows) else 1


async def run_chat(args: argparse.Namespace, cases: list[EvalScenario]) -> int:
    """Run real chat models/tools with synthetic context and no database telemetry."""
    from app.adk.agents.care_coordinator.agent import TOOL_ALLOWLIST, build_care_coordinator
    from app.adk.chat_runtime import APP_NAME, CareCoordinatorRuntime
    from app.adk.runner import build_runner

    runner = build_runner(
        app_name=APP_NAME, agent=build_care_coordinator(), tool_allowlist=TOOL_ALLOWLIST
    )
    runtime = CareCoordinatorRuntime(runner=runner)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        with patch("app.adk.plugins.telemetry.schedule_generation_record"):
            for case in cases:
                context = MagicMock()
                context.get_context = AsyncMock(
                    return_value=case.inputs.get("patient_context") or {}
                )
                started = time.monotonic()
                with patch("app.adk.tools.patient_context._service", return_value=context):
                    events = [
                        event
                        async for event in runtime.process_stream(
                            patient_id="11111111-1111-1111-1111-111111111111",
                            user_id="synthetic-eval",
                            session_id=case.scenario_id,
                            message=case.inputs["message"],
                            language=case.locale,
                            document_context=case.inputs.get("document_context"),
                        )
                    ]
                decision = next((e for e in events if e["type"] == "classification"), {})
                final = next((e for e in reversed(events) if e["type"] == "complete"), {})
                ok = (
                    decision.get("urgency") == case.expected.get("urgency")
                    and not final.get("fallback_used", True)
                    and bool(final.get("response_text"))
                )
                rows.append(
                    {
                        "case": case.scenario_id,
                        "locale": case.locale,
                        "ok": ok,
                        "classification": decision,
                        "final": final,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                    }
                )
                args.out.write_text(
                    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
                await asyncio.sleep(0.6)
    finally:
        await runner.close()
    return 0 if all(row["ok"] for row in rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", action="append", choices=list(WORKLOADS), default=[])
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--model")
    parser.add_argument("--thinking", choices=["LOW", "MEDIUM", "HIGH"])
    parser.add_argument(
        "--fallback", action="store_true", help="Test declared fallback independently"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Run the real chat pipeline with in-memory sessions, synthetic patient reads and no database telemetry",
    )
    parser.add_argument(
        "--production-contract",
        action="store_true",
        help="Use production prompts and the live symptom schema rather than evaluation addenda",
    )
    parser.add_argument("--out", type=Path, default=BACKEND / "reports/gemini-workloads.json")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
