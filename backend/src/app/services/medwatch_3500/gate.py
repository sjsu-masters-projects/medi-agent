"""The single Form 3500 approval gate.

``approval_issues`` is pure and is the one rule used for the draft's missing-item list,
the preview and approval itself, always on the stored revision. An empty list means the
draft may be approved.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.medwatch_form_3500 import GateIssueCode, MedWatchFormDataV2, MedWatchGateIssue
from app.services.medwatch_3500.identifier import PatientIdentity, identifier_violations


@dataclass(frozen=True)
class GateContext:
    """Facts the gate needs beyond the form itself."""

    patient: PatientIdentity
    non_serious_attested: bool = False


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def approval_issues(form: MedWatchFormDataV2, ctx: GateContext) -> list[MedWatchGateIssue]:
    """Every item that blocks approval, in form order."""
    a, b, g = form.section_a, form.section_b, form.section_g
    issues: list[tuple[str, GateIssueCode]] = []
    if _blank(a.identifier):
        issues.append(("section_a.identifier", "identifier_missing"))
    elif identifier_violations(a.identifier, ctx.patient):
        issues.append(("section_a.identifier", "identifier_identifies"))
    if not b.report_types:
        issues.append(("section_b.report_types", "report_type_missing"))
    if not b.outcomes and not ctx.non_serious_attested:
        issues.append(("section_b.outcomes", "non_serious_attestation_required"))
    if "death" in b.outcomes and b.death_date is None:
        issues.append(("section_b.death_date", "death_date_missing"))
    if b.event_date is None:
        issues.append(("section_b.event_date", "event_date_missing"))
    elif not b.event_date_confirmed:
        issues.append(("section_b.event_date", "event_date_unconfirmed"))
    if _blank(b.narrative):
        issues.append(("section_b.narrative", "narrative_missing"))
    if _blank(form.section_d.product_1.name):
        issues.append(("section_d.product_1.name", "product_name_missing"))
    if _blank(g.first_name):
        issues.append(("section_g.first_name", "reporter_first_name_missing"))
    if _blank(g.last_name):
        issues.append(("section_g.last_name", "reporter_last_name_missing"))
    if _blank(g.phone) and _blank(g.email):
        issues.append(("section_g.email", "reporter_contact_missing"))
    if g.health_professional is None:
        issues.append(("section_g.health_professional", "health_professional_missing"))
    if g.occupation is None:
        issues.append(("section_g.occupation", "occupation_missing"))
    if _blank(form.mediagent_review.reportability_rationale):
        issues.append(
            ("mediagent_review.reportability_rationale", "reportability_rationale_missing")
        )
    return [MedWatchGateIssue(path=path, code=code) for path, code in issues]
