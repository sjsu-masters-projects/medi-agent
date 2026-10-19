"""Structured logs: Cloud Logging fields, correlation ids, and no patient text."""

import json
import logging

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.request_context import RequestContextMiddleware
from app.core.structured_logging import (
    JsonFormatter,
    ReadableFormatter,
    configure_logging,
    current_context,
    end_request,
    hash_identifier,
    log_event,
    parse_trace_header,
    set_actor,
    set_turn_id,
    start_request,
)

TRACE = "105445aa7843bc8bf206b12000100000"


def _line(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(message="hello", level=logging.INFO, **extra) -> logging.LogRecord:
    logger = logging.getLogger("t")
    return logger.makeRecord("t", level, __file__, 1, message, (), None, extra=extra or None)


def test_json_line_has_the_cloud_logging_fields_and_the_correlation_ids(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-project")
    tokens = start_request(f"{TRACE}/1;o=1")
    try:
        set_actor("patient-123", "session-abc")
        set_turn_id("turn-1")
        record = _record(
            "Chat turn begun",
            event="chat_turn.begin",
            outcome="execute",
            duration_ms=12,
            execute=True,
        )
        line = _line(record)
    finally:
        end_request(tokens)
    assert line["severity"] == "INFO" and line["message"] == "Chat turn begun"
    assert line["request_id"] == TRACE and line["turn_id"] == "turn-1"
    assert line["event"] == "chat_turn.begin" and line["outcome"] == "execute"
    assert line["duration_ms"] == 12 and line["execute"] is True
    assert line["logging.googleapis.com/trace"] == (f"projects/synthetic-project/traces/{TRACE}")
    assert line["actor_hash"] == hash_identifier("patient-123")
    assert line["session_hash"] == hash_identifier("session-abc")
    assert "patient-123" not in json.dumps(line) and "session-abc" not in json.dumps(line)


def test_hashes_are_salted_short_and_stable():
    assert hash_identifier("x") == hash_identifier("x") != hash_identifier("y")
    assert len(hash_identifier("x")) == 12
    assert hash_identifier("x") not in {"2d711642b726"}  # not the unsalted sha256 prefix


def test_trace_header_parsing():
    assert parse_trace_header(f"{TRACE}/9;o=1") == TRACE
    assert parse_trace_header(TRACE) == TRACE
    assert parse_trace_header("not a trace") is None
    assert parse_trace_header(None) is None


def test_context_is_reset_after_the_request():
    tokens = start_request(None)
    set_turn_id("t")
    assert current_context()["request_id"]
    end_request(tokens)
    assert current_context() == {}


def test_unknown_extra_fields_never_reach_the_log():
    line = _line(_record("m", content="PRIVATE TEXT", message_text="PRIVATE", event="e"))
    assert "PRIVATE" not in json.dumps(line)


def test_exception_message_is_never_written_only_type_and_frames():
    try:
        raise ValueError("PRIVATE patient sentence")
    except ValueError as exc:
        import sys

        record = logging.getLogger("t").makeRecord(
            "t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
        del exc
    text = JsonFormatter().format(record)
    assert "PRIVATE" not in text
    assert json.loads(text)["error_type"] == "ValueError"


def test_credentials_in_messages_are_redacted():
    assert "abc123" not in JsonFormatter().format(_record("url ?token=abc123"))


def test_log_event_ignores_fields_outside_the_vocabulary(caplog):
    with caplog.at_level(logging.INFO):
        log_event(logging.getLogger("t"), "x.y", reason="r", note="PRIVATE")
    assert not hasattr(caplog.records[-1], "note")
    assert caplog.records[-1].reason == "r"


def test_readable_output_is_one_plain_line():
    tokens = start_request(None)
    try:
        text = ReadableFormatter().format(_record("hello", event="a.b", outcome="ok"))
    finally:
        end_request(tokens)
    assert "hello" in text and "event=a.b" in text and "{" not in text


def test_configure_logging_picks_json_on_cloud_run(monkeypatch, capsys):
    monkeypatch.setenv("K_SERVICE", "mediagent-backend")
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        configure_logging()
        logging.getLogger("app.t").info("on cloud run")
        out = capsys.readouterr().out.strip().splitlines()[-1]
        assert json.loads(out)["message"] == "on cloud run"
        monkeypatch.delenv("K_SERVICE")
        configure_logging()
        logging.getLogger("app.t").info("local")
        assert capsys.readouterr().out.strip().endswith("local")
    finally:
        root.handlers[:] = before


@pytest.mark.parametrize("header,expect_trace", [(f"{TRACE}/1;o=1", True), (None, False)])
def test_middleware_sets_the_request_id_from_the_trace_header_or_generates_one(
    monkeypatch, header, expect_trace
):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "synthetic-project")
    seen = {}

    async def endpoint(request):
        seen.update(current_context())
        return JSONResponse({})

    app = Starlette(routes=[Route("/", endpoint)])
    app.add_middleware(RequestContextMiddleware)
    headers = {"X-Cloud-Trace-Context": header} if header else {}
    TestClient(app).get("/", headers=headers)
    if expect_trace:
        assert seen["request_id"] == TRACE and "logging.googleapis.com/trace" in seen
    else:
        assert len(seen["request_id"]) == 32 and "logging.googleapis.com/trace" not in seen
    assert current_context() == {}


def test_task_id_joins_the_correlation_fields_and_resets_with_the_request():
    from app.core import structured_logging as sl

    tokens = sl.start_request(None)
    try:
        sl.set_task_id("chat-turn-abc-a1")
        assert sl.current_context()["task_id"] == "chat-turn-abc-a1"
        assert sl.current_request_id() == sl.current_context()["request_id"]
    finally:
        sl.end_request(tokens)
    assert "task_id" not in sl.current_context()
