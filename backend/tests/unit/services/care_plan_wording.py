"""Shared synthetic fixture: an item whose English and Spanish wording was verified."""

from __future__ import annotations

from typing import Any


def verified_wording(
    title: str = "Walk", instructions: str = "Walk 20 minutes", frequency: str = "daily"
) -> dict[str, Any]:
    return {
        "title": title,
        "instructions": instructions,
        "frequency": frequency,
        "source_locale": "en-US",
        "wording": {
            "en-US": {"title": title, "instructions": instructions, "frequency": frequency},
            "es-MX": {
                "title": f"{title} (es)",
                "instructions": f"{instructions} (es)",
                "frequency": f"{frequency} (es)",
            },
        },
        "wording_origin": {"en-US": "source", "es-MX": "ai_draft"},
        "wording_verified": True,
    }
