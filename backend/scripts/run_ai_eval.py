"""Run the synthetic evaluation scenarios across providers and score every answer.

`EVA-001` compares providers per workload on accuracy, safety, schema validity,
abstention, latency, and cost. `compare_providers.py` asks one prompt; this script asks
the whole gold-labeled scenario set, scores each answer against its label, and writes a
report the team can review and a clinician can adjudicate.

    # Validate the scenario files without calling anything
    python backend/scripts/run_ai_eval.py --dry-run

    # Router models (Vertex credentials) plus any OpenAI-compatible endpoint
    python backend/scripts/run_ai_eval.py --models flash,pro \\
        --provider "gemma4=https://generativelanguage.googleapis.com/v1beta/openai|gemma-4-26b-a4b-it|GOOGLE_API_KEY" \\
        --provider "local=http://localhost:11434/v1|medgemma-1.5-4b|" \\
        --workload triage_classification --pause-seconds 4

Needs live credentials for anything but `--dry-run`. Synthetic scenarios only: the
scenario files are the only input this script will read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.ai_evaluation import EvalRunReport, EvalScenario, ScenarioScore, WorkloadSummary
    from app.services.generation_providers import TextProvider

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "src"))

DEFAULT_SCENARIOS = BACKEND_ROOT / "tests" / "fixtures" / "eval"
DEFAULT_REPORTS = BACKEND_ROOT / "reports"


@dataclass(frozen=True)
class ProviderSpec:
    """One `--provider NAME=BASE_URL|MODEL|KEY_ENV[|REASONING_EFFORT]` argument, parsed."""

    name: str
    base_url: str
    model: str
    api_key_env: str | None
    # Thinking models answer at a default effort far slower than a chat turn can
    # afford; this lets the comparison run them at the level we would deploy.
    reasoning_effort: str | None = None


_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high"})


def parse_provider_spec(raw: str) -> ProviderSpec:
    name, _, rest = raw.partition("=")
    parts = rest.split("|")
    if not name or len(parts) < 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            f"provider must look like NAME=BASE_URL|MODEL|KEY_ENV[|EFFORT], got {raw!r}"
        )
    key_env = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    effort = parts[3].strip().lower() if len(parts) > 3 and parts[3].strip() else None
    if effort is not None and effort not in _REASONING_EFFORTS:
        raise argparse.ArgumentTypeError(
            f"reasoning effort must be one of {sorted(_REASONING_EFFORTS)}, got {effort!r}"
        )
    return ProviderSpec(
        name=name.strip(),
        base_url=parts[0].strip(),
        model=parts[1].strip(),
        api_key_env=key_env,
        reasoning_effort=effort,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--scenarios", type=Path, default=DEFAULT_SCENARIOS, help="Scenario directory"
    )
    parser.add_argument(
        "--workload", action="append", default=[], help="Limit to a workload (repeatable)"
    )
    parser.add_argument("--locale", choices=["en-US", "es-MX"], help="Limit to one locale")
    parser.add_argument("--risk", choices=["low", "medium", "high"], help="Limit to one risk level")
    parser.add_argument(
        "--limit", type=int, default=0, help="Stop after N scenarios per workload (0 = all)"
    )
    parser.add_argument(
        "--models", default="", help="Comma-separated router model names (flash, pro)"
    )
    parser.add_argument(
        "--provider",
        action="append",
        type=parse_provider_spec,
        default=[],
        help="OpenAI-compatible provider: NAME=BASE_URL|MODEL|KEY_ENV",
    )
    parser.add_argument(
        "--prompt-variant",
        choices=["production", "candidate"],
        default="candidate",
        help="candidate adds evidence/red-flag fields the spike requires",
    )
    parser.add_argument(
        "--no-native-schema",
        action="store_true",
        help="Do not request native JSON-schema output from OpenAI-compatible providers",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.0,
        help="Sleep between scenarios (free-tier pacing)",
    )
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry 429 and transient 5xx responses with exponential backoff.",
    )
    parser.add_argument(
        "--max-tokens-scale",
        type=float,
        default=1.0,
        help="Multiply every request's max_tokens. Reasoning models spend the budget on "
        "thinking before answering, so a fair comparison needs more room than a "
        "non-reasoning model.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORTS, help="Report directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Load and validate scenarios, call nothing"
    )
    return parser.parse_args(argv)


def _select(scenarios: list[EvalScenario], args: argparse.Namespace) -> list[EvalScenario]:
    chosen: list[EvalScenario] = []
    per_workload: dict[str, int] = {}
    for scenario in scenarios:
        if args.workload and scenario.workload.value not in args.workload:
            continue
        if args.locale and scenario.locale != args.locale:
            continue
        if args.risk and scenario.risk.value != args.risk:
            continue
        count = per_workload.get(scenario.workload.value, 0)
        if args.limit and count >= args.limit:
            continue
        per_workload[scenario.workload.value] = count + 1
        chosen.append(scenario)
    return chosen


ADC_CREDENTIALS = "ADC"


def _google_adc_bearer() -> Callable[[], str]:
    """Return a callable that yields a current Google access token.

    A token printed by gcloud lasts an hour, which a full run outlives. Reading Application
    Default Credentials and refreshing them on expiry keeps the end of a long run from
    turning into authentication errors.
    """
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    request = Request()

    def token() -> str:
        if not credentials.valid:
            credentials.refresh(request)
        return str(credentials.token)

    token()  # Fail at startup rather than on the first scenario.
    return token


def _resolve_providers(args: argparse.Namespace) -> tuple[list[TextProvider], list[str]]:
    """Router models plus OpenAI-compatible endpoints; report the ones that cannot start."""
    providers: list[TextProvider] = []
    unavailable: list[str] = []

    router_names = [name.strip() for name in args.models.split(",") if name.strip()]
    if router_names:
        from app.clients.model_router import ModelRouter

        router = ModelRouter()
        for name in router_names:
            try:
                providers.append(router.get_text_provider_for_model(name))
            except Exception as error:  # noqa: BLE001 - report and continue
                unavailable.append(f"{name} ({error})")

    from app.clients.openai_compatible import OpenAICompatibleTextProvider

    adc_bearer: Callable[[], str] | None = None
    for spec in args.provider:
        bearer_token: Callable[[], str] | None = None
        api_key: str | None = None
        if spec.api_key_env == ADC_CREDENTIALS:
            try:
                adc_bearer = adc_bearer or _google_adc_bearer()
            except Exception as error:  # noqa: BLE001 - report and continue
                unavailable.append(f"{spec.name} (application default credentials: {error})")
                continue
            bearer_token = adc_bearer
        else:
            api_key = os.environ.get(spec.api_key_env, "") if spec.api_key_env else None
            if spec.api_key_env and not api_key:
                # Settings may hold the key even when the shell does not export it.
                from app.config import settings

                api_key = str(getattr(settings, spec.api_key_env.lower(), "") or "")
            if spec.api_key_env and not api_key:
                unavailable.append(f"{spec.name} ({spec.api_key_env} is not set)")
                continue
        providers.append(
            OpenAICompatibleTextProvider(
                name=spec.name,
                model=spec.model,
                base_url=spec.base_url,
                api_key=api_key or None,
                timeout_seconds=args.timeout_seconds,
                native_structured_output=not args.no_native_schema,
                reasoning_effort=spec.reasoning_effort,
                max_retries=args.max_retries,
                bearer_token=bearer_token,
            )
        )
    return providers, unavailable


def _environment(args: argparse.Namespace, providers: list[TextProvider]) -> dict[str, Any]:
    from app.config import settings
    from app.services.ai_evaluation import PRICING_SNAPSHOT_DATE

    def _version(module: str) -> str | None:
        try:
            from importlib.metadata import version

            return version(module)
        except Exception:  # noqa: BLE001 - metadata is best effort
            return None

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        commit = ""

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": commit or None,
        "packages": {
            name: _version(name)
            for name in ("google-genai", "google-cloud-aiplatform", "httpx", "pydantic")
        },
        "router_models": {
            "flash": settings.gemini_flash_model,
            "pro": settings.gemini_pro_model,
        },
        "providers": [
            {
                "name": p.name,
                "model": p.model,
                # Which endpoint served the call. Without it a report records what was
                # asked and not where it was asked, so a later reader cannot tell a
                # regional endpoint from the global one, or a managed endpoint from a
                # self-hosted container — and the 2026-09-17 run that our routing rests
                # on had to have its endpoint reconstructed from a spec written weeks
                # earlier, because this field did not exist.
                "base_url": getattr(p, "base_url", None),
                "reasoning_effort": getattr(p, "reasoning_effort", None),
                "native_structured_output": getattr(p, "native_structured_output", None),
            }
            for p in providers
        ],
        "prompt_variant": args.prompt_variant,
        "native_schema": not args.no_native_schema,
        "pricing_snapshot": PRICING_SNAPSHOT_DATE,
        # Without these, a later reader cannot separate a model's result from the
        # settings it ran under. The September run's token multiplier had to be
        # reverse-engineered from token counts months later.
        "run_parameters": {
            "max_tokens_scale": args.max_tokens_scale,
            "max_retries": args.max_retries,
            "timeout_seconds": args.timeout_seconds,
            "pause_seconds": args.pause_seconds,
            "sequential_providers": True,
        },
    }


async def _run(args: argparse.Namespace) -> int:
    from app.models.ai_evaluation import EvalRunReport, ScenarioScore
    from app.models.generation import MAX_OUTPUT_TOKENS
    from app.services.ai_evaluation import (
        _disposition_for,
        build_request,
        load_scenario_sets,
        score_trial,
        summarize,
    )

    if not args.scenarios.is_dir():
        print(f"error: {args.scenarios} is not a directory", file=sys.stderr)
        return 2
    sets = load_scenario_sets(args.scenarios)
    scenarios = _select([s for group in sets for s in group.scenarios], args)
    versions = {group.workload.value: group.version for group in sets}
    print(f"loaded {sum(len(g.scenarios) for g in sets)} scenarios, selected {len(scenarios)}")

    if args.dry_run:
        for scenario in scenarios:
            request = build_request(scenario, variant=args.prompt_variant)
            print(
                f"  {scenario.scenario_id} {scenario.locale} {scenario.risk.value:6} prompt={len(request.prompt)} chars"
            )
        return 0

    providers, unavailable = _resolve_providers(args)
    for entry in unavailable:
        print(f"skipped: {entry}", file=sys.stderr)
    if not providers:
        print("error: no provider could be initialized", file=sys.stderr)
        return 2

    from app.services.provider_comparison import compare_text_providers

    started = datetime.now(UTC)
    scores: list[ScenarioScore] = []
    for index, scenario in enumerate(scenarios, start=1):
        request = build_request(scenario, variant=args.prompt_variant)
        if args.max_tokens_scale != 1.0:
            # One ceiling for every workload quietly gave the longest workload the
            # smallest multiple: document extraction ran at 2x while the rest ran at 3x,
            # and it was then the worst-scoring workload in the run.
            request.max_tokens = max(
                1, min(MAX_OUTPUT_TOKENS, int(request.max_tokens * args.max_tokens_scale))
            )
        # These providers share one Google project's capacity, so asking them in parallel
        # makes them compete for the very capacity being measured.
        comparison = await compare_text_providers(request, providers, sequential=True)
        for trial in comparison.trials:
            try:
                score = score_trial(scenario, trial)
            except Exception as error:  # noqa: BLE001
                # A run costs money; a scorer that trips over one odd answer must
                # not discard every scenario already paid for.
                score = ScenarioScore(
                    scenario_id=scenario.scenario_id,
                    workload=scenario.workload,
                    locale=scenario.locale,
                    risk=scenario.risk,
                    provider=trial.provider,
                    model=trial.model,
                    ok=trial.ok,
                    error_code=trial.error_code.value if trial.error_code else None,
                    latency_ms=trial.latency_ms,
                    usage=dict(trial.telemetry.usage) if trial.telemetry else {},
                    retries=trial.telemetry.retries if trial.telemetry else 0,
                    # A scorer that tripped must not leave the attempt looking answered.
                    disposition=_disposition_for(trial),
                    output_text=trial.text,
                    details={"scoring_error": f"{type(error).__name__}: {error}"},
                )
                print(f"    scoring failed for {scenario.scenario_id}/{trial.provider}: {error}")
            scores.append(score)
            marker = "ok " if trial.ok else "ERR"
            print(
                f"[{index}/{len(scenarios)}] {scenario.scenario_id} {trial.provider:12} {marker} "
                f"score={score.score:.2f} safety={score.safety_pass} {trial.latency_ms}ms"
            )
        if args.pause_seconds and index < len(scenarios):
            await asyncio.sleep(args.pause_seconds)

    for provider in providers:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()

    report = EvalRunReport(
        run_id=uuid.uuid4().hex[:12],
        started_at=started,
        finished_at=datetime.now(UTC),
        scenario_set_versions=versions,
        environment=_environment(args, providers),
        summaries=summarize(scores),
        scores=scores,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d_%H%M%S")
    json_path = args.out / f"ai_eval_{stamp}.json"
    md_path = args.out / f"ai_eval_{stamp}.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"\nwrote {json_path}\nwrote {md_path}\n")
    print(render_summary_table(report.summaries))
    return 0 if any(score.ok for score in scores) else 1


def _fmt(value: float | None, *, percent: bool = True) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.0f}%" if percent else f"{value:.4f}"


def _accuracy(summary: WorkloadSummary) -> str:
    """Accuracy on answered calls with its interval, never the point estimate alone."""
    if summary.accuracy_on_answered is None:
        return "—"
    point = f"{summary.accuracy_on_answered * 100:.0f}%"
    if summary.accuracy_ci_low is None or summary.accuracy_ci_high is None:
        return point
    return f"{point} ({summary.accuracy_ci_low * 100:.0f}-{summary.accuracy_ci_high * 100:.0f}%)"


def render_summary_table(summaries: list[WorkloadSummary]) -> str:
    """Availability first, then capability, so the two are never read as one number.

    The counts are printed before the scores because they are the denominator: a model
    that answered 54 of 70 calls and one that answered all 70 are not comparable on
    accuracy alone, and the previous single `score` column hid exactly that.
    """
    header = (
        "| Workload | Provider | Model | n | answered | infra | trunc | unparse | "
        "accuracy on answered (95% CI) | schema | safety | abstain | prec | rec | evid | "
        "median ms | range ms | tokens in/out | est. USD | thresholds |"
    )
    lines = [header, "|" + "---|" * 20]
    for s in summaries:
        thresholds = ", ".join(
            f"{'✅' if ok else '❌'} {name}" for name, ok in s.thresholds.items()
        )
        lines.append(
            f"| {s.workload.value} | {s.provider} | {s.model} | {s.scenarios} | "
            f"{s.answered} | {s.infra_errors} | {s.truncated} | {s.unparseable} | "
            f"{_accuracy(s)} | {_fmt(s.schema_valid_rate)} | {_fmt(s.safety_pass_rate)} | "
            f"{_fmt(s.abstention_accuracy)} | {_fmt(s.precision)} | {_fmt(s.recall)} | "
            f"{_fmt(s.evidence_valid_rate)} | {s.p50_latency_ms} | "
            f"{s.min_latency_ms}-{s.max_latency_ms} | {s.input_tokens}/{s.output_tokens} | "
            f"{_fmt(s.estimated_cost_usd, percent=False)} | {thresholds} |"
        )
    return "\n".join(lines)


def render_markdown(report: EvalRunReport) -> str:
    env = json.dumps(report.environment, indent=2, ensure_ascii=False)
    parts = [
        f"# AI evaluation run `{report.run_id}`",
        "",
        f"Started {report.started_at.isoformat()} · finished {report.finished_at.isoformat()}",
        "",
        "Synthetic scenarios only. Scores are heuristic and offline; clinician adjudication of",
        "high-risk cases is still required before any threshold below counts as met.",
        "",
        "## Summary",
        "",
        render_summary_table(report.summaries),
        "",
        "## Scenario set versions",
        "",
        *[
            f"- `{workload}`: `{version}`"
            for workload, version in report.scenario_set_versions.items()
        ],
        "",
        "## Environment",
        "",
        "```json",
        env,
        "```",
        "",
        "## Per-scenario results",
        "",
        "| Scenario | Locale | Risk | Provider | ok | schema | score | safety | abstained | ms | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in report.scores:
        notes = _score_notes(s)
        parts.append(
            f"| {s.scenario_id} | {s.locale} | {s.risk.value} | {s.provider} | {'yes' if s.ok else s.error_code or 'no'} | "
            f"{'yes' if s.schema_valid else 'no'} | {s.score:.2f} | {s.safety_pass if s.safety_pass is not None else '—'} | "
            f"{s.abstained if s.abstained is not None else '—'} | {s.latency_ms} | {notes} |"
        )
    parts.extend(["", "## Model outputs", ""])
    for s in report.scores:
        if not s.output_text:
            continue
        parts.extend(
            [
                f"### {s.scenario_id} · {s.provider} ({s.model})",
                "",
                "```",
                s.output_text.strip(),
                "```",
                "",
            ]
        )
    return "\n".join(parts)


def _score_notes(score: ScenarioScore) -> str:
    details = score.details
    keys = (
        "floor_rule",
        "predicted_urgency",
        "under_triaged",
        "hallucinated_medications",
        "unsupported_fields_left_empty",
        "evidence_valid_rate",
        "precision",
        "recall",
        "predicted_red_flag",
        "forbidden_hits",
        "detected_language",
        "parse_error",
    )
    notes = []
    for key in keys:
        if key in details and details[key] not in (None, [], False):
            value = details[key]
            notes.append(f"{key}={value:.2f}" if isinstance(value, float) else f"{key}={value}")
    return "; ".join(notes).replace("|", "/")


def main() -> int:
    return asyncio.run(_run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
