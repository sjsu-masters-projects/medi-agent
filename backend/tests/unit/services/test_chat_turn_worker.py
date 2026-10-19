"""The worker's claim, retry semantics, draft coalescing and failure handling (no network)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ExternalServiceError
from app.services import chat_turn_worker as worker
from app.services.chat_turn_worker import DraftCheckpointer, TransientTaskError, run_chat_turn

TURN = str(uuid4())
PATIENT = str(uuid4())
LEASE = str(uuid4())


def claimed(**changes):
    turn = {
        "id": TURN,
        "lease": LEASE,
        "attempt": 1,
        "client_message_id": str(uuid4()),
        "status": "processing",
        "document_context": None,
    }
    user = {
        "id": str(uuid4()),
        "role": "user",
        "content": "Synthetic question",
        "language": "en-US",
        "patient_id": PATIENT,
        "session_id": "chat-test",
    }
    return {
        "accepted": True,
        "patient_id": PATIENT,
        "session_id": "chat-test",
        "next_seq": 2,
        "turn": turn,
        "user_message": user,
        **changes,
    }


class Env:
    """Scripted database: `ops` is chat_turn_worker_operation, `turns` is chat_turn_operation."""

    def __init__(self, monkeypatch, claim):
        self.claim = claim
        self.ops_calls: list[tuple[str, dict]] = []
        self.turn_calls: list[tuple[str, dict]] = []
        self.turn_status = "processing"
        self.fail_on: set[str] = set()
        self.requeue_ok = True
        self.constructed: list[tuple[str, str]] = []
        self.process = AsyncMock(side_effect=self._finish_reply)

        async def ops_call(_self, turn_id, action, payload=None):
            self.ops_calls.append((action, payload or {}))
            if action == "claim":
                if isinstance(self.claim, Exception):
                    raise self.claim
                return self.claim
            if action == "requeue":
                return {"accepted": self.requeue_ok}
            if action == "append_event":
                return {"accepted": True, "next_seq": (payload or {})["seq"] + 1}
            return {"accepted": True}

        monkeypatch.setattr(worker.TurnQueueOps, "call", ops_call)

        class FakeTurns:
            def __init__(self, db, patient_id, session_id):
                env.constructed.append((patient_id, session_id))

            async def call(self, action, payload=None, **kwargs):
                env.turn_calls.append((action, payload or {}))
                if action in env.fail_on:
                    raise ExternalServiceError("Chat", "down")
                if action == "recover":
                    return {"items": [{"id": TURN, "status": env.turn_status}]}
                if action == "complete":
                    env.turn_status = "completed"
                    return {
                        "accepted": True,
                        "message": {
                            "id": str(uuid4()),
                            "role": "assistant",
                            "content": "Synthetic reply",
                            "language": "en-US",
                            "session_id": "chat-test",
                            "created_at": "2026-10-19T10:00:00Z",
                        },
                    }
                if action in {"failed", "interrupted"}:
                    env.turn_status = action
                return {"accepted": True}

        env = self
        monkeypatch.setattr(worker, "ChatTurnService", FakeTurns)
        monkeypatch.setattr(
            worker,
            "ChatService",
            lambda db: MagicMock(
                get_history=AsyncMock(return_value=[]), update_conversation_state=AsyncMock()
            ),
        )
        self.context = AsyncMock(
            return_value={
                "patient_id": PATIENT,
                "session_id": "chat-test",
                "conversation_state": {},
                "incoming": MagicMock(),
                "document_context": None,
            }
        )
        monkeypatch.setattr(worker, "_build_context", self.context)
        monkeypatch.setattr(worker, "_inflight", 0)

    async def _finish_reply(self, emitter, staged, ctx):
        await emitter.send_json(
            {"type": "assistant_start", "intent": "general", "urgency": "routine"}
        )
        await emitter.send_json({"type": "assistant_chunk", "content": "Hello"})
        message = await staged.save_message(
            ctx["patient_id"], {"role": "assistant", "content": "Hello", "language": "en-US"}
        )
        await emitter.send_json({"type": "assistant_complete", "message": message})
        return {}

    def actions(self, which, source=None):
        return [a for a, _ in (source or self.ops_calls) if a == which]

    async def run(self, attempt=1):
        return await run_chat_turn(
            MagicMock(), turn_id=TURN, attempt=attempt, process_message=self.process
        )


@pytest.fixture
def make(monkeypatch):
    return lambda claim=None: Env(monkeypatch, claim if claim is not None else claimed())


@pytest.mark.asyncio
async def test_a_claimed_turn_runs_once_completes_and_prunes(make):
    env = make()
    assert await env.run() == {"outcome": "completed"}
    env.process.assert_awaited_once()
    assert env.actions("complete", env.turn_calls) == ["complete"]
    assert env.actions("prune_events") == ["prune_events"]
    claim_payload = next(p for a, p in env.ops_calls if a == "claim")
    assert claim_payload["attempt"] == 1 and claim_payload["timeout_seconds"] >= 40


@pytest.mark.asyncio
async def test_ownership_comes_from_the_claim_never_from_the_task(make):
    env = make()
    await env.run()
    assert env.constructed == [(PATIENT, "chat-test")]  # ids read by the database claim


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "status:completed",
        "status:failed",
        "status:interrupted",
        "stale_attempt",
        "not_found",
        "queue_expired",
        "attempts_exhausted",
        "document_unavailable",
        "not_worker_turn",
    ],
)
async def test_a_task_for_a_finished_stale_or_unknown_turn_is_a_noop_200(make, reason):
    env = make({"accepted": False, "reason": reason})
    assert await env.run() == {"outcome": "noop", "reason": reason}
    env.process.assert_not_awaited()
    assert not env.turn_calls


@pytest.mark.asyncio
async def test_a_retry_after_actions_started_never_repeats_the_clinical_actions(make):
    """The database refuses the claim of a turn whose actions started (rule 5)."""
    env = make({"accepted": False, "reason": "action_uncertain"})
    assert (await env.run())["reason"] == "action_uncertain"
    env.process.assert_not_awaited()
    assert not env.actions("append_event")


@pytest.mark.asyncio
async def test_a_live_lease_asks_the_queue_to_retry_without_running_anything(make):
    env = make({"accepted": False, "reason": "lease_active"})
    with pytest.raises(TransientTaskError) as caught:
        await env.run()
    assert caught.value.reason == "lease_active"
    env.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unreachable_database_at_claim_is_transient(make):
    env = make(ExternalServiceError("Chat", "down"))
    with pytest.raises(TransientTaskError):
        await env.run()
    env.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_saturated_instance_sheds_before_claiming(make, monkeypatch):
    env = make()
    monkeypatch.setattr(worker, "_inflight", worker.settings.chat_worker_max_concurrency)
    with pytest.raises(TransientTaskError) as caught:
        await env.run()
    assert caught.value.reason == "saturated" and not env.ops_calls


@pytest.mark.asyncio
async def test_exceeding_the_budget_marks_the_turn_interrupted_and_answers_200(make):
    env = make()
    env.process.side_effect = TimeoutError()
    assert await env.run() == {"outcome": "interrupted"}
    assert env.actions("interrupted", env.turn_calls) == ["interrupted"]


@pytest.mark.asyncio
async def test_a_model_error_fails_the_turn_without_a_retry_loop(make):
    env = make()
    env.process.side_effect = RuntimeError("provider detail")
    assert await env.run() == {"outcome": "failed"}
    assert env.actions("failed", env.turn_calls) == ["failed"]
    assert env.process.await_count == 1


@pytest.mark.asyncio
async def test_a_failure_that_cannot_be_recorded_is_transient(make):
    env = make()
    env.process.side_effect = RuntimeError("provider detail")
    env.fail_on = {"failed"}
    with pytest.raises(TransientTaskError) as caught:
        await env.run()
    assert caught.value.reason == "failure_not_recorded"


@pytest.mark.asyncio
async def test_a_lost_completion_confirmation_is_reconciled_from_the_database(make):
    env = make()

    async def complete_then_lose(emitter, staged, ctx):
        await env._finish_reply(emitter, staged, ctx)
        return {}

    env.process.side_effect = complete_then_lose
    original = worker.execute_turn

    async def commit_then_time_out(**kwargs):
        env.turn_status = "completed"  # the save committed
        kwargs["outcome"]["status"] = "failed"
        kwargs["outcome"]["mark_failed"] = True
        return {}

    worker.execute_turn = commit_then_time_out
    try:
        assert await env.run() == {"outcome": "completed"}
    finally:
        worker.execute_turn = original


@pytest.mark.asyncio
async def test_an_unreadable_context_hands_the_turn_back_for_a_clean_retry(make):
    env = make()
    env.context.side_effect = ExternalServiceError("Chat", "down")
    with pytest.raises(TransientTaskError) as caught:
        await env.run()
    assert caught.value.reason == "context_unavailable"
    assert env.actions("requeue") == ["requeue"]
    env.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_returns_the_turn_to_the_queue_instead_of_failing_it(make):
    env = make()
    started = asyncio.Event()

    async def never(emitter, staged, ctx):
        started.set()
        await asyncio.sleep(60)

    env.process.side_effect = never
    task = asyncio.create_task(env.run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert env.actions("requeue") == ["requeue"]
    assert not env.actions("interrupted", env.turn_calls)


@pytest.mark.asyncio
async def test_shutdown_after_actions_started_marks_interrupted(make):
    env = make()
    env.requeue_ok = False  # the database refuses once actions started
    started = asyncio.Event()

    async def never(emitter, staged, ctx):
        started.set()
        await asyncio.sleep(60)

    env.process.side_effect = never
    task = asyncio.create_task(env.run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert env.actions("interrupted", env.turn_calls) == ["interrupted"]


@pytest.mark.asyncio
async def test_notices_and_drafts_are_appended_in_seq_order_for_the_claimed_lease(
    make, monkeypatch
):
    env = make()
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.02)

    async def slow(emitter, staged, ctx):
        await emitter.send_json(
            {"type": "assistant_start", "intent": "symptom", "urgency": "urgent"}
        )
        await emitter.send_json({"type": "assistant_chunk", "content": "Part one. "})
        await emitter.send_json({"type": "appointment_proposal", "proposal_id": "p"})
        await asyncio.sleep(0.4)
        message = await staged.save_message(
            ctx["patient_id"], {"role": "assistant", "content": "Part one.", "language": "en-US"}
        )
        await emitter.send_json({"type": "assistant_complete", "message": message})
        return {}

    env.process.side_effect = slow
    await env.run()
    appends = [p for a, p in env.ops_calls if a == "append_event"]
    assert appends and all(p["lease"] == LEASE for p in appends)
    assert [p["seq"] for p in appends] == list(range(2, 2 + len(appends)))
    kinds = [p["type"] for p in appends]
    assert "notice" in kinds and "draft" in kinds
    draft = next(p for p in appends if p["type"] == "draft")["payload"]
    assert draft == {"content": "Part one. ", "intent": "symptom", "urgency": "urgent"}


# -- draft coalescing -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draft_checkpoints_are_coalesced_to_the_interval(monkeypatch):
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.2)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.02)
    appended = []
    ops = MagicMock()

    async def call(turn_id, action, payload):
        appended.append(payload)
        return {"accepted": True, "next_seq": payload["seq"] + 1}

    ops.call = call
    sink = DraftCheckpointer(ops, TURN, LEASE, 2)
    sink.start()
    sink.publish({"type": "assistant_start", "intent": "general", "urgency": "routine"})
    for _ in range(150):  # 150 chunks over ~0.75 s
        sink.publish({"type": "assistant_chunk", "content": "word "})
        await asyncio.sleep(0.005)
    await sink.stop()
    assert 2 <= len(appended) <= 6  # not 150
    assert appended[-1]["payload"]["content"].count("word") > 100  # whole draft, not a delta
    assert [p["seq"] for p in appended] == list(range(2, 2 + len(appended)))


@pytest.mark.asyncio
async def test_draft_failures_never_fail_the_turn_and_stop_after_three(monkeypatch):
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.01)
    ops = MagicMock()
    ops.call = AsyncMock(side_effect=ExternalServiceError("Chat", "down"))
    sink = DraftCheckpointer(ops, TURN, LEASE, 2)
    sink.start()
    for _ in range(40):
        sink.publish({"type": "assistant_chunk", "content": "x"})
        await asyncio.sleep(0.01)
    await sink.stop()
    assert ops.call.await_count == worker.MAX_DRAFT_FAILURES


@pytest.mark.asyncio
async def test_a_lost_lease_stops_drafting(monkeypatch):
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.01)
    ops = MagicMock()
    ops.call = AsyncMock(return_value={"accepted": False, "reason": "lease_mismatch"})
    sink = DraftCheckpointer(ops, TURN, LEASE, 2)
    sink.start()
    for _ in range(20):
        sink.publish({"type": "assistant_chunk", "content": "x"})
        await asyncio.sleep(0.01)
    await sink.stop()
    assert ops.call.await_count == 1 and sink.stopped


@pytest.mark.asyncio
async def test_a_seq_gap_resyncs_and_the_draft_is_retried(monkeypatch):
    monkeypatch.setattr(worker, "DRAFT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker, "DRAFT_TICK_SECONDS", 0.01)
    replies = iter(
        [
            {"accepted": False, "reason": "seq_gap", "next_seq": 9},
            {"accepted": True, "next_seq": 10},
        ]
    )
    seen = []

    async def call(turn_id, action, payload):
        seen.append(payload["seq"])
        return next(replies)

    ops = MagicMock()
    ops.call = call
    sink = DraftCheckpointer(ops, TURN, LEASE, 2)
    sink.start()
    sink.publish({"type": "assistant_chunk", "content": "x"})
    await asyncio.sleep(0.3)
    await sink.stop()
    assert seen == [2, 9]


def test_only_known_extra_events_become_notices_and_ephemeral_ones_are_dropped():
    sink = DraftCheckpointer(MagicMock(), TURN, LEASE, 2)
    for kind in (
        "chat_turn",
        "user_message_saved",
        "error",
        "assistant_complete",
        "a2a_task_status",
    ):
        sink.publish({"type": kind})
    assert [n["type"] for n in sink.notices] == ["a2a_task_status"]
