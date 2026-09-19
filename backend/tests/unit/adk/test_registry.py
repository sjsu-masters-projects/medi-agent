"""The routing table's invariants.

These are not tests of a data structure. Each one pins a property that, if it broke,
would fail silently in production: a workload with no deterministic answer, a fallback
that retries the same saturated model, or a kill switch whose name no longer resolves.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.adk.registry import (
    FLASH,
    GPT_OSS,
    ModelSpec,
    Transport,
    Workload,
    WorkloadRoute,
    route_for,
    routes,
)
from app.config import settings


def test_every_workload_has_a_route() -> None:
    for workload in Workload:
        assert route_for(workload).workload is workload


def test_every_workload_has_a_deterministic_path() -> None:
    """A disabled, slow, or failing model must still produce an actionable answer."""
    for workload in Workload:
        assert route_for(workload).deterministic.strip()


def test_no_route_falls_back_to_its_own_primary() -> None:
    """Retrying one model against one capacity pool is a delay, not a fallback."""
    for workload in Workload:
        route = route_for(workload)
        if route.fallback is not None:
            assert route.fallback.key != route.primary.key


def test_every_kill_switch_names_a_real_setting() -> None:
    """A misspelled switch reads as False through getattr and disables a workload."""
    for workload in Workload:
        route = route_for(workload)
        assert hasattr(settings, route.enabled_setting)
        assert isinstance(route.is_enabled(), bool)


def test_an_unregistered_workload_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="No route is registered"):
        route_for("not-a-workload")  # type: ignore[arg-type]


def test_the_table_cannot_be_rerouted_at_runtime() -> None:
    """Routing is configuration, not per-request state."""
    with pytest.raises(TypeError):
        routes[Workload.TRIAGE] = route_for(Workload.REPLY)  # type: ignore[index]


def test_triage_leads_with_the_faster_measured_model() -> None:
    """2.2 s median against 6.2 s, at equal accuracy, in the one path a patient waits on."""
    assert route_for(Workload.TRIAGE).primary is GPT_OSS
    assert route_for(Workload.TRIAGE).budget_seconds == 8.0


def test_recall_sensitive_workloads_do_not_fall_back_to_the_lower_recall_model() -> None:
    """Flash reached 94% recall on reconciliation where gpt-oss reached 71%.

    A missed medication discrepancy is the harm this workload exists to prevent, so
    substituting the weaker model on failure would trade the whole point of it for
    availability.
    """
    discrepancy = route_for(Workload.DISCREPANCY)
    assert discrepancy.primary is FLASH
    assert discrepancy.fallback is None


def test_extraction_runs_without_a_user_facing_budget() -> None:
    """It runs in an async job, so nothing is waiting and nothing should be cut short."""
    extraction = route_for(Workload.EXTRACTION)
    assert extraction.budget_seconds is None
    # A second model guessing at an unreadable document produces confident wrong
    # candidates rather than an honest review flag.
    assert extraction.fallback is None
    assert "needs_evidence_review" in extraction.deterministic


def test_schema_conformance_is_recorded_as_a_measured_property() -> None:
    """3 violations in 10 trials against 0 in 10; callers routed to gpt-oss must validate."""
    assert GPT_OSS.honours_response_schema is False
    assert FLASH.honours_response_schema is True


def test_transport_is_independent_of_the_model_id() -> None:
    """The defect just removed from the Gemini client was inferring one from the other."""
    assert FLASH.transport is Transport.VERTEX_GENAI
    assert GPT_OSS.transport is Transport.VERTEX_MAAS_OPENAI


def test_the_maas_model_id_keeps_its_publisher_prefix() -> None:
    """`openai/` is the publisher namespace Vertex's OpenAI surface requires.

    It is spelled identically to a LiteLLM provider prefix, so it reads as redundant next
    to a transport already named `VERTEX_MAAS_OPENAI` and invites removal. Every row of
    the 2026-09-17 report that produced our routing decision used the prefixed id.
    """
    assert GPT_OSS.model_id == "openai/gpt-oss-120b-maas"


def test_the_genai_model_id_carries_no_publisher_prefix() -> None:
    """The same model is named differently on the two surfaces.

    Gemini is `gemini-3.8-flash` through the Gen AI SDK and `google/gemini-3.8-flash`
    through the OpenAI-compatible surface, so an id copied between transports breaks.
    """
    assert FLASH.model_id == "gemini-3.8-flash"


def test_interactive_workloads_all_carry_a_budget() -> None:
    """The measured tail is 95.2 s. Anything a person waits on needs a limit."""
    for workload in (
        Workload.TRIAGE,
        Workload.REPLY,
        Workload.DISCREPANCY,
        Workload.ADR_EXTRACTION,
        Workload.EXPLANATION,
    ):
        budget = route_for(workload).budget_seconds
        assert budget is not None and budget > 0


def test_every_workload_declares_a_token_budget_and_thinking_level() -> None:
    for workload in Workload:
        route = route_for(workload)
        assert route.max_output_tokens > 0
        assert route.thinking_level in {"LOW", "MEDIUM", "HIGH"}


def test_minimal_thinking_is_never_requested() -> None:
    """3.8 Flash rejects MINIMAL with HTTP 400, at call time rather than at startup."""
    for workload in Workload:
        assert route_for(workload).thinking_level != "MINIMAL"


def test_the_explanation_budget_clears_its_measured_answer_length() -> None:
    """Measured: the bilingual explanation answer ran 950-1166 tokens and died at 1024."""
    assert route_for(Workload.EXPLANATION).max_output_tokens >= 2048


def test_an_unsupported_thinking_level_is_rejected_at_import() -> None:
    from app.adk import registry

    broken = WorkloadRoute(
        workload=Workload.TRIAGE,
        primary=GPT_OSS,
        fallback=FLASH,
        budget_seconds=8.0,
        deterministic="rules",
        enabled_setting="triage_ai_enabled",
        thinking_level="MINIMAL",
    )
    original = dict(registry._ROUTES)
    registry._ROUTES[Workload.TRIAGE] = broken
    try:
        with pytest.raises(ValueError, match="thinking level"):
            registry._validate()
    finally:
        registry._ROUTES.clear()
        registry._ROUTES.update(original)


def test_a_non_positive_token_budget_is_rejected() -> None:
    from app.adk import registry

    broken = WorkloadRoute(
        workload=Workload.REPLY,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30.0,
        deterministic="localized reply template",
        enabled_setting="reply_ai_enabled",
        max_output_tokens=0,
    )
    original = dict(registry._ROUTES)
    registry._ROUTES[Workload.REPLY] = broken
    try:
        with pytest.raises(ValueError, match="non-positive token budget"):
            registry._validate()
    finally:
        registry._ROUTES.clear()
        registry._ROUTES.update(original)


def test_a_route_that_breaks_an_invariant_is_rejected() -> None:
    """The validator is what makes the invariants above load-bearing rather than hopeful."""
    from app.adk import registry

    broken = WorkloadRoute(
        workload=Workload.TRIAGE,
        primary=GPT_OSS,
        fallback=GPT_OSS,
        budget_seconds=8.0,
        deterministic="rules",
        enabled_setting="triage_ai_enabled",
    )
    original = dict(registry._ROUTES)
    registry._ROUTES[Workload.TRIAGE] = broken
    try:
        with pytest.raises(ValueError, match="falls back to its own primary"):
            registry._validate()
    finally:
        registry._ROUTES.clear()
        registry._ROUTES.update(original)


def test_a_kill_switch_typo_is_rejected() -> None:
    from app.adk import registry

    broken = WorkloadRoute(
        workload=Workload.REPLY,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30.0,
        deterministic="localized reply template",
        enabled_setting="repply_ai_enabled",
    )
    original = dict(registry._ROUTES)
    registry._ROUTES[Workload.REPLY] = broken
    try:
        with pytest.raises(ValueError, match="which is not a setting"):
            registry._validate()
    finally:
        registry._ROUTES.clear()
        registry._ROUTES.update(original)


def test_a_workload_without_a_deterministic_path_is_rejected() -> None:
    from app.adk import registry

    broken = WorkloadRoute(
        workload=Workload.EXPLANATION,
        primary=FLASH,
        fallback=GPT_OSS,
        budget_seconds=30.0,
        deterministic="   ",
        enabled_setting="explanation_ai_enabled",
    )
    original = dict(registry._ROUTES)
    registry._ROUTES[Workload.EXPLANATION] = broken
    try:
        with pytest.raises(ValueError, match="no deterministic path"):
            registry._validate()
    finally:
        registry._ROUTES.clear()
        registry._ROUTES.update(original)


def test_model_specs_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        FLASH.model_id = "something-else"  # type: ignore[misc]


def test_both_finalists_are_reachable_through_a_declared_transport() -> None:
    for spec in (FLASH, GPT_OSS):
        assert isinstance(spec, ModelSpec)
        assert spec.transport in set(Transport)
        assert spec.model_id
