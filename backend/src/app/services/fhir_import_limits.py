"""Application limits for synthetic FHIR import; not FHIR conformance limits."""

from dataclasses import dataclass

from app.core.exceptions import ExternalServiceError

MAX_IMPORT_RESOURCES = 1000
MAX_IMPORT_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_DEPTH = 8
MAX_PAGES_PER_QUERY = 20
MAX_IMPORT_REQUESTS = 50


@dataclass
class FhirFetchBudget:
    """One shared budget for every resource query in a launch, not per page."""

    requests: int = 0
    bytes_read: int = 0
    resources: int = 0

    def request(self) -> None:
        self.requests += 1
        if self.requests > MAX_IMPORT_REQUESTS:
            raise ExternalServiceError("FHIR resource fetch", "Import request limit exceeded")

    def consume(self, size: int) -> None:
        self.bytes_read += size
        if self.bytes_read > MAX_IMPORT_BYTES:
            raise ExternalServiceError("FHIR resource fetch", "Import byte limit exceeded")

    def add_resources(self, count: int) -> None:
        self.resources += count
        if self.resources > MAX_IMPORT_RESOURCES:
            raise ExternalServiceError("FHIR resource fetch", "Import resource limit exceeded")
