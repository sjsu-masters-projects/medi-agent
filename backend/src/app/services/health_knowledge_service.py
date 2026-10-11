"""Cached public reference text for medications and conditions, shared by every patient.

This is the one place Nora's general medical knowledge comes from. It is the same for all
patients and holds no patient data: the cache is keyed by an RxNorm ingredient or a
condition name, never by who asked. What a particular patient takes or has lives in their
own record and is read by the patient-scoped tools; the tools join the two.

Freshness, as the NORA-002 plan sets it:

- a row checked within ``FRESH_FOR`` is served without a request;
- a recorded miss is retried after ``MISS_RETRY_AFTER``;
- a source that does not answer never overwrites or removes a cached row, and is never
  recorded as a miss; an old row is served instead, marked stale after ``STALE_AFTER``;
- an inline lookup stops after ``INLINE_BUDGET_SECONDS`` and reports the source as
  unavailable, so a slow source cannot hold up a chat reply.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast

import httpx

from app.services import health_knowledge_sources as sources
from app.services.health_knowledge_sources import Ingredient, SourceText, SourceUnavailableError

logger = logging.getLogger(__name__)

FRESH_FOR = timedelta(days=7)
MISS_RETRY_AFTER = timedelta(days=7)
STALE_AFTER = timedelta(days=30)
RESOLUTION_FRESH_FOR = timedelta(days=30)
INLINE_BUDGET_SECONDS = 8.0

Status = Literal["found", "not_found", "unavailable"]
_MEDICATION_SOURCES = (("medlineplus", "en-US"), ("medlineplus", "es-MX"), ("dailymed", "en-US"))


@dataclass(frozen=True)
class Reference:
    """One cached source text, with what a citation needs."""

    source: str
    locale: str
    title: str
    url: str | None
    summary: str
    sections: dict[str, str]
    source_version: str | None
    source_updated_on: date | None
    checked_at: datetime
    stale: bool


@dataclass(frozen=True)
class Knowledge:
    status: Status
    subject: str | None = None
    references: list[Reference] = field(default_factory=list)


def name_key(name: str) -> str:
    """The cache key for a name as written: case- and spacing-insensitive."""
    return " ".join(name.casefold().split())[:200]


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


class HealthKnowledgeService:
    def __init__(
        self,
        db: Any,
        *,
        client_factory: Callable[[], httpx.AsyncClient] = httpx.AsyncClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        budget_seconds: float = INLINE_BUDGET_SECONDS,
    ) -> None:
        self.db = db
        self._client_factory = client_factory
        self._now = clock
        self._budget = budget_seconds

    # ── reads ──────────────────────────────────────────────────────────────

    async def medication(self, name: str) -> Knowledge:
        """General reference text for a medication name as a patient or record writes it."""
        try:
            async with asyncio.timeout(self._budget):
                return await self._medication(name)
        except TimeoutError:
            logger.warning("Medication reference lookup exceeded its time budget")
            return await self._cached_only("medication", await self._known_rxcui(name))

    async def condition(self, name: str, locale: str) -> Knowledge:
        """A plain-language MedlinePlus topic for a condition, in the patient's language."""
        key = name_key(name)
        if not key:
            return Knowledge(status="not_found")
        try:
            async with asyncio.timeout(self._budget):
                return await self._condition(key, name, locale)
        except TimeoutError:
            logger.warning("Condition reference lookup exceeded its time budget")
            return await self._cached_only("condition", key, locales=(locale,))

    async def _medication(self, name: str) -> Knowledge:
        ingredient = await self._resolve(name)
        if ingredient is None:
            return Knowledge(status="not_found")
        if isinstance(ingredient, SourceUnavailableError):
            return Knowledge(status="unavailable")
        rows = await self._rows("medication", ingredient.rxcui)
        if not self._needs_fetch(rows, _MEDICATION_SOURCES):
            return self._knowledge(rows, ingredient.name)
        async with self._client_factory() as client:
            fetched = await sources.gather_medication(client, ingredient)
        await self._store("medication", ingredient.rxcui, ingredient.name, fetched, rows)
        knowledge = self._knowledge(
            await self._rows("medication", ingredient.rxcui), ingredient.name
        )
        return _unless_unavailable(knowledge, fetched)

    async def _condition(self, key: str, name: str, locale: str) -> Knowledge:
        wanted = (("medlineplus", locale),)
        rows = await self._rows("condition", key)
        if self._needs_fetch(rows, wanted):
            async with self._client_factory() as client:
                try:
                    found: sources.Fetched = await sources.medlineplus_condition(
                        client, name, locale
                    )
                except SourceUnavailableError as error:
                    found = error
            await self._store("condition", key, name.strip()[:200], {wanted[0]: found}, rows)
            rows = [row for row in await self._rows("condition", key) if row["locale"] == locale]
            return _unless_unavailable(self._knowledge(rows, name.strip()), {wanted[0]: found})
        rows = [row for row in rows if row["locale"] == locale]
        return self._knowledge(rows, name.strip())

    async def _cached_only(
        self, subject_type: str, key: str | None, *, locales: tuple[str, ...] | None = None
    ) -> Knowledge:
        if not key:
            return Knowledge(status="unavailable")
        rows = await self._rows(subject_type, key)
        if locales:
            rows = [row for row in rows if row["locale"] in locales]
        knowledge = self._knowledge(rows, rows[0]["subject_name"] if rows else None)
        return knowledge if knowledge.status == "found" else Knowledge(status="unavailable")

    # ── name resolution ────────────────────────────────────────────────────

    async def _known_rxcui(self, name: str) -> str | None:
        row = await self._resolution_row(name_key(name))
        return str(row["rxcui"]) if row and row.get("rxcui") else None

    async def _resolve(self, name: str) -> Ingredient | SourceUnavailableError | None:
        key = name_key(name)
        if not key:
            return None
        cached = await self._resolution_row(key)
        now = self._now()
        if cached is not None:
            age = now - _parse_time(cached["resolved_at"])
            if cached.get("rxcui") and age < RESOLUTION_FRESH_FOR:
                return Ingredient(rxcui=str(cached["rxcui"]), name=str(cached["ingredient"]))
            if not cached.get("rxcui") and age < MISS_RETRY_AFTER:
                return None
        try:
            async with self._client_factory() as client:
                ingredient = await sources.resolve_ingredient(client, name)
        except SourceUnavailableError as error:
            if cached is not None and cached.get("rxcui"):
                return Ingredient(rxcui=str(cached["rxcui"]), name=str(cached["ingredient"]))
            return error
        await self._execute(
            self.db.table("medication_name_resolutions").upsert(
                {
                    "name_key": key,
                    "rxcui": ingredient.rxcui if ingredient else None,
                    "ingredient": ingredient.name if ingredient else None,
                    "resolved_at": now.isoformat(),
                },
                on_conflict="name_key",
            )
        )
        return ingredient

    async def _resolution_row(self, key: str) -> dict[str, Any] | None:
        result = await self._execute(
            self.db.table("medication_name_resolutions")
            .select("name_key, rxcui, ingredient, resolved_at")
            .eq("name_key", key)
            .limit(1)
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return rows[0] if rows else None

    # ── cache ──────────────────────────────────────────────────────────────

    async def _rows(self, subject_type: str, key: str) -> list[dict[str, Any]]:
        result = await self._execute(
            self.db.table("health_knowledge")
            .select("*")
            .eq("subject_type", subject_type)
            .eq("subject_key", key)
        )
        return cast(list[dict[str, Any]], result.data or [])

    def _needs_fetch(self, rows: list[dict[str, Any]], wanted: tuple[tuple[str, str], ...]) -> bool:
        by_source = {(row["source"], row["locale"]): row for row in rows}
        now = self._now()
        for key in wanted:
            row = by_source.get(key)
            if row is None:
                return True
            limit = FRESH_FOR if row["status"] == "found" else MISS_RETRY_AFTER
            if now - _parse_time(row["checked_at"]) >= limit:
                return True
        return False

    async def _store(
        self,
        subject_type: str,
        key: str,
        subject_name: str,
        fetched: dict[tuple[str, str], sources.Fetched],
        existing: list[dict[str, Any]],
    ) -> None:
        by_source = {(row["source"], row["locale"]): row for row in existing}
        now = self._now().isoformat()
        for (source, locale), result in fetched.items():
            if isinstance(result, SourceUnavailableError):
                continue  # Keep whatever is cached; an outage is not a miss.
            previous = by_source.get((source, locale))
            row = self._row(subject_type, key, subject_name, source, locale, result, now)
            if previous is not None and previous.get("content_hash") == row["content_hash"]:
                row["fetched_at"] = previous["fetched_at"]
            await self._execute(
                self.db.table("health_knowledge").upsert(
                    row, on_conflict="subject_type,subject_key,source,locale"
                )
            )

    @staticmethod
    def _row(
        subject_type: str,
        key: str,
        subject_name: str,
        source: str,
        locale: str,
        text: SourceText | None,
        now: str,
    ) -> dict[str, Any]:
        base = {
            "subject_type": subject_type,
            "subject_key": key,
            "subject_name": subject_name,
            "source": source,
            "locale": locale,
            "checked_at": now,
            "fetched_at": now,
        }
        if text is None:
            return {
                **base,
                "status": "not_found",
                "title": "",
                "url": None,
                "summary": "",
                "sections": {},
                "source_version": None,
                "source_updated_on": None,
                "content_hash": "",
            }
        url = text.url if text.url and text.url.startswith("https://") else None
        return {
            **base,
            "status": "found",
            "title": text.title[:300],
            "url": url,
            "summary": text.summary,
            "sections": text.sections,
            "source_version": (text.version or None) and text.version[:80],
            "source_updated_on": text.updated_on.isoformat() if text.updated_on else None,
            "content_hash": text.content_hash,
        }

    def _knowledge(self, rows: list[dict[str, Any]], subject: str | None) -> Knowledge:
        now = self._now()
        references = [
            Reference(
                source=str(row["source"]),
                locale=str(row["locale"]),
                title=str(row.get("title") or ""),
                url=row.get("url"),
                summary=str(row.get("summary") or ""),
                sections=cast(dict[str, str], row.get("sections") or {}),
                source_version=row.get("source_version"),
                source_updated_on=_parse_date(row.get("source_updated_on")),
                checked_at=_parse_time(row["checked_at"]),
                stale=now - _parse_time(row["checked_at"]) >= STALE_AFTER,
            )
            for row in rows
            if row.get("status") == "found"
        ]
        if not references:
            return Knowledge(status="not_found", subject=subject)
        return Knowledge(status="found", subject=subject, references=references)

    # ── weekly refresh ─────────────────────────────────────────────────────

    async def refresh_due(self, *, limit: int) -> dict[str, int]:
        """Re-check the oldest cached subjects and every patient medication not yet cached.

        Counts only; no names are returned or logged, because the seed list comes from
        patients' medication and condition rows.
        """
        counts = {"subjects_checked": 0, "subjects_unavailable": 0, "subjects_failed": 0}
        cutoff = (self._now() - FRESH_FOR).isoformat()
        due = await self._execute(
            self.db.table("health_knowledge")
            .select("subject_type, subject_key, subject_name, locale")
            .lt("checked_at", cutoff)
            .order("checked_at")
            .limit(limit * 3)
        )
        subjects: dict[tuple[str, str], tuple[str, set[str]]] = {}
        for row in cast(list[dict[str, Any]], due.data or []):
            entry = subjects.setdefault(
                (row["subject_type"], row["subject_key"]), (row["subject_name"], set())
            )
            entry[1].add(str(row["locale"]))
        for name in await self._uncached_medication_names(limit):
            subjects.setdefault(("medication_name", name_key(name)), (name, set()))

        for (subject_type, _key), (name, locales) in list(subjects.items())[:limit]:
            counts["subjects_checked"] += 1
            try:
                if subject_type == "condition":
                    results = [await self.condition(name, locale) for locale in sorted(locales)]
                else:
                    results = [await self.medication(name)]
            except Exception:  # noqa: BLE001 - one subject never stops the run
                logger.exception("Reference refresh failed for one subject")
                counts["subjects_failed"] += 1
                continue
            if any(result.status == "unavailable" for result in results):
                counts["subjects_unavailable"] += 1
        return counts

    async def _uncached_medication_names(self, limit: int) -> list[str]:
        meds = await self._execute(
            self.db.table("medications").select("name").eq("is_active", True).limit(500)
        )
        names = {
            _medication_name(str(row.get("name") or ""))
            for row in cast(list[dict[str, Any]], meds.data or [])
        }
        names.discard("")
        if not names:
            return []
        known = await self._execute(
            self.db.table("medication_name_resolutions")
            .select("name_key")
            .in_("name_key", sorted(name_key(name) for name in names))
        )
        resolved = {str(row["name_key"]) for row in cast(list[dict[str, Any]], known.data or [])}
        return sorted(name for name in names if name_key(name) not in resolved)[:limit]

    async def _execute(self, query: Any) -> Any:
        return await asyncio.to_thread(query.execute)


def _unless_unavailable(
    knowledge: Knowledge, fetched: dict[tuple[str, str], sources.Fetched]
) -> Knowledge:
    """Nothing found because a source did not answer is an outage, not a miss."""
    if knowledge.status == "not_found" and any(
        isinstance(result, SourceUnavailableError) for result in fetched.values()
    ):
        return Knowledge(status="unavailable", subject=knowledge.subject)
    return knowledge


def _medication_name(name: str) -> str:
    """A medication's name without the dose text a record often carries with it."""
    return re.split(r"\s\d", name.strip(), maxsplit=1)[0].strip()
