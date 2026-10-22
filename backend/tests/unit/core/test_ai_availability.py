"""Bounded availability counters: classification, bounds, flush and the admin-only read."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.config import settings
from app.core import ai_availability as av
from app.core.ai_availability import AvailabilityRecorder, classify_outcome, summarize
from app.main import app
from app.models.auth import CurrentUser


@pytest.mark.parametrize(
    ("status_code", "cause", "expected"),
    [
        (200, "none", "success"),
        (429, "retry_429", "rate_limited"),
        (429, "retry_exhausted", "rate_limited"),
        (503, "provider_error", "server_error"),
        (500, "failed_after_text", "server_error"),
        (504, "deadline", "timeout"),
        (None, "cancelled_or_deadline", "timeout"),
        (None, "cancelled", "cancelled"),
        (503, "circuit_open", "circuit_open"),
        (503, "admission_timeout", "shed"),
        (404, "provider_error", "client_error"),
        (None, "provider_error", "other"),
    ],
)
def test_attempts_map_to_a_closed_outcome_set(status_code, cause, expected) -> None:
    assert classify_outcome(status_code, cause) == expected


def _record(rec: AvailabilityRecorder, outcome: str = "success", ms: int = 100, **kw: Any) -> None:
    rec.record(
        workload=kw.get("workload", "reply"),
        model=kw.get("model", "gemini-3.8-flash"),
        outcome=outcome,
        fallback=kw.get("fallback", False),
        latency_ms=ms,
    )


def test_keys_are_bounded_and_values_are_sanitised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_availability_enabled", False)
    rec = AvailabilityRecorder()
    for i in range(av.MAX_KEYS + 25):
        _record(rec, model=f"m{i}")
    assert len(rec._counts) == av.MAX_KEYS and rec.dropped == 25
    other = AvailabilityRecorder()
    _record(other, workload="Reply; DROP TABLE x", model="a b\nc")
    assert list(other._counts) == [("replydroptablex", "abc", "success", False)]


@pytest.mark.asyncio
async def test_a_flush_sends_aggregates_only_and_a_failure_keeps_the_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_availability_enabled", False)
    sent: list[Any] = []
    state = {"fail": True}

    class _Client:
        def rpc(self, name: str, params: dict[str, Any]) -> Any:
            def execute() -> Any:
                if state["fail"]:
                    raise RuntimeError("db down")
                sent.append((name, params))
                return MagicMock(data={"accepted": True})

            return MagicMock(execute=execute)

    monkeypatch.setattr("app.clients.supabase.get_admin_client", lambda: _Client())
    rec = AvailabilityRecorder()
    _record(rec, ms=300)
    _record(rec, ms=300)
    _record(rec, "rate_limited", ms=900, fallback=True)
    with pytest.raises(RuntimeError):
        await rec.flush()
    assert sum(v[0] for v in rec._counts.values()) == 3  # kept for the next flush
    state["fail"] = False
    await rec.flush()
    name, params = sent[0]
    assert name == "record_ai_availability"
    rows = {(r["outcome"], r["fallback"]): r for r in params["p_rows"]}
    assert rows[("success", False)]["attempts"] == 2
    assert rows[("success", False)]["bins"][1] == 2  # 250-500 ms
    assert set(rows[("success", False)]) == {
        "workload",
        "model",
        "outcome",
        "fallback",
        "attempts",
        "latency_sum_ms",
        "bins",
    }
    assert not rec._counts


@pytest.mark.asyncio
async def test_recording_never_blocks_and_flushes_in_the_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_availability_enabled", True)
    monkeypatch.setattr(settings, "ai_availability_flush_seconds", 5.0)
    flushed = asyncio.Event()

    rec = AvailabilityRecorder()
    rec._last_flush -= 60

    async def fake_flush() -> bool:
        flushed.set()
        return True

    monkeypatch.setattr(rec, "flush", fake_flush)
    _record(rec)
    assert not flushed.is_set()  # scheduled, not awaited by the caller
    await asyncio.wait_for(flushed.wait(), 1)
    await asyncio.sleep(0)
    assert rec._task is None


def test_the_summary_reports_rates_fallbacks_and_percentiles() -> None:
    bins = [0, 8, 1, 1, 0, 0, 0, 0, 0, 0]  # 10 attempts: 8 in 250-500 ms
    rows = [
        {
            "workload": "reply",
            "model": "m",
            "outcome": "success",
            "fallback": False,
            "attempts": 8,
            "latency_sum_ms": 3000,
            "latency_bins": bins,
        },
        {
            "workload": "reply",
            "model": "m",
            "outcome": "rate_limited",
            "fallback": False,
            "attempts": 1,
            "latency_sum_ms": 100,
            "latency_bins": [0] * 10,
        },
        {
            "workload": "reply",
            "model": "m",
            "outcome": "timeout",
            "fallback": True,
            "attempts": 1,
            "latency_sum_ms": 9000,
            "latency_bins": [0] * 10,
        },
    ]
    item = summarize(rows)[0]
    assert item["attempts"] == 10 and item["fallback_attempts"] == 1
    assert item["outcomes"]["rate_limited"] == 1 and item["outcomes"]["timeout"] == 1
    assert item["success_rate"] == 0.8
    assert item["latency_ms"]["p50"] == 500 and item["latency_ms"]["p99"] == 2000


class _Service:
    def __init__(self, admin: bool) -> None:
        self.admin = admin

    async def require_admin(self, user: CurrentUser) -> None:
        if not self.admin:
            from app.core.exceptions import AuthorizationError

            raise AuthorizationError("Only clinic admins can read AI availability")

    async def window(self, hours: int) -> dict[str, Any]:
        return {"window_hours": hours, "items": []}


@pytest.mark.parametrize(("admin", "code"), [(True, 200), (False, 403)])
def test_only_clinic_admins_can_read(client, monkeypatch, admin: bool, code: int) -> None:
    from app.routers import ops

    monkeypatch.setattr(ops, "AiAvailabilityService", lambda db: _Service(admin))
    app.dependency_overrides[ops._clinician_dep] = lambda: CurrentUser(
        id=uuid4(), email="a@b.c", role="clinician"
    )
    try:
        response = client.get("/api/v1/ops/ai-availability?hours=6")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == code
    if admin:
        assert response.json()["window_hours"] == 6


def test_patients_and_anonymous_callers_are_refused(client) -> None:
    assert client.get("/api/v1/ops/ai-availability").status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }
