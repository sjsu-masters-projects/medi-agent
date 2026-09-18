"""Which model runs each workload, how long it may take, and what runs when it does not.

This table replaces `TASK_MODEL_MAP`, which named one model per task and could express
nothing else: no fallback, no time limit, and no answer for the case where the model is
slow, disabled, or wrong. Each of those gaps has cost us something measurable.

Every figure here comes from the 2026-09-17 paired re-run over 70 scenarios
(`.agent/specs/eval-harness-protocol-2026-09.md` §12, §14), not from judgement. The two
finalists could not be separated on clinical accuracy at that sample size, so the primary
for each workload is chosen on the properties that *did* separate them — latency, cost,
recall on reconciliation, and whether the model honours an output schema.

Three invariants are enforced at import time, because each one has a failure mode that is
silent rather than loud:

- **Every workload has a deterministic path.** A model that is disabled, over budget, or
  unreachable must still produce an answer a patient can act on, in their own language.
- **A fallback is a different model.** Retrying the same model against the same capacity
  pool is a delay dressed up as resilience.
- **Every kill switch names a setting that exists.** A misspelled switch reads as `False`
  through `getattr`, which silently disables a workload nobody meant to disable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.config import settings


class Workload(StrEnum):
    """A unit of work routed to a model, named for what it produces."""

    TRIAGE = "triage"
    REPLY = "reply"
    EXTRACTION = "extraction"
    DISCREPANCY = "discrepancy"
    ADR_EXTRACTION = "adr_extraction"
    EXPLANATION = "explanation"


class Transport(StrEnum):
    """How a model is reached. The model id alone does not determine this."""

    # Gemini on Vertex through the Google Gen AI SDK against the global endpoint.
    VERTEX_GENAI = "vertex_genai"
    # Open-weight managed endpoints, which Vertex serves behind an OpenAI-compatible
    # `/chat/completions` surface authenticated with an Application Default Credentials
    # bearer token rather than an API key.
    VERTEX_MAAS_OPENAI = "vertex_maas_openai"


@dataclass(frozen=True)
class ModelSpec:
    """One addressable model.

    `honours_response_schema` is a measured deployment property, not a claim from a model
    card. gpt-oss-120b violated an accepted JSON schema in 3 of 10 trials on Vertex where
    Gemini 3.8 Flash violated it in 0 of 10 (protocol §11). A caller routed to a model
    with this set `False` must validate the result and be able to recover from a
    violation; it must not assume the shape it asked for is the shape it received.
    """

    key: str
    model_id: str
    transport: Transport
    honours_response_schema: bool


GPT_OSS: Final = ModelSpec(
    key="gpt_oss",
    # The `openai/` prefix is part of the model id Vertex's OpenAI-compatible surface
    # expects, not decoration. It is recorded in every row of the 2026-09-17 report, and
    # it is a publisher namespace that happens to be spelled the same way a LiteLLM
    # provider prefix is. Those are different things, and reading it as the latter — and
    # "cleaning it up" because the transport is already known to be OpenAI-shaped — is
    # how this call starts returning 404 for a model that is deployed and working.
    model_id="openai/gpt-oss-120b-maas",
    transport=Transport.VERTEX_MAAS_OPENAI,
    honours_response_schema=False,
)

FLASH: Final = ModelSpec(
    key="flash",
    # Unprefixed, because this reaches Gemini through the Gen AI SDK rather than the
    # OpenAI-compatible surface, which wants `google/gemini-3.8-flash` instead. The id
    # therefore cannot be read without knowing the transport beside it.
    # This remains deployment configuration rather than a source edit: promotion to a
    # replacement model is a reviewed Cloud Run setting change, not a code change that
    # can leave the legacy router and the agent runtime on different Flash versions.
    model_id=settings.gemini_flash_model,
    transport=Transport.VERTEX_GENAI,
    honours_response_schema=True,
)


THINKING_LEVELS: Final = frozenset({"LOW", "MEDIUM", "HIGH"})
"""Thinking ceilings this product may request.

`MINIMAL` is deliberately absent: Gemini 3.8 Flash rejects it with HTTP 400, and a config
that assumes otherwise fails at call time rather than at startup. `thinking_budget` is not
used at all — it is deprecated on Gemini 3.x, where dynamic thinking is always on and the
level is a ceiling the model may spend less than, or ignore entirely (protocol §17).
"""


@dataclass(frozen=True)
class WorkloadRoute:
    """The complete routing decision for one workload.

    `budget_seconds` is a wall-clock limit on the model call, enforced by the caller. It
    is not a timeout tuned for the model's comfort: it is the point at which waiting
    longer is worse for the person than a deterministic answer. The measured tail is why
    it exists at all — Flash took 95.2 s on its slowest triage call and 88.2 s on its
    slowest explanation, and neither is survivable in front of a patient.

    `deterministic` names what runs when the model is disabled, over budget, or failing.
    It is a name rather than a callable so this module stays free of agent imports and
    can be read as the routing table it is.
    """

    workload: Workload
    primary: ModelSpec
    fallback: ModelSpec | None
    budget_seconds: float | None
    deterministic: str
    enabled_setting: str
    # Sized from measured answer lengths, not guessed. Thought tokens are billed against
    # this same ceiling, and the share they take is prompt-dependent — 0% to 96% across
    # our runs — so these are floors that make truncation rare, not limits that make it
    # impossible. Detecting truncation is what has to be reliable.
    max_output_tokens: int = 2048
    thinking_level: str = "LOW"

    def is_enabled(self) -> bool:
        """Whether the model path is live for this workload right now."""
        return bool(getattr(settings, self.enabled_setting))


_ROUTES: Final[dict[Workload, WorkloadRoute]] = {
    # gpt-oss answered triage at a 2.2 s median against Flash's 6.2 s and scored 100% on
    # the same scenarios, so it leads here. Triage output is a small enum, which is the
    # one shape its schema violations are least likely to damage — and the deterministic
    # emergency floor runs before the model either way, so no escalation depends on it.
    Workload.TRIAGE: WorkloadRoute(
        workload=Workload.TRIAGE,
        primary=GPT_OSS,
        fallback=FLASH,
        budget_seconds=8.0,
        # There used to be a keyword cascade here, guessing an intent from substrings when
        # the model was unavailable and answering the patient in that intent's voice. It
        # was deleted: a guess and an answer were indistinguishable in the reply, which is
        # not a trade worth making for clinical content. What remains is the floor, which
        # decides emergencies without a model, and an honest outage message for everything
        # else.
        deterministic="emergency safety floor, then the localized service-unavailable message",
        enabled_setting="triage_ai_enabled",
        # Measured: answers run 115-136 tokens with 201-439 spent thinking, so 1024 is
        # comfortable and keeps the fastest workload fast.
        max_output_tokens=1024,
        thinking_level="LOW",
    ),
    # Patient-facing prose, where Flash's fluency and its perfect schema record matter
    # more than gpt-oss's speed advantage. The budget is the total; the first chunk is
    # held to a tighter limit by the streaming caller, because that is the number the
    # patient actually experiences.
    Workload.REPLY: WorkloadRoute(
        workload=Workload.REPLY,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30.0,
        deterministic="localized reply template",
        enabled_setting="reply_ai_enabled",
        max_output_tokens=2048,
        thinking_level="LOW",
    ),
    # Runs inside an asynchronous ingestion job, so there is no one waiting on it and no
    # budget to enforce. There is deliberately no fallback: a second model guessing at a
    # document nobody could read produces candidates that look confident and are not.
    Workload.EXTRACTION: WorkloadRoute(
        workload=Workload.EXTRACTION,
        primary=FLASH,
        fallback=None,
        budget_seconds=None,
        deterministic="mark needs_evidence_review and write no candidates",
        enabled_setting="extraction_ai_enabled",
        # Structured output over whole documents, and nothing is waiting on it, so this
        # gets the most room of any workload.
        max_output_tokens=8192,
        thinking_level="MEDIUM",
    ),
    # Flash reached 94% recall on reconciliation where gpt-oss reached 71%. A missed
    # medication discrepancy is the failure this workload exists to prevent, so recall
    # decides it and gpt-oss is not an acceptable fallback for correctness here.
    Workload.DISCREPANCY: WorkloadRoute(
        workload=Workload.DISCREPANCY,
        primary=FLASH,
        fallback=None,
        budget_seconds=20.0,
        deterministic="deterministic discrepancy engine alone",
        enabled_setting="discrepancy_ai_enabled",
        # Reconciliation is the recall-critical workload, so it is given room to reason.
        max_output_tokens=4096,
        thinking_level="MEDIUM",
    ),
    Workload.ADR_EXTRACTION: WorkloadRoute(
        workload=Workload.ADR_EXTRACTION,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=15.0,
        # There used to be a rule-based extractor here, inferring the symptom from
        # substrings and inventing a severity when the model was unavailable — "worst
        # headache pain today" became severity 8, and severe chest pain in Spanish became
        # an unflagged severity 4. Those values were written to `symptom_reports` and read
        # later by a clinician as the patient's own account. A guess that persists is
        # worse than one that does not, so nothing is recorded now and the patient is told.
        deterministic="no symptom report is written and the patient is told so",
        enabled_setting="adr_extraction_ai_enabled",
        max_output_tokens=2048,
        thinking_level="LOW",
    ),
    Workload.EXPLANATION: WorkloadRoute(
        workload=Workload.EXPLANATION,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30.0,
        deterministic="localized explanation template",
        enabled_setting="explanation_ai_enabled",
        # Measured: the bilingual explanation answer runs 950-1166 tokens and truncated
        # outright at 1024, so this is the workload that proved 1024 is too small.
        max_output_tokens=2048,
        thinking_level="LOW",
    ),
}


def _validate() -> None:
    """Check the invariants once, at import, so a bad table cannot reach a request."""
    missing = [workload for workload in Workload if workload not in _ROUTES]
    if missing:
        raise ValueError(f"Workloads have no route: {[w.value for w in missing]}")

    for workload, route in _ROUTES.items():
        if route.workload is not workload:
            raise ValueError(f"Route for {workload.value} is keyed as {route.workload.value}")
        if not route.deterministic.strip():
            raise ValueError(f"Workload {workload.value} has no deterministic path")
        if route.fallback is not None and route.fallback.key == route.primary.key:
            raise ValueError(
                f"Workload {workload.value} falls back to its own primary, which is a delay "
                "rather than a fallback"
            )
        if route.budget_seconds is not None and route.budget_seconds <= 0:
            raise ValueError(f"Workload {workload.value} has a non-positive budget")
        if route.max_output_tokens <= 0:
            raise ValueError(f"Workload {workload.value} has a non-positive token budget")
        if route.thinking_level not in THINKING_LEVELS:
            # `MINIMAL` reaches here from a config that looks reasonable and fails as an
            # HTTP 400 on the first real request, so it is rejected at import instead.
            raise ValueError(
                f"Workload {workload.value} requests thinking level "
                f"'{route.thinking_level}', which is not one of {sorted(THINKING_LEVELS)}"
            )
        if not hasattr(settings, route.enabled_setting):
            # `getattr` on a misspelled switch would read as disabled and silently turn
            # the workload off, so the name is checked rather than trusted.
            raise ValueError(
                f"Workload {workload.value} names kill switch "
                f"'{route.enabled_setting}', which is not a setting"
            )


_validate()

routes: Final = MappingProxyType(_ROUTES)
"""The routing table, read-only so a caller cannot reroute a workload at runtime."""


def route_for(workload: Workload) -> WorkloadRoute:
    """Return the route for a workload.

    Raises rather than defaulting: a workload with no entry is a programming error, and
    guessing a model for it would put unreviewed output in front of a patient.
    """
    try:
        return _ROUTES[workload]
    except KeyError:
        raise ValueError(f"No route is registered for workload {workload!r}") from None
