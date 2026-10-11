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
    assert counts == {"subjects_checked": 1, "subjects_unavailable": 0, "subjects_failed": 0}
    assert [row["name_key"] for row in db.tables["medication_name_resolutions"]] == ["metformin"]
    # Nothing is due a week later minus a day; everything is due after it.
    clock.now += timedelta(days=6)
    assert (await _service(db, clock).refresh_due(limit=10))["subjects_checked"] == 0
    clock.now += timedelta(days=2)
    assert (await _service(db, clock).refresh_due(limit=10))["subjects_checked"] == 1


def test_name_keys_ignore_case_and_spacing() -> None:
    assert name_key("  Metformina   500 MG ") == "metformina 500 mg"
