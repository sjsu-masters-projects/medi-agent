"""Bounded testimony preview. Record context is never used to answer a question."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from supabase import Client

from app.intake.library import Bundle

RETRIEVAL_VERSION = "symptom-context/1"


def testimony_only(report: dict[str, Any]) -> dict[str, Any]:
    """Clinical consumers get consented testimony, not cached source authorization."""
    content = report.get("confirmed_content")
    if not isinstance(content, dict):
        return report
    return {
        **report,
        "confirmed_content": {key: value for key, value in content.items() if key != "context"},
    }


def summarize(row: dict[str, Any], bundle: Bundle) -> str:
    parts = []
    spanish = row["locale"] == "es-MX"
    labels = (
        {
            "concern": "Preocupación por un producto",
            "name": "Producto",
            "strength": "Concentración",
            "dose": "Dosis",
            "route": "Vía",
            "indication": "Motivo de uso",
            "start": "Inicio",
            "stop": "Suspensión",
            "change": "Cambio",
        }
        if spanish
        else {
            "concern": "Product concern",
            "name": "Product",
            "strength": "Strength",
            "dose": "Dose",
            "route": "Route",
            "indication": "Reason for use",
            "start": "Start",
            "stop": "Stop",
            "change": "Change",
        }
    )

    def display(value: Any) -> str:
        if type(value) is bool:
            return ("Sí" if value else "No") if spanish else ("Yes" if value else "No")
        return str(value)

    for question in bundle.questions:
        answer = row["answers"].get(question.id)
        if not answer:
            continue
        state = answer["state"]
        value = answer.get("value")
        if isinstance(value, dict):
            value = "; ".join(f"{labels[key]}: {display(item)}" for key, item in value.items())
        elif type(value) is bool:
            value = display(value)
        unresolved = (
            ("No sé" if state == "unknown" else "Prefiero no responder")
            if row["locale"] == "es-MX"
            else ("I don’t know" if state == "unknown" else "Prefer not to answer")
        )
        parts.append(
            f"{question.wording[row['locale']]} {value if state == 'answered' else unresolved}"
        )
    return "\n".join(parts)


async def retrieve_context(db: Client, row: dict[str, Any]) -> dict[str, Any]:
    """One purpose-bound RPC selects only evidence for an exact patient-named product."""
    import httpx
    from postgrest.exceptions import APIError

    from app.core.exceptions import ValidationError

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                db.rpc(
                    "symptom_intake_context",
                    {
                        "p_patient_id": row["patient_id"],
                        "p_intake_id": row["id"],
                    },
                ).execute
            ),
            timeout=8,
        )
    except (TimeoutError, OSError, httpx.TransportError, APIError):
        raise ValidationError(
            "Record context unavailable", code="INTAKE_PERSISTENCE_UNAVAILABLE"
        ) from None
    if not isinstance(result.data, dict):
        raise ValidationError("Record context unavailable", code="INTAKE_PERSISTENCE_UNAVAILABLE")
    return cast(dict[str, Any], result.data)


async def verify_context(db: Client, row: dict[str, Any]) -> bool:
    """Read and confirmation recheck exact eligible sources; commit rechecks under locks."""
    saved = (row.get("preview") or {}).get("context", {})
    current = await retrieve_context(db, row)
    return all(saved.get(key) == current.get(key) for key in ("medications", "facts", "excerpts"))
