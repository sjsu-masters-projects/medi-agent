"""Ask MedGemma, Flash, and Pro the same question and print what each one said.

`EVA-001` selects a default and fallback provider from measured results rather than
assumption. This is the tool that produces those measurements: it sends one prompt to
several providers and reports latency, success, and output side by side.

Production routing cannot do this. `TASK_MODEL_MAP` binds each task to exactly one
model, so the serving path can never show you what the alternatives would have said.

    export GOOGLE_PROJECT_ID=... VERTEX_AI_MEDGEMMA_ENDPOINT=...
    python backend/scripts/compare_providers.py --prompt "Summarize this medication list."
    python backend/scripts/compare_providers.py --prompt-file scenario.txt --models medgemma,flash
    python backend/scripts/compare_providers.py --prompt "..." --json > run.json

Needs real provider credentials and network access; it calls the live endpoints. Exits
non-zero only when every provider failed — a partial result is still a result, since an
unavailable provider is one of the things being compared.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.generation import ProviderComparison
    from app.services.generation_providers import TextProvider

# `app` is not installed into the virtualenv, so resolve the source root directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DEFAULT_MODELS = ("medgemma", "flash", "pro")
# "nim" is comparable too, but stays out of the default set: it needs
# NVIDIA_NIM_API_KEY, and a skipped provider on every run would be noise.
AVAILABLE_MODELS = (*DEFAULT_MODELS, "nim")

# Importing `app` constructs Settings, which requires the full service environment.
# Doing that at module scope would make `--help` and argument errors depend on
# credentials the caller does not need in order to read usage, so every app import
# below happens inside the function that needs it.


def _resolve_providers(names: list[str]) -> tuple[list[TextProvider], list[str]]:
    """Build a provider per requested model, reporting the ones that could not start.

    A model that fails to initialize is reported and skipped rather than aborting the
    run: comparing the two that did start is more useful than comparing none.
    """
    from app.clients.model_router import ModelRouter

    router = ModelRouter()
    providers: list[TextProvider] = []
    unavailable: list[str] = []
    for name in names:
        try:
            providers.append(router.get_text_provider_for_model(name))
        except Exception as error:  # noqa: BLE001 - report and continue
            unavailable.append(f"{name} ({error})")
    return providers, unavailable


def _render(comparison: ProviderComparison) -> str:
    rows = [
        ("PROVIDER", "MODEL", "OK", "LATENCY", "CHARS", "DETAIL"),
    ]
    for trial in comparison.trials:
        rows.append(
            (
                trial.provider,
                trial.model,
                "yes" if trial.ok else "no",
                f"{trial.latency_ms}ms",
                str(len(trial.text or "")),
                "" if trial.ok else str(trial.error_code or "failed"),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(v.ljust(widths[i]) for i, v in enumerate(row)) for row in rows)


async def _run(args: argparse.Namespace) -> int:
    prompt = Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt
    if not prompt or not prompt.strip():
        print("error: prompt is empty", file=sys.stderr)
        return 2

    from app.models.generation import GenerationRequest
    from app.services.provider_comparison import compare_text_providers

    names = [name.strip() for name in args.models.split(",") if name.strip()]
    providers, unavailable = _resolve_providers(names)
    for entry in unavailable:
        print(f"skipped: {entry}", file=sys.stderr)
    if not providers:
        print("error: no requested provider could be initialized", file=sys.stderr)
        return 2

    comparison = await compare_text_providers(
        GenerationRequest(
            prompt=prompt,
            task=args.task,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        ),
        providers,
    )

    if args.json:
        print(comparison.model_dump_json(indent=2))
    else:
        print(_render(comparison))
        if args.show_output:
            for trial in comparison.succeeded:
                print(f"\n--- {trial.provider} ({trial.model}) ---\n{trial.text}")

    # Every provider failing is a real finding, and the exit code should say so.
    return 0 if comparison.succeeded else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Prompt text to send to every provider")
    source.add_argument("--prompt-file", help="File containing the prompt")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=(
            f"Comma-separated model names from {','.join(AVAILABLE_MODELS)} "
            f"(default: {','.join(DEFAULT_MODELS)})"
        ),
    )
    parser.add_argument("--task", default="comparison", help="Task label recorded in telemetry")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help=(
            "Output token budget per provider. Raise it for reasoning models: a trace "
            "can consume the whole budget and leave the answer empty (default: 1024)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the full result as JSON")
    parser.add_argument(
        "--show-output", action="store_true", help="Print each provider's text after the table"
    )
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
