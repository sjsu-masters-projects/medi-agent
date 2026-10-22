"""Read business identifiers as source metadata, never local identity authority."""

from copy import deepcopy
from typing import Any


def source_identifiers(resource: dict[str, Any]) -> dict[str, Any]:
    """Normalize cardinality without changing case, whitespace or leading zeroes."""
    identifiers = resource.get("identifier", [])
    if isinstance(identifiers, dict):  # Bundle.identifier has cardinality 0..1.
        identifiers = [identifiers]
    result = {
        "identifiers": deepcopy(identifiers) if isinstance(identifiers, list) else [],
        "master_identifier": deepcopy(resource.get("masterIdentifier")),
    }
    return result
