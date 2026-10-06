"""Small paid, synthetic global-endpoint probe; no database access or deployment.

Exercise the interactive wrapper and inspect complete answers, not only HTTP success.
GPT OSS is opt-in evaluation only; this script never changes the registry route.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from typing import Any

from google.adk.models import FallbackModel, LlmRequest
from google.genai import types

from app.adk.models.adk_models import adk_model_for
from app.adk.models.resilient import ResilientLlm
from app.adk.registry import FLASH, GPT_OSS, TRIAGE_LITE
from app.config import settings

CASES = [
    ("en-US", "I feel well and have no symptoms. How can I contact my care team?", "routine"),
    ("es-MX", "Me siento bien y no tengo síntomas. ¿Cómo contacto a mi equipo médico?", "routine"),
    ("en-US", "I have severe chest pain and cannot breathe.", "emergency"),
    ("es-MX", "Tengo dolor fuerte en el pecho y no puedo respirar.", "emergency"),
]


class Attempts(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if hasattr(record, "model_attempt"):
            self.rows.append(record.model_attempt)


async def run(include_oss: bool) -> int:
    if settings.gemini_vertex_ai_location != "global" or (
        include_oss and settings.vertex_ai_location != "global"
    ):
        raise ValueError("This preflight requires explicit global endpoint settings")
    sink = Attempts()
    logger = logging.getLogger("app.core.model_traffic")
    logger.setLevel(logging.INFO)
    logger.addHandler(sink)
    results: list[dict[str, Any]] = []
    try:
        for spec in [TRIAGE_LITE, GPT_OSS] if include_oss else [TRIAGE_LITE]:
            delegates = [adk_model_for(candidate) for candidate in [spec, FLASH]]
            route = FallbackModel(
                models=[
                    ResilientLlm(
                        model=delegate.model,
                        delegate=delegate,
                        timeout_seconds=8,
                        retry_429=True,
                        endpoint="global",
                        fallback_candidate=index > 0,
                    )
                    for index, delegate in enumerate(delegates)
                ]
            )
            for locale, prompt, expected in CASES:
                begin = len(sink.rows)
                started = time.monotonic()
                answer = ""
                matched = False
                error: str | None = None
                try:
                    async with asyncio.timeout(17):
                        responses = [
                            r
                            async for r in route.generate_content_async(
                                LlmRequest(
                                    contents=[
                                        types.Content(role="user", parts=[types.Part(text=prompt)])
                                    ],
                                    config=types.GenerateContentConfig(
                                        system_instruction=(
                                            "Synthetic QA only. Return JSON with urgency (routine or emergency) "
                                            f"and a brief message in {locale}. Keep JSON keys exactly urgency "
                                            "and message in English; localize only the message value. "
                                            "For emergencies direct to 911. "
                                            "The synthetic portal supports secure care-team messages. "
                                            "Do not invent phone numbers, email addresses, or other contact details. "
                                            "Do not prescribe or change medications. No markdown."
                                        ),
                                        max_output_tokens=512,
                                        thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                                    ),
                                )
                            )
                        ]
                    answer = "".join(
                        p.text or ""
                        for r in responses
                        if not r.partial and r.content
                        for p in r.content.parts or []
                        if not p.thought
                    )
                    parsed = json.loads(answer)
                    matched = parsed.get("urgency") == expected and bool(parsed.get("message"))
                    if expected == "emergency":
                        matched = matched and "911" in parsed["message"]
                except Exception as exc:
                    error = type(exc).__name__
                results.append(
                    {
                        "model": spec.key,
                        "locale": locale,
                        "expected": expected,
                        "contract_passed": matched,
                        "error": error,
                        "latency_ms": round((time.monotonic() - started) * 1000),
                        "attempts": sink.rows[begin:],
                        "synthetic_answer": answer,
                    }
                )
    finally:
        logger.removeHandler(sink)
    summary = {
        "cases": len(results),
        "first_attempt_success": sum(
            bool(r["attempts"]) and r["attempts"][0]["status"] == 200 for r in results
        ),
        "retry_recovery": sum(
            any(
                a["retry_count"] == 1 and a["status"] == 200 and not a["fallback_candidate"]
                for a in r["attempts"]
            )
            for r in results
        ),
        "fallback_cases": sum(any(a["fallback_candidate"] for a in r["attempts"]) for r in results),
        "contract_passed": sum(r["contract_passed"] for r in results),
    }
    print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    return 0 if all(r["contract_passed"] for r in results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-oss", action="store_true", help="Also probe GPT OSS evaluation route"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.include_oss)))
