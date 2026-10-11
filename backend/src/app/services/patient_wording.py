"""Choose the patient's language for approved medication and activity text.

Approval projects reviewed wording in both languages into ``patient_wording``; the
patient's saved language picks one at read time, so a language switch needs no new
review. Older single-language rows are shown as written, with ``content_locale`` set
when their language is evident so the portal can label them.
"""

from __future__ import annotations

from typing import Any, cast

from app.services.frequency_labels import localized_frequency
from app.utils.localization import detect_locale


def patient_text(
    target_type: str, target: dict[str, Any], locale: str, *, include_dosage: bool = True
) -> dict[str, str | None]:
    """Return ``name``, ``description``, ``frequency`` and ``content_locale``."""
    wording = cast(dict[str, dict[str, str]], target.get("patient_wording") or {}).get(locale)
    raw_frequency = str(target.get("frequency") or "")
    if wording and str(wording.get("title") or "").strip():
        return {
            "name": wording["title"],
            "description": wording.get("instructions") or None,
            "frequency": wording.get("frequency") or raw_frequency,
            "content_locale": locale,
        }
    if target_type == "medication":
        dosage = str(target.get("dosage") or "").strip()
        name = str(target.get("name") or "")
        if include_dosage and dosage:
            name = f"{name} {dosage}"
        description = cast(str | None, target.get("instructions"))
    else:
        name = str(target.get("description") or "")
        description = cast(str | None, target.get("notes"))
    # Medication names carry no language; only the wording around them does.
    evidence = [description or ""] if target_type == "medication" else [name, description or ""]
    return {
        "name": name,
        "description": description,
        "frequency": localized_frequency(raw_frequency, locale) or raw_frequency,
        "content_locale": detect_locale(*evidence, raw_frequency),
    }
