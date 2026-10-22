"""Cloud Tasks dispatch, the outbox sweep and idempotent send for worker-run Nora turns."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from google.api_core import exceptions as gax
from google.cloud import tasks_v2

from app.config import settings
from app.core.exceptions import ExternalServiceError
from app.services import chat_turn_queue
from app.services.chat_turn_queue import TurnDispatcher, TurnQueueOps, submit_turn, task_id


@pytest.fixture(autouse=True)
def queue_settings(monkeypatch):
    monkeypatch.setattr(settings, "cloud_tasks_project", "synthetic-project")
    monkeypatch.setattr(settings, "cloud_tasks_location", "us-central1")
    monkeypatch.setattr(settings, "cloud_tasks_queue", "nora-turns")
    monkeypatch.setattr(settings, "chat_worker_url", "https://worker.example.test")
    monkeypatch.setattr(
        settings, "chat_worker_invoker_sa", "invoker@synthetic.iam.gserviceaccount.com"
    )
    monkeypatch.setattr(settings, "chat_worker_oidc_audience", "")
    monkeypatch.setattr(chat_turn_queue, "DISPATCH_RETRY_BASE_SECONDS", 0.0)


def test_task_id_is_deterministic_per_turn_and_attempt():
    turn = str(uuid4())
    assert task_id(turn, 1) == task_id(turn, 1) == f"chat-turn-{turn}-a1"
    assert task_id(turn, 2) != task_id(turn, 1)
    with pytest.raises(ValueError):
        task_id("not-a-uuid", 1)


def test_task_is_a_valid_authenticated_http_task_that_carries_no_clinical_data():
    turn = str(uuid4())
    task = TurnDispatcher(MagicMock()).build_task(turn, 2)
    request = tasks_v2.CreateTaskRequest(parent="projects/p/locations/l/queues/q", task=task)
    http = request.task.http_request
    assert http.url == "https://worker.example.test/internal/tasks/chat-turn"
    assert http.oidc_token.service_account_email == "invoker@synthetic.iam.gserviceaccount.com"
    assert http.oidc_token.audience == "https://worker.example.test"  # defaults to the URL
    assert json.loads(http.body) == {"turn_id": turn, "attempt": 2}
    assert request.task.name.endswith(f"/tasks/chat-turn-{turn}-a2")
    # Nesting (rule 11): the dispatch deadline exceeds the database lease, and Cloud Run's 300 s.
    assert 70 < request.task.dispatch_deadline.total_seconds() < 300


def test_an_explicit_audience_wins(monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_oidc_audience", "https://audience.example.test")
    task = TurnDispatcher(MagicMock()).build_task(str(uuid4()), 1)
    assert task["http_request"]["oidc_token"]["audience"] == "https://audience.example.test"


@pytest.mark.parametrize(
    "field",
    ["cloud_tasks_queue", "chat_worker_url", "chat_worker_invoker_sa", "cloud_tasks_location"],
)
def test_unconfigured_queue_is_detected(monkeypatch, field):
    assert TurnDispatcher.configured()
    monkeypatch.setattr(settings, field, "")
    assert not TurnDispatcher.configured()


def test_project_falls_back_to_the_google_project(monkeypatch):
    monkeypatch.setattr(settings, "cloud_tasks_project", "")
    monkeypatch.setattr(settings, "google_project_id", "fallback-project")
    assert TurnDispatcher.project() == "fallback-project"


def _client(monkeypatch, create=None):
    fake = MagicMock()
    fake.queue_path.return_value = "projects/p/locations/l/queues/q"
    fake.create_task = create or MagicMock()
    monkeypatch.setattr(chat_turn_queue, "_client", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_dispatch_creates_the_task_once_and_marks_the_outbox(monkeypatch):
    fake = _client(monkeypatch)
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(return_value={"accepted": True})
    turn = str(uuid4())
    assert await dispatcher.dispatch(turn, 1)
    fake.create_task.assert_called_once()
    sent = fake.create_task.call_args.kwargs["request"]["task"]
    assert sent["name"].endswith(task_id(turn, 1))
    dispatcher.ops.call.assert_awaited_once_with(turn, "dispatched", {"attempt": 1})


@pytest.mark.asyncio
async def test_a_task_that_already_exists_counts_as_dispatched(monkeypatch):
    _client(monkeypatch, MagicMock(side_effect=gax.AlreadyExists("duplicate")))
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(return_value={"accepted": True})
    assert await dispatcher.dispatch(str(uuid4()), 1)
    dispatcher.ops.call.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_enqueue_never_raises_and_is_left_for_the_sweep(monkeypatch):
    _client(monkeypatch, MagicMock(side_effect=gax.ServiceUnavailable("queue down")))
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock()
    assert not await dispatcher.dispatch(str(uuid4()), 1)
    dispatcher.ops.call.assert_not_awaited()  # dispatched_at stays NULL: still in the outbox


@pytest.mark.asyncio
async def test_a_failed_mark_after_a_good_enqueue_is_not_an_error(monkeypatch):
    _client(monkeypatch)
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(side_effect=ExternalServiceError("Chat", "down"))
    assert await dispatcher.dispatch(str(uuid4()), 1)


@pytest.mark.asyncio
async def test_sweep_requeues_only_what_the_outbox_lists(monkeypatch):
    fake = _client(monkeypatch)
    first, second = str(uuid4()), str(uuid4())
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(
        side_effect=lambda turn, action, payload=None: {
            "undispatched": {"items": [{"id": first, "attempt": 1}, {"id": second, "attempt": 2}]},
        }.get(action, {"accepted": True})
    )
    assert await dispatcher.sweep() == {"examined": 2, "dispatched": 2, "failed": 0}
    names = [c.kwargs["request"]["task"]["name"] for c in fake.create_task.call_args_list]
    assert [n.rsplit("/", 1)[-1] for n in names] == [task_id(first, 1), task_id(second, 2)]


@pytest.mark.asyncio
async def test_sweep_counts_failures_and_stops_when_unconfigured(monkeypatch):
    _client(monkeypatch, MagicMock(side_effect=gax.DeadlineExceeded("slow")))
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(return_value={"items": [{"id": str(uuid4()), "attempt": 1}]})
    assert (await dispatcher.sweep())["failed"] == 1
    monkeypatch.setattr(settings, "chat_worker_url", "")
    dispatcher.ops.call.reset_mock()
    assert await dispatcher.sweep() == {"examined": 0, "dispatched": 0, "failed": 0}
    dispatcher.ops.call.assert_not_awaited()


# -- send: one transaction, then the enqueue ----------------------------------------------------


def _begin_result(execute, status="queued", attempt=1):
    return {
        "execute": execute,
        "turn": {
            "id": "11111111-1111-4111-8111-111111111111",
            "status": status,
            "attempt": attempt,
        },
        "user_message": {"id": str(uuid4()), "content": "Synthetic question"},
    }


@pytest.mark.asyncio
async def test_send_enqueues_once_per_idempotency_key(monkeypatch):
    order: list[str] = []
    results = iter([_begin_result(True), _begin_result(False)])

    async def begin(self, request, timeout, *, queued=False):
        order.append(f"begin:queued={queued}")
        return next(results)

    async def dispatch(self, turn_id, attempt):
        order.append(f"dispatch:{attempt}")
        return True

    monkeypatch.setattr("app.services.chat_turn_service.ChatTurnService.begin", begin)
    monkeypatch.setattr(TurnDispatcher, "dispatch", dispatch)
    monkeypatch.setattr("app.services.chat_service.ChatService.set_conversation_title", AsyncMock())
    request = {"client_message_id": str(uuid4()), "content": "x", "document_id": None}
    first = await submit_turn(
        MagicMock(), patient_id="p", session_id="s", request=request, language="en-US"
    )
    again = await submit_turn(
        MagicMock(), patient_id="p", session_id="s", request=request, language="en-US"
    )
    assert first["dispatched"] and not again["dispatched"]
    # The turn is committed (begin) before anything is enqueued; a repeat enqueues nothing.
    assert order == ["begin:queued=True", "dispatch:1", "begin:queued=True"]


@pytest.mark.asyncio
async def test_a_failed_enqueue_does_not_fail_the_send_and_leaves_the_turn_queued(monkeypatch):
    async def begin(self, request, timeout, *, queued=False):
        return _begin_result(True)

    monkeypatch.setattr("app.services.chat_turn_service.ChatTurnService.begin", begin)
    monkeypatch.setattr(TurnDispatcher, "dispatch", AsyncMock(return_value=False))
    monkeypatch.setattr("app.services.chat_service.ChatService.set_conversation_title", AsyncMock())
    result = await submit_turn(
        MagicMock(),
        patient_id="p",
        session_id="s",
        request={"client_message_id": str(uuid4()), "content": "x", "document_id": None},
        language="en-US",
    )
    assert result["turn"]["status"] == "queued" and result["dispatched"] is False


@pytest.mark.asyncio
async def test_queue_ops_surface_a_database_failure_as_an_external_error():
    from postgrest.exceptions import APIError

    db = MagicMock()
    db.rpc.return_value.execute.side_effect = APIError({"message": "boom", "code": "57014"})
    with pytest.raises(ExternalServiceError):
        await TurnQueueOps(db).call(str(uuid4()), "claim", {})


@pytest.mark.asyncio
async def test_the_saved_message_is_announced_after_the_commit_and_before_the_enqueue(monkeypatch):
    order: list[str] = []

    async def begin(self, request, timeout, *, queued=False):
        order.append("begin")
        return _begin_result(True)

    async def dispatch(self, turn_id, attempt):
        order.append("dispatch")
        return True

    async def saved(result):
        order.append("saved")

    monkeypatch.setattr("app.services.chat_turn_service.ChatTurnService.begin", begin)
    monkeypatch.setattr(TurnDispatcher, "dispatch", dispatch)
    monkeypatch.setattr("app.services.chat_service.ChatService.set_conversation_title", AsyncMock())
    await submit_turn(
        MagicMock(),
        patient_id="p",
        session_id="s",
        request={"client_message_id": str(uuid4()), "content": "x", "document_id": None},
        language="en-US",
        on_saved=saved,
    )
    assert order == ["begin", "saved", "dispatch"]


@pytest.mark.asyncio
async def test_a_failing_saved_notice_never_blocks_the_enqueue(monkeypatch):
    async def begin(self, request, timeout, *, queued=False):
        return _begin_result(True)

    async def broken(result):
        raise RuntimeError("socket closed")

    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.chat_turn_service.ChatTurnService.begin", begin)
    monkeypatch.setattr(TurnDispatcher, "dispatch", dispatch)
    monkeypatch.setattr("app.services.chat_service.ChatService.set_conversation_title", AsyncMock())
    result = await submit_turn(
        MagicMock(),
        patient_id="p",
        session_id="s",
        request={"client_message_id": str(uuid4()), "content": "x", "document_id": None},
        language="en-US",
        on_saved=broken,
    )
    dispatch.assert_awaited_once()
    assert result["dispatched"] is True


# -- latency: one warm client per process, immediate bounded retry -------------------------------


def test_the_client_is_created_once_per_process_and_reused(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr(chat_turn_queue, "_client_singleton", None)
    monkeypatch.setattr(chat_turn_queue, "_fresh_credentials", lambda: "creds")
    monkeypatch.setattr(tasks_v2, "CloudTasksClient", FakeClient)
    first = chat_turn_queue._client()
    assert chat_turn_queue._client() is first
    assert created == [{"credentials": "creds"}]


def test_credentials_that_cannot_be_prefetched_fall_back_to_the_client_lookup(monkeypatch):
    import google.auth

    def broken(**kwargs):
        raise RuntimeError("no metadata server")

    monkeypatch.setattr(google.auth, "default", broken)
    assert chat_turn_queue._fresh_credentials() is None


@pytest.mark.asyncio
async def test_warm_up_runs_on_the_dispatch_pool_and_never_raises(monkeypatch):
    warmed = MagicMock(return_value=5)
    monkeypatch.setattr(chat_turn_queue, "warm_client", warmed)
    await chat_turn_queue.warm_dispatcher()
    warmed.assert_called_once()
    monkeypatch.setattr(chat_turn_queue, "warm_client", MagicMock(side_effect=RuntimeError("x")))
    await chat_turn_queue.warm_dispatcher()  # logged, not raised
    monkeypatch.setattr(settings, "chat_worker_url", "")
    warmed.reset_mock()
    monkeypatch.setattr(chat_turn_queue, "warm_client", warmed)
    await chat_turn_queue.warm_dispatcher()  # unconfigured: nothing to warm
    warmed.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_enqueue_is_retried_at_once_then_succeeds(monkeypatch):
    _client(
        monkeypatch,
        MagicMock(side_effect=[gax.ServiceUnavailable("blip"), gax.DeadlineExceeded("slow"), None]),
    )
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock(return_value={"accepted": True})
    assert await dispatcher.dispatch_with_retry(str(uuid4()), 1)


@pytest.mark.asyncio
async def test_retry_is_bounded_and_leaves_the_turn_to_the_sweep(monkeypatch):
    fake = _client(monkeypatch, MagicMock(side_effect=gax.ServiceUnavailable("down")))
    dispatcher = TurnDispatcher(MagicMock())
    dispatcher.ops.call = AsyncMock()
    assert not await dispatcher.dispatch_with_retry(str(uuid4()), 1)
    assert fake.create_task.call_count == chat_turn_queue.DISPATCH_RETRY_ATTEMPTS
    dispatcher.ops.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_stops_when_the_time_budget_is_spent(monkeypatch):
    monkeypatch.setattr(chat_turn_queue, "DISPATCH_RETRY_BASE_SECONDS", 1.0)
    monkeypatch.setattr(chat_turn_queue, "DISPATCH_RETRY_BUDGET_SECONDS", 0.1)
    fake = _client(monkeypatch, MagicMock(side_effect=gax.ServiceUnavailable("down")))
    dispatcher = TurnDispatcher(MagicMock())
    assert not await dispatcher.dispatch_with_retry(str(uuid4()), 1)
    assert fake.create_task.call_count == 1  # no pause fits the budget


@pytest.mark.asyncio
async def test_a_hung_enqueue_is_cut_off_by_the_timeout(monkeypatch):
    import time as _time

    monkeypatch.setattr(chat_turn_queue, "ENQUEUE_TIMEOUT_SECONDS", -1.9)  # wait_for gets 0.1 s
    _client(monkeypatch, MagicMock(side_effect=lambda **kw: _time.sleep(0.5)))
    dispatcher = TurnDispatcher(MagicMock())
    started = _time.monotonic()
    assert not await dispatcher.dispatch(str(uuid4()), 1)
    assert _time.monotonic() - started < 0.4


@pytest.mark.asyncio
async def test_the_title_label_is_saved_after_the_enqueue(monkeypatch):
    order: list[str] = []

    async def begin(self, request, timeout, *, queued=False):
        return _begin_result(True)

    async def dispatch(self, turn_id, attempt):
        order.append("dispatch")
        return True

    async def title(*args, **kwargs):
        order.append("title")

    monkeypatch.setattr("app.services.chat_turn_service.ChatTurnService.begin", begin)
    monkeypatch.setattr(TurnDispatcher, "dispatch", dispatch)
    monkeypatch.setattr("app.services.chat_service.ChatService.set_conversation_title", title)
    await submit_turn(
        MagicMock(),
        patient_id="p",
        session_id="s",
        request={"client_message_id": str(uuid4()), "content": "x", "document_id": None},
        language="en-US",
    )
    assert order == ["dispatch", "title"]
