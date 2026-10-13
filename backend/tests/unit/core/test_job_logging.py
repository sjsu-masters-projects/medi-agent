"""The scheduled-job run lines: one shape for every job, counts only, no exception text."""

from __future__ import annotations

import json
import logging

import pytest
from postgrest.exceptions import APIError

from app.core.job_logging import FINISHED, STARTED, JobRunLog, sanitized_error


def test_a_successful_run_writes_a_started_and_a_finished_line(
    job_logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "synthetic-execution")
    log = JobRunLog("reminders_dispatch", dry_run=True)
    log.started(run_id="run-1", parameters={"window_minutes": 15})
    log.finished("success", {"medication_created": 2})

    started, finished = job_logs.lines
    assert started == {
        "message": "Scheduled job reminders_dispatch started",
        "event": STARTED,
        "job": "reminders_dispatch",
        "run_id": "run-1",
        "dry_run": True,
        "execution": "synthetic-execution",
        "parameters": {"window_minutes": 15},
        "severity": "INFO",
    }
    assert finished["event"] == FINISHED
    assert finished["status"] == "success"
    assert finished["run_id"] == "run-1"
    assert finished["summary"] == {"medication_created": 2}
    assert isinstance(finished["duration_ms"], int) and finished["duration_ms"] >= 0
    assert finished["severity"] == "INFO"
    assert [record.levelno for record in job_logs.records] == [logging.INFO, logging.INFO]


def test_a_failure_is_an_error_with_type_and_category_but_never_the_message(job_logs) -> None:
    error = RuntimeError("Synthetic Patient took metformin 500 mg and reported dizziness")
    JobRunLog("document_ingestion").finished("failed", {"claimed": 1}, error=error)

    [line] = job_logs.lines
    assert line["severity"] == "ERROR" and line["status"] == "failed"
    assert line["error_type"] == "RuntimeError"
    assert line["error_category"] == "unknown_error"
    assert "metformin" not in json.dumps(line) and "Synthetic Patient" not in json.dumps(line)
    assert job_logs.records[0].levelno == logging.ERROR


def test_a_skipped_run_is_a_warning(job_logs) -> None:
    JobRunLog("health_knowledge_refresh").finished("skipped", {}, reason="already_running")
    [line] = job_logs.lines
    assert line["severity"] == "WARNING" and line["reason"] == "already_running"


def test_only_code_shaped_error_codes_are_kept() -> None:
    database = APIError({"code": "23505", "message": "Key (dedupe_key)=(medication:x) exists"})
    assert sanitized_error(database) == {
        "error_type": "APIError",
        "error_category": "unknown_error",
        "error_code": "23505",
    }

    class _ChattyError(Exception):
        code = "row for Synthetic Patient"

    assert "error_code" not in sanitized_error(_ChattyError("x"))


def test_each_line_is_one_json_object_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    JobRunLog("reminders_dispatch").finished("success", {"medication_created": 0})
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["severity"] == "INFO" and payload["event"] == FINISHED
