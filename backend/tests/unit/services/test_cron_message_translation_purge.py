"""LOC-003 item 9: the message-translation retention rule runs as a recorded cron job.

A retention function nothing calls is not a retention rule, so the sweep has a job of its
own with the same run record and log lines as every other scheduled job.
"""

from __future__ import annotations

import pytest

from tests.unit.services.cron_store import Store, service_for


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.mark.asyncio
async def test_the_purge_reports_what_it_removed(store: Store) -> None:
    store.rpc_results["purge_message_translations"] = {
        "orphans_removed": 3,
        "expired_failure_markers_removed": 2,
    }

    result = await service_for(store).purge_message_translations()

    assert result["job_name"] == "message_translation_purge"
    assert result["status"] == "success"
    assert result["summary"] == {
        "orphans_removed": 3,
        "expired_failure_markers_removed": 2,
    }
    [(name, params)] = store.rpc_calls
    assert name == "purge_message_translations"
    assert params == {"p_failure_marker_max_age": "7 days"}


@pytest.mark.asyncio
async def test_the_failure_marker_age_is_passed_through_as_an_interval(store: Store) -> None:
    store.rpc_results["purge_message_translations"] = {}

    await service_for(store).purge_message_translations(failure_marker_max_age_days=30)

    assert store.rpc_calls[0][1] == {"p_failure_marker_max_age": "30 days"}


@pytest.mark.asyncio
async def test_a_run_that_removed_nothing_is_still_a_recorded_success(store: Store) -> None:
    store.rpc_results["purge_message_translations"] = {}

    result = await service_for(store).purge_message_translations()

    assert result["status"] == "success"
    assert result["summary"] == {"orphans_removed": 0, "expired_failure_markers_removed": 0}
    [run] = store.tables["cron_job_runs"]
    assert run["job_name"] == "message_translation_purge"
    assert run["metadata"] == {"failure_marker_max_age_days": 7}


@pytest.mark.asyncio
async def test_a_database_failure_is_a_failed_run_not_a_silent_one(store: Store) -> None:
    def explode(name: str, params: object = None):
        raise RuntimeError("purge unavailable")

    store.rpc = explode  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        await service_for(store).purge_message_translations()

    [run] = store.tables["cron_job_runs"]
    assert run["status"] == "failed"
