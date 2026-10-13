"""Reference cache: freshness, misses, outages, the time budget and the weekly refresh."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import health_knowledge_service as module
from app.services.health_knowledge_service import HealthKnowledgeService, name_key
from app.services.health_knowledge_sources import Ingredient, SourceText, SourceUnavailableError

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)
METFORMIN = Ingredient("6809", "metformin")


class _Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, db: _Db, table: str) -> None:
        self.db, self.table = db, table
        self.filters: list[Any] = []
        self.write: tuple[str, Any, str | None] | None = None
        self._limit: int | None = None

    def select(self, *_: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.filters.append(lambda row: str(row.get(column)) == str(value))
        return self

    def lt(self, column: str, value: Any) -> _Query:
        self.filters.append(lambda row: str(row.get(column)) < str(value))
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self.filters.append(lambda row: str(row.get(column)) in {str(v) for v in values})
        return self

    def order(self, *_: Any, **__: Any) -> _Query:
        return self

    def limit(self, count: int) -> _Query:
        self._limit = count
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str) -> _Query:
        self.write = ("upsert", row, on_conflict)
        return self

    def execute(self) -> _Result:
        rows = self.db.tables.setdefault(self.table, [])
        if self.write is not None:
            _, row, conflict = self.write
            keys = (conflict or "").split(",")
            for index, existing in enumerate(rows):
                if all(existing.get(key) == row.get(key) for key in keys):
                    rows[index] = {**existing, **row}
                    break
            else:
                rows.append(dict(row))
            self.db.writes += 1
            return _Result([row])
        matched = [row for row in rows if all(test(row) for test in self.filters)]
        return _Result(matched[: self._limit] if self._limit else matched)


class _Db:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.writes = 0

    def table(self, name: str) -> _Query:
        return _Query(self, name)


class _Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class _NullClient:
    async def __aenter__(self) -> _NullClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


def _summary(
    title: str = "Metformin", text: str = "Metformin treats type 2 diabetes."
) -> SourceText:
    return SourceText(
        title=title, url="https://medlineplus.gov/druginfo/meds/a696005.html", summary=text
    )


def _label() -> SourceText:
    return SourceText(
        title="METFORMIN TABLET",
        url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=s1",
        sections={"drug_interactions": "Topiramate."},
        version="7",
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the fetchers; tests set ``calls["medication"]`` to change what comes back."""
    state: dict[str, Any] = {
        "resolve": 0,
        "gather": 0,
        "ingredient": METFORMIN,
        "medication": {
            ("medlineplus", "en-US"): _summary(),
            ("medlineplus", "es-MX"): _summary("Metformina", "La metformina trata la diabetes."),
            ("dailymed", "en-US"): _label(),
        },
    }

    async def resolve(_client: Any, _name: str) -> Any:
        state["resolve"] += 1
        if isinstance(state["ingredient"], Exception):
            raise state["ingredient"]
        return state["ingredient"]

    async def gather(_client: Any, _ingredient: Ingredient) -> Any:
        state["gather"] += 1
        return dict(state["medication"])

    monkeypatch.setattr(module.sources, "resolve_ingredient", resolve)
    monkeypatch.setattr(module.sources, "gather_medication", gather)
    return state


def _service(db: _Db, clock: _Clock, **kwargs: Any) -> HealthKnowledgeService:
    return HealthKnowledgeService(db, client_factory=_NullClient, clock=clock, **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_first_lookup_fetches_and_a_repeat_within_a_week_is_served_from_cache(
    calls: dict[str, Any],
) -> None:
    db, clock = _Db(), _Clock()
    first = await _service(db, clock).medication("Metformina 500 mg")
    assert first.status == "found" and first.subject == "metformin"
    assert {(r.source, r.locale) for r in first.references} == {
        ("medlineplus", "en-US"),
        ("medlineplus", "es-MX"),
        ("dailymed", "en-US"),
    }
    clock.now += timedelta(days=6)
    again = await _service(db, clock).medication("metformina 500 MG")
    assert again.status == "found"
    assert calls["gather"] == 1 and calls["resolve"] == 1  # name resolution is cached too


@pytest.mark.asyncio
async def test_after_a_week_it_rechecks_and_unchanged_text_keeps_its_fetch_date(
    calls: dict[str, Any],
) -> None:
    db, clock = _Db(), _Clock()
    await _service(db, clock).medication("metformin")
    clock.now += timedelta(days=8)
    await _service(db, clock).medication("metformin")
    assert calls["gather"] == 2
    row = next(r for r in db.tables["health_knowledge"] if r["source"] == "dailymed")
    assert row["fetched_at"] == NOW.isoformat()
    assert row["checked_at"] == clock.now.isoformat()


@pytest.mark.asyncio
async def test_an_outage_keeps_the_cached_text_and_marks_it_stale_after_a_month(
    calls: dict[str, Any],
) -> None:
    db, clock = _Db(), _Clock()
    await _service(db, clock).medication("metformin")
    calls["medication"] = {key: SourceUnavailableError("down") for key in calls["medication"]}
    clock.now += timedelta(days=31)
    result = await _service(db, clock).medication("metformin")
    assert result.status == "found"
    assert all(reference.stale for reference in result.references)
    assert all(row["status"] == "found" for row in db.tables["health_knowledge"])


@pytest.mark.asyncio
async def test_an_outage_with_nothing_cached_is_unavailable_and_records_no_miss(
    calls: dict[str, Any],
) -> None:
    calls["medication"] = {key: SourceUnavailableError("down") for key in calls["medication"]}
    db = _Db()
    result = await _service(db, _Clock()).medication("metformin")
    assert result.status == "unavailable"
    assert db.tables.get("health_knowledge", []) == []


@pytest.mark.asyncio
async def test_an_rxnorm_outage_is_unavailable_and_never_cached_as_a_miss(
    calls: dict[str, Any],
) -> None:
    calls["ingredient"] = SourceUnavailableError("rxnav")
    db = _Db()
    result = await _service(db, _Clock()).medication("metformin")
    assert result.status == "unavailable"
    assert db.tables.get("medication_name_resolutions", []) == []


@pytest.mark.asyncio
async def test_an_unknown_name_is_cached_as_a_miss_and_retried_after_a_week(
    calls: dict[str, Any],
) -> None:
    calls["ingredient"] = None
    db, clock = _Db(), _Clock()
    assert (await _service(db, clock).medication("hydration")).status == "not_found"
    assert (await _service(db, clock).medication("Hydration")).status == "not_found"
    assert calls["resolve"] == 1
    clock.now += timedelta(days=8)
    await _service(db, clock).medication("hydration")
    assert calls["resolve"] == 2


@pytest.mark.asyncio
async def test_a_slow_source_returns_within_the_budget(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow(_client: Any, _ingredient: Ingredient) -> Any:
        await asyncio.sleep(5)

    monkeypatch.setattr(module.sources, "gather_medication", slow)
    result = await _service(_Db(), _Clock(), budget_seconds=0.05).medication("metformin")
    assert result.status == "unavailable"


def _condition_fetcher(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Answer every condition search with a topic; record (name, locale) per request."""
    asked: list[tuple[str, str]] = []

    async def fetch(_client: Any, name: str, locale: str) -> SourceText:
        asked.append((name, locale))
        return SourceText(
            title=name, url="https://medlineplus.gov/diabetestype2.html", summary="Topic."
        )

    monkeypatch.setattr(module.sources, "medlineplus_condition", fetch)
    return asked


@pytest.mark.asyncio
async def test_the_weekly_refresh_seeds_uncached_patient_medications(
    calls: dict[str, Any],
) -> None:
    db, clock = _Db(), _Clock()
    db.tables["medications"] = [
        {"name": "Metformin 500 mg", "is_active": True},
        {"name": "Lisinopril 10 mg", "is_active": False},
    ]
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts == {
        "subjects_total": 0,
        "subjects_due": 0,
        "subjects_new_medications": 1,
        "subjects_new_conditions": 0,
        "subjects_new_locales": 0,
        "subjects_checked": 1,
        "subjects_updated": 1,
        "subjects_unavailable": 0,
        "subjects_failed": 0,
        "subjects_deferred": 0,
        "next_due_at": None,
        "sources": {"dailymed": {"updated": 1}, "medlineplus": {"updated": 2}},
    }
    assert [row["name_key"] for row in db.tables["medication_name_resolutions"]] == ["metformin"]
    # Nothing is due within six days; everything is due after it.
    clock.now += timedelta(days=6)
    idle = await _service(db, clock).refresh_due(limit=10)
    assert idle["subjects_checked"] == 0
    clock.now += timedelta(days=2)
    again = await _service(db, clock).refresh_due(limit=10)
    assert again["subjects_checked"] == 1 and again["subjects_due"] == 1
    assert again["subjects_updated"] == 0  # same text: re-checked, not rewritten
    assert again["sources"] == {"dailymed": {"unchanged": 1}, "medlineplus": {"unchanged": 2}}


@pytest.mark.asyncio
async def test_a_run_that_checks_nothing_says_how_many_are_cached_and_when_the_next_is_due(
    calls: dict[str, Any],
) -> None:
    db, clock = _Db(), _Clock()
    db.tables["medications"] = [{"name": "Metformin 500 mg", "is_active": True}]
    await _service(db, clock).refresh_due(limit=10)
    clock.now += timedelta(hours=2)
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_checked"] == 0
    assert counts["subjects_total"] == 1 and counts["subjects_due"] == 0
    assert counts["next_due_at"] == (NOW + module.REFRESH_DUE_AFTER).isoformat()


@pytest.mark.asyncio
async def test_rows_the_last_weekly_run_checked_are_due_at_the_next_weekly_run(
    calls: dict[str, Any],
) -> None:
    """A run's own writes land after its start; a 7-day cutoff skipped them for a week."""
    db, clock = _Db(), _Clock()
    db.tables["medications"] = [{"name": "Metformin 500 mg", "is_active": True}]
    clock.now = NOW + timedelta(seconds=40)
    await _service(db, clock).refresh_due(limit=10)
    # Next Sunday's run starts at the same time, or an hour earlier after a clock change.
    clock.now = NOW + timedelta(days=7) - timedelta(hours=1)
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_due"] == 1 and counts["subjects_checked"] == 1
    assert calls["gather"] == 2


@pytest.mark.asyncio
async def test_the_weekly_refresh_seeds_documented_conditions_in_both_languages(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _condition_fetcher(monkeypatch)
    db, clock = _Db(), _Clock()
    db.tables["conditions"] = [
        {"name": "Type 2 diabetes", "status": "active"},
        {"name": "type 2  Diabetes", "status": "active"},
        {"name": "Resolved sprain", "status": "resolved"},
    ]
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_new_conditions"] == 1 and counts["subjects_checked"] == 1
    assert sorted(locale for _name, locale in asked) == ["en-US", "es-MX"]
    assert {(row["subject_key"], row["locale"]) for row in db.tables["health_knowledge"]} == {
        ("type 2 diabetes", "en-US"),
        ("type 2 diabetes", "es-MX"),
    }
    # Cached now: a second run the same day neither seeds nor re-checks it.
    again = await _service(db, clock).refresh_due(limit=10)
    assert again["subjects_new_conditions"] == 0 and again["subjects_checked"] == 0


def _cached_condition(name: str, locale: str, checked_at: datetime) -> dict[str, Any]:
    return {
        "subject_type": "condition",
        "subject_key": name_key(name),
        "subject_name": name,
        "source": "medlineplus",
        "locale": locale,
        "status": "found",
        "title": name,
        "url": "https://medlineplus.gov/diabetestype2.html",
        "summary": "Topic.",
        "sections": {},
        "source_version": None,
        "source_updated_on": None,
        "content_hash": "cached",
        "checked_at": checked_at.isoformat(),
        "fetched_at": checked_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_a_condition_cached_in_one_language_gets_the_other(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _condition_fetcher(monkeypatch)
    db, clock = _Db(), _Clock()
    yesterday = NOW - timedelta(days=1)
    db.tables["conditions"] = [
        {"name": "Type 2 diabetes", "status": "active"},
        {"name": "Diabetes tipo 2", "status": "active"},
    ]
    db.tables["health_knowledge"] = [
        _cached_condition("Type 2 diabetes", "en-US", yesterday),
        _cached_condition("Diabetes tipo 2", "es-MX", yesterday),
    ]
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_new_locales"] == 2 and counts["subjects_new_conditions"] == 0
    assert counts["subjects_due"] == 0 and counts["subjects_checked"] == 2
    # Only the missing language is fetched; the cached one is not due and not re-checked.
    assert sorted(asked) == [("Diabetes tipo 2", "en-US"), ("Type 2 diabetes", "es-MX")]
    rows = {(row["subject_key"], row["locale"]): row for row in db.tables["health_knowledge"]}
    assert set(rows) == {
        ("type 2 diabetes", "en-US"),
        ("type 2 diabetes", "es-MX"),
        ("diabetes tipo 2", "es-MX"),
        ("diabetes tipo 2", "en-US"),
    }
    assert rows[("type 2 diabetes", "en-US")]["checked_at"] == yesterday.isoformat()
    again = await _service(db, clock).refresh_due(limit=10)
    assert again["subjects_new_locales"] == 0 and again["subjects_checked"] == 0


@pytest.mark.asyncio
async def test_conditions_cached_in_both_languages_are_left_alone_until_due(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _condition_fetcher(monkeypatch)
    db, clock = _Db(), _Clock()
    yesterday = NOW - timedelta(days=1)
    db.tables["conditions"] = [{"name": "High blood pressure", "status": "active"}]
    db.tables["health_knowledge"] = [
        _cached_condition("High blood pressure", "en-US", yesterday),
        {**_cached_condition("High blood pressure", "es-MX", yesterday), "status": "not_found"},
    ]
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_new_locales"] == 0 and counts["subjects_checked"] == 0
    assert asked == [] and db.writes == 0


@pytest.mark.asyncio
async def test_a_due_condition_missing_a_language_is_checked_in_both(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _condition_fetcher(monkeypatch)
    db, clock = _Db(), _Clock()
    db.tables["conditions"] = [{"name": "Type 2 diabetes", "status": "active"}]
    db.tables["health_knowledge"] = [
        _cached_condition("Type 2 diabetes", "en-US", NOW - timedelta(days=8)),
    ]
    counts = await _service(db, clock).refresh_due(limit=10)
    assert counts["subjects_due"] == 1 and counts["subjects_new_locales"] == 1
    assert counts["subjects_checked"] == 1 and counts["subjects_deferred"] == 0
    assert sorted(locale for _name, locale in asked) == ["en-US", "es-MX"]


@pytest.mark.asyncio
async def test_missing_languages_beyond_the_limit_are_deferred(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = _condition_fetcher(monkeypatch)
    db, clock = _Db(), _Clock()
    yesterday = NOW - timedelta(days=1)
    names = [f"Condition {index}" for index in range(3)]
    db.tables["conditions"] = [{"name": name, "status": "active"} for name in names]
    db.tables["health_knowledge"] = [_cached_condition(name, "en-US", yesterday) for name in names]
    counts = await _service(db, clock).refresh_due(limit=2)
    assert counts["subjects_new_locales"] == 3
    assert counts["subjects_checked"] == 2 and counts["subjects_deferred"] == 1
    assert len(asked) == 2
    later = await _service(db, clock).refresh_due(limit=2)
    assert later["subjects_new_locales"] == 1 and later["subjects_checked"] == 1


@pytest.mark.asyncio
async def test_a_resolved_medication_with_no_cached_text_is_seeded_again(
    calls: dict[str, Any],
) -> None:
    """An outage after resolution left no rows; the name is no longer 'uncached' by name."""
    calls["medication"] = {key: SourceUnavailableError("down") for key in calls["medication"]}
    db, clock = _Db(), _Clock()
    db.tables["medications"] = [{"name": "Metformin 500 mg", "is_active": True}]
    first = await _service(db, clock).refresh_due(limit=10)
    assert first["subjects_unavailable"] == 1
    assert first["sources"] == {"dailymed": {"unavailable": 1}, "medlineplus": {"unavailable": 2}}
    calls["medication"] = {
        ("medlineplus", "en-US"): _summary(),
        ("medlineplus", "es-MX"): _summary("Metformina", "La metformina trata la diabetes."),
        ("dailymed", "en-US"): _label(),
    }
    clock.now += timedelta(hours=1)
    second = await _service(db, clock).refresh_due(limit=10)
    assert second["subjects_new_medications"] == 1 and second["subjects_updated"] == 1


@pytest.mark.asyncio
async def test_subjects_beyond_the_limit_are_reported_as_deferred(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _condition_fetcher(monkeypatch)
    db = _Db()
    db.tables["conditions"] = [
        {"name": f"Condition {index}", "status": "active"} for index in range(3)
    ]
    counts = await _service(db, _Clock()).refresh_due(limit=2)
    assert counts["subjects_checked"] == 2 and counts["subjects_deferred"] == 1


def test_name_keys_ignore_case_and_spacing() -> None:
    assert name_key("  Metformina   500 MG ") == "metformina 500 mg"
