"""Bounded synthetic imports: no hosted DB, OAuth exchange or clinical mutations."""

import json
from copy import deepcopy
from unittest.mock import MagicMock
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import ExternalServiceError, ValidationError
from app.services import fhir_import_limits as limits
from app.services import fhir_import_service as importer
from app.services import smart_launch_service as launch
from app.services.fhir_import_limits import FhirFetchBudget
from app.services.fhir_import_service import FhirImportService
from app.services.smart_launch_service import SmartLaunchService
from tests.unit.services.test_fhir_import_service import Database

ISSUER = "https://sandbox.example/fhir"
URL = ISSUER + "/Observation?patient=synthetic"
HEADERS = {"Authorization": "Bearer synthetic-test-token"}


def service(handler):
    return SmartLaunchService(
        MagicMock(), http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def bundle(*resources, next_url=None):
    value = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": resource} for resource in resources],
    }
    if next_url:
        value["link"] = [{"relation": "next", "url": next_url}]
    return value


def fetch(client, budget=None):
    return client._get_bundle_resources(url=URL, issuer=ISSUER, headers=HEADERS, budget=budget)


def test_relative_query_pagination_retains_resource_path_and_auth():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.headers["authorization"] == HEADERS["Authorization"]
        page = parse_qs(request.url.query.decode()).get("page", ["1"])[0]
        return httpx.Response(
            200,
            json=bundle(
                {"resourceType": "Observation", "id": page},
                next_url="?page=2" if page == "1" else None,
            ),
        )

    client = service(handler)
    assert [row["id"] for row in fetch(client)] == ["1", "2"]
    assert calls == [URL, ISSUER + "/Observation?page=2"]
    client.db.table.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/fhir/Observation",
        "http://sandbox.example/fhir/Observation",
        "/other-app/Observation",
        "/fhir/../other-app/Observation",
        "/fhir/%2e%2e/other-app/Observation",
        "/fhir/%252e%252e/other-app/Observation",
        "//other.example/Observation",
        "/fhir/Observation#fragment",
        "/fhir\\other",
        "/fhir/Observation%00hidden",
        "/fhir/Observation%0aextra",
        "https://[invalid/fhir/Observation",
    ],
)
def test_rejected_next_url_never_receives_the_bearer_header(url):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=bundle(next_url=url))

    client = service(handler)
    with pytest.raises(ExternalServiceError, match="pagination"):
        fetch(client)
    assert calls == [URL]
    client.db.table.assert_not_called()


@pytest.mark.parametrize(
    "url", ["\n/fhir/Observation", "/fhir/Obser\tvation", "/fhir/Observation\x7f"]
)
def test_control_characters_are_rejected_before_url_normalization(url):
    with pytest.raises(ExternalServiceError, match="Invalid pagination"):
        SmartLaunchService._bounded_fhir_url(url, issuer=ISSUER, base=URL)


@pytest.mark.parametrize(
    "links",
    [
        [{"relation": "next"}],
        [{"relation": "next", "url": ""}],
        [{"relation": "next", "url": "?page=2"}, {"relation": "next", "url": "?page=3"}],
    ],
)
def test_invalid_or_ambiguous_next_link_is_not_silently_truncated(links):
    client = service(lambda request: httpx.Response(200, json={**bundle(), "link": links}))
    with pytest.raises(ExternalServiceError, match="Invalid next-page"):
        fetch(client)
    client.db.table.assert_not_called()


def test_cycle_is_rejected_before_repeating_a_request():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=bundle(next_url=URL))

    with pytest.raises(ExternalServiceError, match="cycle"):
        fetch(service(handler))
    assert calls == [URL]


def test_page_limit_is_checked_before_fetching_the_extra_page(monkeypatch):
    monkeypatch.setattr(launch, "MAX_PAGES_PER_QUERY", 2)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=bundle(next_url=f"?page={len(calls) + 1}"))

    with pytest.raises(ExternalServiceError, match="page limit"):
        fetch(service(handler))
    assert len(calls) == 2


def test_global_request_budget_is_shared_by_all_context_queries(monkeypatch):
    monkeypatch.setattr(limits, "MAX_IMPORT_REQUESTS", 2)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"resourceType": "Patient", "id": "synthetic"})

    client = service(handler)
    with pytest.raises(ExternalServiceError, match="request limit"):
        client._fetch_contextual_resources(
            session={"issuer": ISSUER}, token={"access_token": "synthetic", "patient": "synthetic"}
        )
    assert len(calls) == 2
    client.db.table.assert_not_called()


def test_resource_budget_accumulates_across_queries(monkeypatch):
    monkeypatch.setattr(limits, "MAX_IMPORT_RESOURCES", 1)
    client = service(lambda _: httpx.Response(200, json=bundle({"resourceType": "Patient"})))
    budget = FhirFetchBudget()
    assert len(fetch(client, budget)) == 1
    with pytest.raises(ExternalServiceError, match="resource limit"):
        fetch(client, budget)
    client.db.table.assert_not_called()


def test_response_byte_limit_stops_stream_before_json_or_persistence(monkeypatch):
    monkeypatch.setattr(launch, "MAX_RESPONSE_BYTES", 20)
    client = service(lambda _: httpx.Response(200, content=b"x" * 100))
    with pytest.raises(ExternalServiceError, match="Response byte"):
        fetch(client)
    client.db.table.assert_not_called()


def test_import_byte_budget_is_not_reset_between_resource_queries(monkeypatch):
    payload = {"resourceType": "Patient", "id": "synthetic"}
    size = len(json.dumps(payload).encode())
    monkeypatch.setattr(limits, "MAX_IMPORT_BYTES", size + 5)
    client = service(lambda _: httpx.Response(200, content=json.dumps(payload).encode()))
    budget = FhirFetchBudget()
    fetch(client, budget)
    with pytest.raises(ExternalServiceError, match="Import byte"):
        fetch(client, budget)


def test_redirect_is_not_followed_even_with_a_redirecting_client():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://other.example/target"})

    client = service(handler)
    client.http.follow_redirects = True
    with pytest.raises(ExternalServiceError):
        fetch(client)
    assert calls == [URL]


@pytest.mark.parametrize(
    "context",
    [
        {"patient": "synthetic?other=x"},
        {"patient": "synthetic", "encounter": "../other"},
        {"patient": ".."},
        {"patient": "."},
    ],
)
def test_token_resource_id_cannot_inject_paths_or_queries(context):
    client = service(lambda _: pytest.fail("Malformed context must not trigger HTTP"))
    with pytest.raises(ExternalServiceError, match="Malformed resource"):
        client._fetch_contextual_resources(
            session={"issuer": ISSUER}, token={"access_token": "synthetic", **context}
        )


def test_upstream_error_does_not_echo_body_or_credentials():
    client = service(lambda _: httpx.Response(503, text="private provider details"))
    with pytest.raises(ExternalServiceError) as error:
        fetch(client)
    assert "private provider" not in str(error.value)
    assert "synthetic-test-token" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"resourceType": "Bundle", "entry": {}},
        {"resourceType": "Bundle", "link": {}},
        {"resourceType": "Bundle", "entry": [None]},
        {"resourceType": "Bundle", "entry": [{}]},
        {"resourceType": "Bundle", "entry": [{"resource": []}]},
    ],
)
def test_malformed_page_fails_without_database_writes(payload):
    client = service(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(ExternalServiceError):
        fetch(client)
    client.db.table.assert_not_called()


def test_nested_bundle_depth_is_bounded_before_first_candidate_write(monkeypatch):
    monkeypatch.setattr(importer, "MAX_BUNDLE_DEPTH", 2)
    value = {"resourceType": "Patient", "id": "synthetic"}
    for _ in range(3):
        value = bundle(value)
    db = MagicMock()
    with pytest.raises(ValidationError, match="nesting limit"):
        FhirImportService(db).import_resources(
            import_id=uuid4(),
            patient_id=uuid4(),
            actor_id=uuid4(),
            issuer=ISSUER,
            resources=[value],
        )
    db.table.assert_not_called()


@pytest.mark.parametrize("entry", [None, {"resource": "invalid"}])
def test_malformed_nested_entries_fail_before_persistence(entry):
    db = MagicMock()
    with pytest.raises(ValidationError, match="resource objects"):
        FhirImportService(db).import_resources(
            import_id=uuid4(),
            patient_id=uuid4(),
            actor_id=uuid4(),
            issuer=ISSUER,
            resources=[{"resourceType": "Bundle", "type": "collection", "entry": [entry]}],
        )
    db.table.assert_not_called()


@pytest.mark.parametrize(
    "limit_name,limit_value", [("MAX_IMPORT_RESOURCES", 1), ("MAX_IMPORT_BYTES", 20)]
)
def test_direct_import_limits_preflight_the_whole_batch(monkeypatch, limit_name, limit_value):
    monkeypatch.setattr(importer, limit_name, limit_value)
    db = MagicMock()
    with pytest.raises(ValidationError, match="limit exceeded"):
        FhirImportService(db).import_resources(
            import_id=uuid4(),
            patient_id=uuid4(),
            actor_id=uuid4(),
            issuer=ISSUER,
            resources=[
                {"resourceType": "Patient", "id": "one"},
                {"resourceType": "Patient", "id": "two"},
            ],
        )
    db.table.assert_not_called()


def test_source_business_identifiers_are_preserved_without_becoming_editable_facts():
    db = Database()
    resource = {
        "resourceType": "Patient",
        "id": "synthetic",
        "identifier": [
            {"system": "urn:synthetic:MRN", "value": "00AbC", "use": "official"},
            {
                "system": "urn:synthetic:other",
                "value": "00abc",
                "assigner": {"display": "Synthetic clinic"},
            },
        ],
    }
    original = deepcopy(resource)
    result = FhirImportService(db).import_resources(
        import_id=uuid4(), patient_id=uuid4(), actor_id=uuid4(), issuer=ISSUER, resources=[resource]
    )
    assert result["candidate_facts_created"] == 1
    assert db.store["fhir_import_resources"][0]["raw_resource"] == original
    location = db.store["source_provenances"][0]["document_location"]
    assert location["identifiers"] == original["identifier"]
    assert "identifiers" not in db.store["clinical_facts"][0]["value"]
    resource["identifier"][0]["value"] = "changed client object"
    assert location["identifiers"][0]["value"] == "00AbC"
