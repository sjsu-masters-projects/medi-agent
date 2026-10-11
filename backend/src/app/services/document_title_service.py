"""Short English and Spanish record titles for the patient's and clinician's lists.

A file name is a poor title ("Morgan-Ellis-01-Hidratacion-es-MX-2026-10-09.pdf"), and it
is in whatever language the uploader used. The worker drafts a descriptive title from
what the document already has: its patient summary or its extracted candidates. It never
re-reads the stored file, never changes clinical data, and a title is a description,
not an instruction, so a rejected or failed draft simply leaves the cleaned file name.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from supabase import Client

from app.adk.background_generation import generate_for_workload
from app.adk.registry import Workload
from app.models.generation import GenerationProviderError
from app.services.clinical_fact_service import ClinicalFactService

logger = logging.getLogger(__name__)

MAX_TITLE_ATTEMPTS = 3
_TITLED_PARSE_STATES = ("completed", "duplicate")
_MISSING_COLUMN_CODES = {"PGRST204", "42703"}
_FILE_NOISE = re.compile(r"\.[a-z0-9]+$|\d{4}[-_]\d{2}[-_]\d{2}|\b(?:en[-_]US|es[-_]MX)\b", re.I)

TITLE_SYSTEM = """You name patient health documents for a records list in a supervised care
app. Write a short, plain title in American English (en-US) and in Mexican Spanish (es-MX)
saying what kind of document it is and its main topic, for example "Hydration
instructions" / "Indicaciones de hidratación" or "Metformin prescription" / "Receta de
metformina".

Rules:
- 2 to 6 words each. No dates, numbers, doses, people's names or clinic names.
- Describe the document; never give advice or instructions.
- Use only the supplied information. Return JSON only."""

TITLE_USER = """Document type: {document_type}
File name words: {file_words}
Patient summary (may be empty): {summary}
Extracted topics (may be empty): {topics}"""


class _Titles(BaseModel):
    en_us: str = Field(max_length=80)
    es_mx: str = Field(max_length=80)


def response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"en_us": {"type": "string"}, "es_mx": {"type": "string"}},
        "required": ["en_us", "es_mx"],
    }


def valid_title(title: str) -> bool:
    """A list title: a few words, no digits (so no doses or dates), no line breaks."""
    words = title.split()
    return 2 <= len(title) <= 60 and 1 <= len(words) <= 8 and not re.search(r"[\d\n]", title)


def _file_words(file_name: str) -> str:
    return " ".join(_FILE_NOISE.sub(" ", file_name).replace("-", " ").replace("_", " ").split())


def _topics(facts: list[dict[str, Any]]) -> list[str]:
    """Names only: a medication's name or an activity's description, never doses."""
    topics: list[str] = []
    for fact in facts:
        value = cast(dict[str, Any], fact.get("value") or {})
        topic = value.get("name") or value.get("label") or value.get("description")
        if isinstance(topic, str) and topic.strip():
            topics.append(re.sub(r"\d.*$", "", topic).strip()[:80])
    return topics[:6]


def _is_missing_column(error: APIError) -> bool:
    message = str(getattr(error, "message", error))
    return str(getattr(error, "code", "")) in _MISSING_COLUMN_CODES and "display_title" in message


class DocumentTitleService:
    def __init__(self, db: Client, *, facts: ClinicalFactService | None = None) -> None:
        self.db = db
        self._facts = facts or ClinicalFactService(db)

    async def fill_missing(self, *, limit: int) -> dict[str, int]:
        counts = {"titles_claimed": 0, "titles_ready": 0, "titles_failed": 0}
        try:
            rows = cast(
                list[dict[str, Any]],
                self.db.table("documents")
                .select(
                    "id, patient_id, file_name, document_type, ai_summary, display_title_attempts"
                )
                .eq("display_title", "{}")
                .lt("display_title_attempts", MAX_TITLE_ATTEMPTS)
                .in_("parse_status", list(_TITLED_PARSE_STATES))
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or [],
            )
        except APIError as error:
            if _is_missing_column(error):
                # The worker image can reach Cloud Run before migration 050.
                return {**counts, "titles_schema_unavailable": 1}
            raise
        for row in rows:
            counts["titles_claimed"] += 1
            titles = await self._draft(row)
            self._record(row, titles)
            counts["titles_ready" if titles else "titles_failed"] += 1
        return counts

    async def _draft(self, row: dict[str, Any]) -> dict[str, str] | None:
        facts: list[dict[str, Any]] = []
        try:
            facts = self._facts.list_facts_for_document(
                UUID(str(row["id"])), UUID(str(row["patient_id"]))
            )
        except Exception:  # noqa: BLE001 - topics only enrich the title
            facts = []
        prompt = TITLE_USER.format(
            document_type=str(row.get("document_type") or "other"),
            file_words=_file_words(str(row.get("file_name") or "")),
            summary=str(row.get("ai_summary") or "")[:1200],
            topics=json.dumps(_topics(facts), ensure_ascii=False),
        )
        try:
            response = await generate_for_workload(
                Workload.EXPLANATION,
                prompt=prompt,
                system_instruction=TITLE_SYSTEM,
                temperature=0,
                response_schema=response_schema(),
            )
            titles = _Titles.model_validate_json(response.text)
        except (GenerationProviderError, PydanticValidationError):
            return None
        english, spanish = titles.en_us.strip(), titles.es_mx.strip()
        if not (valid_title(english) and valid_title(spanish)):
            return None
        return {"en-US": english, "es-MX": spanish}

    def _record(self, row: dict[str, Any], titles: dict[str, str] | None) -> None:
        attempts = int(row.get("display_title_attempts") or 0)
        payload: dict[str, Any] = {"display_title_attempts": attempts + 1}
        if titles:
            payload["display_title"] = titles
        # Compare-and-set on the attempt count so two workers never double count.
        self.db.table("documents").update(payload).eq("id", str(row["id"])).eq(
            "display_title_attempts", attempts
        ).execute()
