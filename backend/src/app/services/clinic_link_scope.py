"""The patients a clinician's list shows, and the clinic each one is linked at (CLN-003).

A clinician sees every patient they hold an active care-team link to. The clinic of an item is
the clinic of that clinician's link (``care_teams.clinic_id``), never ``clinicians.clinic_id``.
An optional clinic filter narrows the scope to the links at one clinic; a clinic where the
caller has no active membership gives an empty scope, the same as a clinic with no links, so
nothing reveals whether that clinic exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClinicLinkScope:
    """Patient id -> (clinic id, clinic name) for the links a list may show."""

    links: Mapping[str, tuple[str | None, str | None]] = field(default_factory=dict)
    # Every (patient id, clinic id) link, including a patient's links at several clinics.
    extra_pairs: frozenset[tuple[str, str]] = frozenset()

    @property
    def pairs(self) -> frozenset[tuple[str, str]]:
        own = {(patient, clinic) for patient, (clinic, _) in self.links.items() if clinic}
        return frozenset(own) | self.extra_pairs

    @property
    def patient_ids(self) -> list[str]:
        return list(self.links)

    @property
    def clinic_ids(self) -> list[str]:
        """The clinics of the links in scope (each once), for items that carry their own clinic."""
        return sorted({clinic for _, clinic in self.pairs})

    def __contains__(self, patient_id: object) -> bool:
        return str(patient_id) in self.links

    def tag(self, patient_id: object) -> dict[str, str | None]:
        clinic_id, clinic_name = self.links.get(str(patient_id), (None, None))
        return {"clinic_id": clinic_id, "clinic_name": clinic_name}

    def annotate(self, row: dict[str, Any], key: str = "patient_id") -> dict[str, Any]:
        """Add the link's clinic to an item (in place) and return it."""
        row.update(self.tag(row.get(key)))
        return row

    def keep(self, rows: Iterable[dict[str, Any]], key: str = "patient_id") -> list[dict[str, Any]]:
        """Rows whose patient is in scope, each tagged with its clinic."""
        return [self.annotate(row, key) for row in rows if row.get(key) in self]


def scope_from_links(
    rows: Iterable[Mapping[str, Any]], clinic_id: str | None, allowed: set[str]
) -> ClinicLinkScope:
    """Build a scope from link rows; ``clinic_id`` keeps one clinic, if the caller belongs."""
    wanted = str(clinic_id) if clinic_id is not None else None
    if wanted is not None and wanted not in allowed:
        return ClinicLinkScope()
    links: dict[str, tuple[str | None, str | None]] = {}
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        patient = row.get("patient_id")
        if not patient:
            continue
        clinic = str(row["clinic_id"]) if row.get("clinic_id") else None
        if wanted is not None and clinic != wanted:
            continue
        if clinic:
            pairs.add((str(patient), clinic))
        clinic_row = row.get("clinics")
        name = clinic_row.get("display_name") if isinstance(clinic_row, dict) else None
        links.setdefault(str(patient), (clinic, name))
    return ClinicLinkScope(links, frozenset(pairs))
