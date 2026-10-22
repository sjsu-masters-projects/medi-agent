"""Real PostgREST embedding/count contract over disposable migration-led PostgreSQL.

Requires cached postgres:16 and postgrest/postgrest:v14.1 images. Both containers
share an isolated network namespace; HTTP goes through its loopback only.
"""

import io
import os
import shlex
import subprocess
import time
from http.client import HTTPResponse
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from postgrest import SyncPostgrestClient

from app.services.external_record_review_service import ExternalRecordReviewService
from tests.integration.test_reconciliation_postgres import (
    FOREIGN,
    PATIENT,
    fact,
    postgres,  # noqa: F401 -- imported container fixture
    source,
    sql,  # noqa: F401 -- own migration fixture, no shared harness edits
)

pytestmark = pytest.mark.skipif(
    os.environ.get("EXTERNAL_REVIEW_TEST_POSTGREST_DOCKER") != "1",
    reason="explicit opt-in disposable PostgreSQL plus PostgREST contract check",
)


def test_actual_nested_source_query_counts_facts_and_excludes_ineligible_evidence(sql):  # noqa: F811
    key = fact(sql)
    document, _ = source(sql, key, document=True)
    sql(f"""UPDATE source_provenances SET captured_at='2026-09-01T12:00:00Z';
      INSERT INTO clinical_facts(patient_id,fact_type,subject_type,value,reconciliation_state)
        SELECT '{PATIENT}',CASE WHEN n%3=0 THEN 'allergy' WHEN n%3=1 THEN 'condition' ELSE 'observation' END,
          'patient','{{}}',CASE WHEN n=1 THEN 'deferred' ELSE 'not_started' END
        FROM generate_series(1,38) n;
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt)
        SELECT f.id,p.id,'Synthetic evidence' FROM clinical_facts f CROSS JOIN source_provenances p
        WHERE f.id <> '{key}';
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt)
        SELECT '{key}',id,'Second citation must not double count' FROM source_provenances;
    """)
    rejected = fact(sql)
    sql(f"UPDATE clinical_facts SET review_state='rejected' WHERE id='{rejected}';")
    source(sql, rejected, document=True)
    withdrawn = fact(sql)
    withdrawn_doc, _ = source(sql, withdrawn, document=True)
    sql(f"UPDATE source_provenances SET withdrawn_at=now() WHERE document_id='{withdrawn_doc}';")
    private = fact(sql)
    sql(f"""INSERT INTO source_provenances(artifact_type,source_system,source_reference)
      VALUES('patient_report','synthetic','private-report');
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt)
      SELECT '{private}',id,'Private testimony must not enter imports work'
      FROM source_provenances WHERE artifact_type='patient_report';""")
    foreign = fact(sql, patient=FOREIGN)
    source(sql, foreign, document=True)
    # A candidate without any cited imported source also must be excluded.
    fact(sql)
    command = sql.command
    docker, container, database = command[0], command[3], command[-1]
    server = "mediagent-external-review-rest-" + uuid4().hex
    subprocess.run(
        [
            docker,
            "run",
            "--detach",
            "--pull=never",
            "--name",
            server,
            "--network=container:" + container,
            "--env",
            f"PGRST_DB_URI=postgresql://postgres@127.0.0.1:5432/{database}",
            "--env",
            "PGRST_DB_ANON_ROLE=service_role",
            "--env",
            "PGRST_DB_SCHEMAS=public",
            "postgrest/postgrest:v14.1",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    try:
        _wait_for_rest(docker, container)
        with (
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: _local_http(docker, container, request)
                )
            ) as http,
            SyncPostgrestClient("http://127.0.0.1:3000", http_client=http) as db,
        ):
            import asyncio

            result = asyncio.run(ExternalRecordReviewService(db)._patient(PATIENT))
        assert result["pending_count"] == 39
        assert result["inspected_candidates"] == 39
        assert result["source_times_complete"] is True
        assert result["oldest_source_captured_at"].isoformat() == "2026-09-01T12:00:00+00:00"
        assert sql(f"SELECT count(*) FROM documents WHERE id='{document}';") == "1"
    finally:
        subprocess.run(
            [docker, "rm", "--force", server], check=True, capture_output=True, timeout=15
        )


def _wait_for_rest(docker, container):
    for _ in range(50):
        result = subprocess.run(
            [docker, "exec", container, "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/3000"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return
        time.sleep(0.1)
    pytest.fail("Disposable PostgREST did not become ready")


def _local_http(docker, container, request):
    wire = f"GET {request.url.raw_path.decode()} HTTP/1.1\r\nHost: localhost\r\nPrefer: count=exact\r\nConnection: close\r\n\r\n"
    result = subprocess.run(
        [
            docker,
            "exec",
            container,
            "bash",
            "-c",
            "exec 3<>/dev/tcp/127.0.0.1/3000; printf '%s' " + shlex.quote(wire) + " >&3; cat <&3",
        ],
        capture_output=True,
        check=True,
        timeout=15,
    )
    response = HTTPResponse(SimpleNamespace(makefile=lambda *_: io.BytesIO(result.stdout)))
    response.begin()
    return httpx.Response(
        response.status, headers=dict(response.getheaders()), content=response.read()
    )
