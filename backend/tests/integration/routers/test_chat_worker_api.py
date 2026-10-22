# ruff: noqa: F811  (pytest fixtures are imported by name)
"""Worker-run Nora turns: HTTP send/read, the task endpoint, the sweep, and viewing the event log."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketState

from app.config import settings
from app.core.exceptions import ExternalServiceError, ValidationError
from app.core.security import get_current_user
from app.core.task_auth import require_cloud_tasks_oidc
from app.db.connection import get_db
from app.main import app, create_app
from app.models.auth import CurrentUser
from app.models.chat import ChatMessageCreate
from app.models.enums import ChatRole, Language
from app.routers import chat, chat_turns, internal_tasks
from app.services.chat_turn_events import (
    TurnEventReader,
    TurnWatchSet,
    event_to_messages,
    watch_turn,
)
from app.services.chat_turn_queue import TurnDispatcher
from app.services.chat_turn_worker import TransientTaskError
from tests.integration.routers.test_chat_document_focus import (  # noqa: F401
    _FakeChatStore,
    _opening_events,
    _types,
    connect,
    patient_id,
)
from tests.integration.routers.test_chat_socket_recovery import turns  # noqa: F401

PATIENT = UUID("00000000-0000-4000-8000-0000000000aa")
TURN = "11111111-1111-4111-8111-111111111111"
MESSAGE = str(uuid4())


def _fake_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def worker_flag(monkeypatch):
    monkeypatch.setattr(settings, "chat_turns_via_worker", True)
    monkeypatch.setattr(settings, "cloud_tasks_project", "synthetic-project")
    monkeypatch.setattr(settings, "chat_worker_url", "https://worker.example.test")
    monkeypatch.setattr(
        settings, "chat_worker_invoker_sa", "invoker@synthetic.iam.gserviceaccount.com"
    )


@pytest.fixture
def patient():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=PATIENT, email="p@test.test", role="patient"
    )
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.clear()


def queued(execute=True, **changes):
    record = {
        "id": TURN,
        "client_message_id": str(uuid4()),
        "status": "queued",
        "attempt": 1,
        "via_worker": True,
        "deadline_at": "2026-10-19T10:02:00Z",
        "lease": "secret",
    }
    user = {
        "id": MESSAGE,
        "patient_id": str(PATIENT),
        "session_id": "chat-test",
        "role": "user",
        "language": "en-US",
        "content": "Synthetic question",
        "created_at": "2026-10-19T10:00:00Z",
    }
    return {
        "execute": execute,
        "dispatched": execute,
        "turn": record,
        "user_message": user,
        **changes,
    }


# -- POST /chat/turns --------------------------------------------------------------------------


def body(**changes):
    return {
        "client_message_id": str(uuid4()),
        "content": "Synthetic question",
        "session_id": "chat-test",
        **changes,
    }


def test_http_send_is_unavailable_until_the_flag_is_on(patient):
    assert TestClient(app).post("/api/v1/chat/turns", json=body()).status_code == 404
    assert TestClient(app).get(f"/api/v1/chat/turns/{TURN}/events").status_code == 404


def test_http_send_queues_the_turn_and_returns_it_without_running_the_model(
    patient, worker_flag, monkeypatch
):
    submit = AsyncMock(return_value=queued())
    monkeypatch.setattr(chat_turns, "submit_turn", submit)
    process = AsyncMock()
    monkeypatch.setattr(chat, "_process_chat_message", process)
    response = TestClient(app).post("/api/v1/chat/turns", json=body())
    assert response.status_code == 202
    payload = response.json()
    assert payload["turn"]["status"] == "queued" and payload["dispatched"] is True
    assert "lease" not in str(payload) and "request_hash" not in str(payload)
    assert submit.await_args.kwargs["patient_id"] == str(PATIENT)  # from the token, not the body
    process.assert_not_awaited()


def test_http_send_replays_a_finished_turn_without_queueing_again(
    patient, worker_flag, monkeypatch
):
    saved = {
        "id": str(uuid4()),
        "patient_id": str(PATIENT),
        "session_id": "chat-test",
        "role": "assistant",
        "language": "en-US",
        "content": "Synthetic reply",
        "created_at": "2026-10-19T10:00:05Z",
    }
    done = queued(execute=False, assistant_message=saved)
    done["turn"]["status"] = "completed"
    monkeypatch.setattr(chat_turns, "submit_turn", AsyncMock(return_value=done))
    response = TestClient(app).post("/api/v1/chat/turns", json=body())
    assert response.status_code == 200
    assert response.json()["assistant_message"]["content"] == "Synthetic reply"
    assert response.json()["execute"] is False


def test_http_send_maps_a_busy_conversation_to_409(patient, worker_flag, monkeypatch):
    monkeypatch.setattr(
        chat_turns, "submit_turn", AsyncMock(side_effect=ValidationError("CHAT_TURN_BUSY"))
    )
    response = TestClient(app).post("/api/v1/chat/turns", json=body())
    assert response.status_code == 409 and response.json()["error"]["code"] == "CHAT_TURN_BUSY"


def test_http_send_fails_closed_when_the_queue_is_not_configured(patient, worker_flag, monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_url", "")
    submit = AsyncMock()
    monkeypatch.setattr(chat_turns, "submit_turn", submit)
    response = TestClient(app).post("/api/v1/chat/turns", json=body())
    assert response.status_code >= 500
    submit.assert_not_awaited()  # nothing saved that could never run


def test_only_a_patient_may_send(worker_flag, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=PATIENT, email="c@test.test", role="clinician"
    )
    app.dependency_overrides[get_db] = _fake_db
    try:
        assert TestClient(app).post("/api/v1/chat/turns", json=body()).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_a_message_over_the_limit_is_rejected_at_the_boundary(patient, worker_flag):
    assert (
        TestClient(app).post("/api/v1/chat/turns", json=body(content="x" * 8001)).status_code == 422
    )
    assert TestClient(app).post("/api/v1/chat/turns", json=body(content="")).status_code == 422


def test_events_are_read_for_the_owner_only(patient, worker_flag, monkeypatch):
    async def turn(self, patient_id, turn_id):
        return (
            None
            if patient_id != str(PATIENT)
            else {
                "id": TURN,
                "status": "processing",
                "attempt": 1,
                "client_message_id": str(uuid4()),
            }
        )

    monkeypatch.setattr(TurnEventReader, "turn", turn)
    monkeypatch.setattr(
        TurnEventReader,
        "events_after",
        AsyncMock(return_value=[{"seq": 2, "type": "draft", "payload": {"content": "Hel"}}]),
    )
    response = TestClient(app).get(f"/api/v1/chat/turns/{TURN}/events?after_seq=1")
    assert response.status_code == 200 and response.json()["next_seq"] == 2
    monkeypatch.setattr(TurnEventReader, "turn", AsyncMock(return_value=None))
    assert TestClient(app).get(f"/api/v1/chat/turns/{TURN}/events").status_code == 404


# -- the cron sweep ---------------------------------------------------------------------------------


def test_the_sweep_endpoint_needs_the_cron_token_and_reports_counts(monkeypatch):
    monkeypatch.setattr(settings, "cron_auth_token", "cron-token")
    app.dependency_overrides[get_db] = _fake_db
    sweep = AsyncMock(return_value={"examined": 2, "dispatched": 2, "failed": 0})
    monkeypatch.setattr(TurnDispatcher, "sweep", sweep)
    try:
        client = TestClient(app)
        assert client.post("/api/v1/cron/chat-turns/dispatch").status_code == 403
        ok = client.post("/api/v1/cron/chat-turns/dispatch", headers={"X-Cron-Auth": "cron-token"})
        assert ok.status_code == 200 and ok.json() == {"examined": 2, "dispatched": 2, "failed": 0}
    finally:
        app.dependency_overrides.clear()


# -- the worker app ---------------------------------------------------------------------------------


@pytest.fixture
def worker_app(monkeypatch):
    monkeypatch.setattr(settings, "worker_mode", True)
    application = create_app()
    application.dependency_overrides[get_db] = _fake_db
    return application


def task(**changes):
    return {"turn_id": TURN, "attempt": 1, **changes}


def test_the_task_route_exists_only_on_the_worker_and_the_worker_serves_nothing_else(
    worker_app, monkeypatch
):
    assert TestClient(app).post("/internal/tasks/chat-turn", json=task()).status_code == 404
    client = TestClient(worker_app)
    assert client.get("/health").json()["service"] == "mediagent-chat-worker"
    for path in (
        "/api/v1/chat/history/" + str(PATIENT),
        "/api/v1/cron/chat-turns/dispatch",
        "/docs",
    ):
        assert client.get(path).status_code in {404, 405}


def test_the_task_route_refuses_unauthenticated_calls(worker_app, monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_url", "https://worker.example.test")
    monkeypatch.setattr(
        settings, "chat_worker_invoker_sa", "invoker@synthetic.iam.gserviceaccount.com"
    )
    run = AsyncMock()
    monkeypatch.setattr(internal_tasks, "run_chat_turn", run)
    client = TestClient(worker_app)
    assert client.post("/internal/tasks/chat-turn", json=task()).status_code == 401
    assert (
        client.post(
            "/internal/tasks/chat-turn", json=task(), headers={"Authorization": "Bearer forged"}
        ).status_code
        == 401
    )
    run.assert_not_awaited()


@pytest.fixture
def authenticated(worker_app):
    worker_app.dependency_overrides[require_cloud_tasks_oidc] = lambda: {"email": "x"}
    return TestClient(worker_app)


def test_a_finished_task_answers_200_so_the_queue_stops(authenticated, monkeypatch):
    run = AsyncMock(return_value={"outcome": "noop", "reason": "status:completed"})
    monkeypatch.setattr(internal_tasks, "run_chat_turn", run)
    response = authenticated.post(
        "/internal/tasks/chat-turn",
        json=task(),
        headers={
            "X-CloudTasks-TaskName": f"chat-turn-{TURN}-a1",
            "X-CloudTasks-TaskRetryCount": "2",
        },
    )
    assert response.status_code == 200 and response.json()["reason"] == "status:completed"
    assert run.await_args.kwargs["turn_id"] == TURN and run.await_args.kwargs["attempt"] == 1


def test_a_transient_error_answers_503_so_the_queue_retries(authenticated, monkeypatch):
    monkeypatch.setattr(
        internal_tasks,
        "run_chat_turn",
        AsyncMock(side_effect=TransientTaskError("claim_unavailable")),
    )
    response = authenticated.post("/internal/tasks/chat-turn", json=task())
    assert response.status_code == 503 and response.headers["Retry-After"] == "5"
    assert response.json() == {"outcome": "retry", "reason": "claim_unavailable"}


@pytest.mark.parametrize(
    "bad", [{}, {"turn_id": "nope", "attempt": 1}, task(attempt=0), task(attempt=9)]
)
def test_an_unusable_task_body_is_dropped_with_200_not_retried_forever(
    authenticated, monkeypatch, bad
):
    run = AsyncMock()
    monkeypatch.setattr(internal_tasks, "run_chat_turn", run)
    response = authenticated.post("/internal/tasks/chat-turn", json=bad)
    assert response.status_code == 200 and response.json()["reason"] == "invalid_task"
    run.assert_not_awaited()


def test_the_task_runs_the_shared_pipeline(authenticated, monkeypatch):
    run = AsyncMock(return_value={"outcome": "completed"})
    monkeypatch.setattr(internal_tasks, "run_chat_turn", run)
    authenticated.post("/internal/tasks/chat-turn", json=task())
    assert run.await_args.kwargs["process_message"] is chat._process_chat_message


# -- the socket: queue, never run -------------------------------------------------------------------


def socket_and_context():
    websocket = MagicMock()
    websocket.application_state = WebSocketState.CONNECTED
    websocket.send_json = AsyncMock()
    service = MagicMock()
    service.db = MagicMock()
    context = {
        "patient_id": PATIENT,
        "session_id": "chat-test",
        "conversation_state": {"turn_count": 1},
        "incoming": ChatMessageCreate(
            content="Synthetic question", role=ChatRole.USER, language=Language.EN
        ),
    }
    return websocket, service, context


@pytest.mark.asyncio
async def test_with_the_flag_on_a_socket_send_queues_and_the_api_never_calls_the_model(
    worker_flag, monkeypatch
):
    websocket, service, context = socket_and_context()
    process = AsyncMock()
    monkeypatch.setattr(chat, "_process_chat_message", process)
    runner = MagicMock()
    monkeypatch.setattr(chat, "turn_runner", runner)
    submit = AsyncMock(return_value=queued())
    monkeypatch.setattr(chat, "submit_turn", submit)
    watchers = MagicMock()
    state = await chat._queue_durable_message(
        websocket, service, context, {"client_message_id": "c"}, watchers
    )
    assert state == {"turn_count": 1}
    process.assert_not_awaited()
    runner.start.assert_not_called()
    submit.assert_awaited_once()
    sent = [call.args[0]["type"] for call in websocket.send_json.call_args_list]
    assert sent == ["chat_turn", "user_message_saved"]
    watchers.start.assert_called_once()  # a viewer of the event log, not an owner


@pytest.mark.asyncio
async def test_the_user_message_reaches_the_socket_before_the_task_is_enqueued(
    worker_flag, monkeypatch
):
    websocket, service, context = socket_and_context()
    order: list[str] = []
    websocket.send_json = AsyncMock(side_effect=lambda p: order.append(p["type"]))

    async def submit(*args, on_saved=None, **kwargs):
        result = queued()
        await on_saved(result)
        order.append("enqueue")
        return result

    monkeypatch.setattr(chat, "submit_turn", submit)
    await chat._queue_durable_message(
        websocket, service, context, {"client_message_id": "c"}, MagicMock()
    )
    # Saved state once, ahead of the slow enqueue, never duplicated afterwards.
    assert order == ["chat_turn", "user_message_saved", "enqueue"]


@pytest.mark.asyncio
async def test_a_repeated_socket_send_does_not_enqueue_again_but_watches_the_running_turn(
    worker_flag, monkeypatch
):
    websocket, service, context = socket_and_context()
    repeat = queued(execute=False)
    repeat["turn"]["status"] = "processing"
    monkeypatch.setattr(chat, "submit_turn", AsyncMock(return_value=repeat))
    watchers = MagicMock()
    await chat._queue_durable_message(
        websocket, service, context, {"client_message_id": "c"}, watchers
    )
    watchers.start.assert_called_once()


@pytest.mark.asyncio
async def test_a_busy_conversation_is_reported_like_the_in_process_path(worker_flag, monkeypatch):
    websocket, service, context = socket_and_context()
    monkeypatch.setattr(
        chat, "submit_turn", AsyncMock(side_effect=ValidationError("CHAT_TURN_BUSY"))
    )
    monkeypatch.setattr(
        chat, "ChatTurnService", lambda *_: MagicMock(call=AsyncMock(return_value={"items": []}))
    )
    await chat._queue_durable_message(
        websocket, service, context, {"client_message_id": "c"}, MagicMock()
    )
    codes = [c.args[0].get("code") for c in websocket.send_json.call_args_list]
    assert "CHAT_TURN_BUSY" in codes


@pytest.mark.asyncio
async def test_an_unconfigured_queue_saves_nothing_and_says_so(worker_flag, monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_invoker_sa", "")
    websocket, service, context = socket_and_context()
    submit = AsyncMock()
    monkeypatch.setattr(chat, "submit_turn", submit)
    monkeypatch.setattr(
        chat, "ChatTurnService", lambda *_: MagicMock(call=AsyncMock(return_value={"items": []}))
    )
    await chat._queue_durable_message(
        websocket, service, context, {"client_message_id": "c"}, MagicMock()
    )
    submit.assert_not_awaited()
    assert websocket.send_json.call_args_list[0].args[0]["type"] == "error"


@pytest.mark.asyncio
async def test_a_reloaded_tab_watches_only_running_worker_turns():
    started = []
    watchers = MagicMock()
    watchers.start = lambda turn_id, factory: started.append(turn_id)
    items = [
        {"id": "a", "status": "processing", "via_worker": True, "user_message": {}},
        {"id": "b", "status": "queued", "via_worker": True},
        {"id": "c", "status": "processing", "via_worker": False},
        {"id": "d", "status": "completed", "via_worker": True},
    ]
    chat._watch_inflight_worker_turns(
        watchers, MagicMock(), MagicMock(db=MagicMock()), "p", "s", items
    )
    assert started == ["a", "b"]


# -- viewing the event log --------------------------------------------------------------------------


class FakeReader:
    def __init__(self, batches, status_rows=None):
        self.batches, self.calls, self.status_rows = list(batches), [], status_rows or []

    async def events_after(self, turn_id, after_seq):
        self.calls.append(after_seq)
        return self.batches.pop(0) if self.batches else []

    async def message(self, patient_id, message_id):
        return {
            "id": message_id,
            "patient_id": patient_id,
            "session_id": "chat-test",
            "role": "assistant",
            "language": "en-US",
            "content": "Synthetic reply",
            "created_at": "2026-10-19T10:00:05Z",
        }

    async def turn(self, patient_id, turn_id):
        return self.status_rows.pop(0) if self.status_rows else None


def ev(seq, kind, **payload):
    return {"seq": seq, "type": kind, "payload": payload}


async def collect(reader, **kwargs):
    seen = []

    async def send(event):
        seen.append(event)
        return True

    await watch_turn(
        reader,
        patient_id=str(PATIENT),
        turn={"id": TURN, "status": "queued", "attempt": 1},
        user_message=None,
        send=send,
        **kwargs,
    )
    return seen


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    from app.services import chat_turn_events

    monkeypatch.setattr(chat_turn_events, "POLL_ACTIVE_SECONDS", 0.001)
    monkeypatch.setattr(chat_turn_events, "POLL_MAX_IDLE_SECONDS", 0.002)


@pytest.mark.asyncio
async def test_a_viewer_shows_the_draft_then_the_final_reply_in_order():
    reader = FakeReader(
        [
            [ev(1, "started", attempt=1)],
            [ev(2, "draft", content="Hel", intent="symptom", urgency="routine")],
            [ev(3, "draft", content="Hello there")],
            [ev(4, "completed", message_id=MESSAGE)],
        ]
    )
    seen = await collect(reader)
    kinds = [e["type"] for e in seen]
    assert kinds == [
        "chat_turn",
        "assistant_start",
        "assistant_chunk",
        "assistant_chunk",
        "assistant_complete",
        "chat_turn",
    ]
    assert [e["content"] for e in seen if e["type"] == "assistant_chunk"] == ["Hel", "lo there"]
    assert seen[-1]["turn"]["status"] == "completed"
    assert reader.calls == [0, 1, 2, 3]  # resumes by seq


@pytest.mark.asyncio
async def test_a_late_viewer_gets_the_draft_so_far_as_one_chunk():
    reader = FakeReader([[ev(2, "started"), ev(40, "draft", content="Whole draft so far")]])
    seen = await collect(reader, max_seconds=0.05)
    chunks = [e["content"] for e in seen if e["type"] == "assistant_chunk"]
    assert chunks == ["Whole draft so far"]


@pytest.mark.asyncio
async def test_a_failed_turn_ends_the_viewer_and_triggers_the_recovery_hook():
    reader = FakeReader([[ev(1, "started")], [ev(2, "failed", failure_code="processing_failed")]])
    hook = AsyncMock()
    seen = await collect(reader, on_terminal=hook)
    assert seen[-1]["turn"]["status"] == "failed"
    hook.assert_awaited_once_with("failed")


@pytest.mark.asyncio
async def test_notices_pass_through_and_a_draft_that_does_not_extend_the_text_is_skipped():
    state: dict = {}
    base = {"id": TURN, "attempt": 1}
    out = event_to_messages(ev(2, "draft", content="Hello"), state, base)
    assert [m["type"] for m in out] == ["assistant_start", "assistant_chunk"]
    assert event_to_messages(ev(3, "draft", content="Goodbye"), state, base) == []
    notice = event_to_messages(
        ev(4, "notice", type="appointment_proposal", proposal_id="p"), state, base
    )
    assert notice == [{"type": "appointment_proposal", "proposal_id": "p"}]
    assert event_to_messages(ev(5, "notice", other=1), state, base) == []


@pytest.mark.asyncio
async def test_a_terminal_row_without_a_terminal_event_still_ends_the_viewer():
    reader = FakeReader([], status_rows=[{"status": "completed", "assistant_message_id": MESSAGE}])
    seen = await collect(reader, max_seconds=5)
    assert [e["type"] for e in seen] == ["assistant_complete", "chat_turn"]


@pytest.mark.asyncio
async def test_a_viewer_whose_socket_is_gone_stops_without_touching_the_turn():
    reader = FakeReader([[ev(1, "started")], [ev(2, "draft", content="x")]])

    async def dead(_event):
        return False

    await watch_turn(
        reader,
        patient_id=str(PATIENT),
        turn={"id": TURN, "status": "queued", "attempt": 1},
        user_message=None,
        send=dead,
    )
    assert reader.calls == [0]


@pytest.mark.asyncio
async def test_a_busy_pool_skips_a_tick_instead_of_ending_the_viewer():
    calls = {"n": 0}

    class Flaky(FakeReader):
        async def events_after(self, turn_id, after_seq):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ExternalServiceError("Chat", "busy")
            return [ev(1, "completed", message_id=MESSAGE)]

    seen = await collect(Flaky([]))
    assert seen[-1]["turn"]["status"] == "completed" and calls["n"] == 2


@pytest.mark.asyncio
async def test_watch_set_runs_one_viewer_per_turn_cancels_on_close_and_sheds_when_full(monkeypatch):
    watchers = TurnWatchSet()
    gate = asyncio.Event()

    async def hold():
        await gate.wait()

    assert watchers.start("t1", hold) and not watchers.start("t1", hold)
    assert watchers.watching("t1")
    await asyncio.sleep(0)
    await watchers.close()
    assert not watchers.watching("t1")
    from app.services import chat_turn_events

    full = TurnWatchSet()
    monkeypatch.setattr(chat_turn_events, "MAX_WATCHERS", 1)
    assert full.start("a", hold)
    other = TurnWatchSet()
    assert not other.start("b", hold)  # shed: the client recovers by request
    await full.close()
    await other.close()


# -- the real socket handler, flag on and off -----------------------------------------------------


def _forbid_in_process_model_work(monkeypatch):
    async def forbidden(*_a, **_k):
        raise AssertionError("the API must not run model work while the worker flag is on")

    monkeypatch.setattr(chat, "_process_chat_message", forbidden)
    monkeypatch.setattr(chat.turn_runner, "start", forbidden)


def test_socket_send_with_the_flag_on_queues_and_never_runs_the_model(
    connect, turns, worker_flag, monkeypatch
):
    _forbid_in_process_model_work(monkeypatch)
    submit = AsyncMock(return_value=queued())
    monkeypatch.setattr(chat, "submit_turn", submit)

    async def idle(*_a, **_k):
        await asyncio.sleep(0)

    monkeypatch.setattr(chat, "watch_turn", idle)
    with connect("turn_protocol=1") as socket:
        _opening_events(socket)
        socket.send_json(
            {
                "type": "user_message",
                "content": "What does this mean?",
                "language": "en",
                "client_message_id": str(uuid4()),
                "document_id": None,
            }
        )
        first, second = socket.receive_json(), socket.receive_json()
    assert [first["type"], second["type"]] == ["chat_turn", "user_message_saved"]
    assert first["turn"]["status"] == "queued"
    submit.assert_awaited_once()


def test_a_legacy_socket_cannot_start_in_process_work_while_the_flag_is_on(
    connect, patient_id, worker_flag, monkeypatch
):
    _FakeChatStore(str(patient_id), {}).install(monkeypatch)
    _forbid_in_process_model_work(monkeypatch)
    with connect() as socket:
        _opening_events(socket)
        socket.send_json({"type": "user_message", "content": "Hello", "language": "en"})
        assert socket.receive_json()["code"] == "CHAT_PROTOCOL_UPDATE_REQUIRED"


def test_a_reconnecting_socket_shows_a_running_worker_turn_from_the_event_log(
    connect, turns, monkeypatch
):
    running = {**queued()["turn"], "status": "processing", "user_message": queued()["user_message"]}
    turns.recover = {"items": [running]}
    watched = []

    async def watch(reader, *, turn, send, **_kwargs):
        watched.append(turn["id"])
        await send({"type": "assistant_chunk", "content": "Draft from the event log"})

    monkeypatch.setattr(chat, "watch_turn", watch)
    with connect("turn_protocol=1") as socket:  # note: the flag is off; running turns still show
        events = _opening_events(socket)
    assert "chat_turns" in _types(events)
    chunk = next(e for e in events if e["type"] == "assistant_chunk")
    assert watched == [TURN] and chunk["content"] == "Draft from the event log"


def test_with_the_flag_off_the_socket_runs_in_process_exactly_as_before(
    connect, patient_id, monkeypatch
):
    assert settings.chat_turns_via_worker is False
    _FakeChatStore(str(patient_id), {}).install(monkeypatch)
    submit = AsyncMock()
    monkeypatch.setattr(chat, "submit_turn", submit)
    with connect() as socket:
        _opening_events(socket)
        socket.send_json(
            {"type": "user_message", "content": "What does this mean?", "language": "en"}
        )
        while socket.receive_json()["type"] != "assistant_complete":
            pass
    submit.assert_not_awaited()
