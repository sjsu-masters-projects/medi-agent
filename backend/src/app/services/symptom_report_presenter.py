"""Shape the database's report card for readers. Pure functions; no I/O, no invented history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.symptom_report_history import (
    ClinicianSymptomReport,
    ReportAnswer,
    ReportEvent,
    ReportProvenance,
    ReportTriage,
    SymptomReportDetail,
    SymptomReportListItem,
    TeamReview,
)

# Row labels in the language used; LOC-001 project-scope interface review recorded October 22.
_LABELS: dict[str, dict[str, str]] = {
    "en-US": {
        "description": "What happened",
        "location": "Where",
        "onset": "When it started",
        "duration": "How long",
        "course": "How it has changed",
        "severity": "Severity (0 to 10)",
        "associated": "Other symptoms",
        "red_flags": "Warning signs",
        "product": "Product involved",
        "concomitant": "Other products",
        "history": "Related history",
        "outcome": "Outcome so far",
    },
    "es-MX": {
        "description": "Qué pasó",
        "location": "Dónde",
        "onset": "Cuándo empezó",
        "duration": "Cuánto tiempo",
        "course": "Cómo ha cambiado",
        "severity": "Intensidad (0 a 10)",
        "associated": "Otros síntomas",
        "red_flags": "Señales de alerta",
        "product": "Producto involucrado",
        "concomitant": "Otros productos",
        "history": "Antecedentes relacionados",
        "outcome": "Resultado hasta ahora",
    },
}
_PRODUCT_LABELS: dict[str, dict[str, str]] = {
    "en-US": {
        "concern": "Product concern",
        "name": "Product",
        "strength": "Strength",
        "dose": "Dose",
        "route": "Route",
        "indication": "Reason for use",
        "start": "Start",
        "stop": "Stop",
        "change": "Change",
    },
    "es-MX": {
        "concern": "Preocupación por un producto",
        "name": "Producto",
        "strength": "Concentración",
        "dose": "Dosis",
        "route": "Vía",
        "indication": "Motivo de uso",
        "start": "Inicio",
        "stop": "Suspensión",
        "change": "Cambio",
    },
}
_UNRESOLVED = {
    "en-US": {"unknown": "I don’t know", "declined": "Prefer not to answer"},
    "es-MX": {"unknown": "No sé", "declined": "Prefiero no responder"},
}
_YES_NO = {"en-US": ("Yes", "No"), "es-MX": ("Sí", "No")}
_ORDER = tuple(_LABELS["en-US"])


def report_locale(card: dict[str, Any]) -> str:
    return "es-MX" if card.get("locale") == "es-MX" else "en-US"


def _scalar(value: Any, locale: str) -> str:
    if isinstance(value, bool):
        return _YES_NO[locale][0 if value else 1]
    return str(value)


def present_answers(card: dict[str, Any]) -> list[ReportAnswer]:
    locale = report_locale(card)
    raw = card.get("answers") or {}
    if not isinstance(raw, dict):
        return []
    rows: list[ReportAnswer] = []
    for key in sorted(raw, key=lambda k: _ORDER.index(k) if k in _ORDER else len(_ORDER)):
        answer = raw[key]
        if not isinstance(answer, dict) or answer.get("state") not in {
            "answered",
            "unknown",
            "declined",
        }:
            continue
        state = answer["state"]
        value = answer.get("value")
        if state != "answered":
            display = _UNRESOLVED[locale][state]
        elif isinstance(value, dict):
            labels = _PRODUCT_LABELS[locale]
            display = "; ".join(
                f"{labels.get(k, k)}: {_scalar(v, locale)}" for k, v in value.items()
            )
        else:
            display = _scalar(value, locale)
        wording = answer.get("wording")
        rows.append(
            ReportAnswer(
                question_id=key,
                label=_LABELS[locale].get(key, key),
                state=state,
                display=display,
                wording=wording if isinstance(wording, str) and wording.strip() else None,
                captured_at=_parse(answer.get("captured_at")),
            )
        )
    return rows


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def build_events(card: dict[str, Any]) -> list[ReportEvent]:
    """Only recorded events: confirmation, the hand-off outcome, a delivered urgent alert, reviews."""
    confirmed = _required(card["confirmed_at"])
    events = [ReportEvent(kind="reported", at=confirmed)]
    handoff = card.get("handoff_state")
    handed = _parse(card.get("handed_off_at"))
    if handoff == "sent" and handed:
        events.append(ReportEvent(kind="shared_with_care_team", at=handed))
    elif handoff == "not_sent":
        events.append(ReportEvent(kind="not_sent_no_care_team", at=confirmed))
    escalation = card.get("escalation")
    if isinstance(escalation, dict) and escalation.get("delivery_state") == "delivered":
        at = _parse(escalation.get("at"))
        if at:
            events.append(ReportEvent(kind="flagged_urgent", at=at))
    for review in card.get("reviews") or []:
        if at := _parse(review.get("reviewed_at")):
            events.append(
                ReportEvent(
                    kind="reviewed",
                    at=at,
                    actor_name=review.get("reviewed_by_name"),
                    team_label=review.get("team_label"),
                )
            )
    return sorted(events, key=lambda event: event.at)


def _required(value: Any) -> datetime:
    parsed = _parse(value)
    if parsed is None:
        raise ValueError("A confirmed report must carry its confirmation time")
    return parsed


def _status(events: list[ReportEvent]) -> str:
    kinds = {event.kind for event in events}
    if "reviewed" in kinds:
        return "reviewed"
    if "shared_with_care_team" in kinds:
        return "shared"
    return "not_sent" if "not_sent_no_care_team" in kinds else "reported"


def _base(card: dict[str, Any]) -> dict[str, Any]:
    events = build_events(card)
    return {
        "id": card["id"],
        "symptom": card["symptom"],
        "severity": card.get("severity"),
        "onset": card.get("onset"),
        "duration": card.get("duration"),
        "confirmed_at": _required(card["confirmed_at"]),
        "locale": report_locale(card),
        "status": _status(events),
        "handoff": card.get("handoff_state")
        if card.get("handoff_state") in {"sent", "not_sent"}
        else "unrecorded",
        "events": events,
    }


def present_list_item(card: dict[str, Any]) -> SymptomReportListItem:
    return SymptomReportListItem(**_base(card))


def present_detail(card: dict[str, Any]) -> SymptomReportDetail:
    return SymptomReportDetail(
        **_base(card),
        body_area=card.get("body_area"),
        timezone=card.get("timezone"),
        answers=present_answers(card),
        summary=card.get("summary"),
    )


def present_clinician(card: dict[str, Any]) -> ClinicianSymptomReport:
    base = present_detail(card).model_dump()
    provenance = card.get("provenance") or {}
    safety = card.get("safety") or {}
    escalation = card.get("escalation") or {}
    reviews = [
        TeamReview(
            care_team_id=item["care_team_id"],
            team_label=item.get("team_label"),
            reviewed_by_name=item.get("reviewed_by_name"),
            reviewed_at=_required(item["reviewed_at"]),
            mine=bool(item.get("mine")),
        )
        for item in card.get("reviews") or []
    ]
    return ClinicianSymptomReport(
        **base,
        patient_id=card["patient_id"],
        flagged_for_adr=bool(card.get("flagged_for_adr")),
        related_medication_name=card.get("related_medication_name"),
        provenance=ReportProvenance(
            report_id=provenance["report_id"],
            intake_id=provenance.get("intake_id"),
            source_message_id=provenance.get("source_message_id"),
            session_id=provenance.get("session_id"),
            schema_version=provenance.get("schema_version"),
            library_version=provenance.get("library_version"),
            submitted_status=provenance.get("submitted_status"),
            confirmed_at=_required(card["confirmed_at"]),
            confirmed_by=provenance.get("confirmed_by"),
            language=report_locale(card),  # type: ignore[arg-type]
            timezone=card.get("timezone"),
            consent_recorded=bool(provenance.get("consent_recorded")),
        ),
        triage=ReportTriage(
            safety_rule_version=safety.get("rule_version"),
            safety_result=safety.get("result"),
            escalation_urgency=escalation.get("urgency"),
            escalation_delivery=escalation.get("delivery_state"),
            escalation_at=_parse(escalation.get("at")),
        ),
        your_care_team_ids=card.get("viewer_care_team_ids") or [],
        reviews=reviews,
        reviewed_by_your_team=any(item.mine for item in reviews),
        acting_care_team_id=card.get("acting_care_team_id"),
        already_reviewed=card.get("already_reviewed"),
    )
