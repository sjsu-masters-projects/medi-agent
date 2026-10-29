"""Real privileges, locale bounds and document lifecycle for presentation cache 102."""

import json
import os

import pytest

from tests.integration.care_team_plan_harness import TEAM
from tests.integration.test_care_team_records_postgres import document, two_teams

pytest_plugins = ["tests.integration.care_team_plan_harness"]
pytestmark = [
    pytest.mark.timeout(600),
    pytest.mark.skipif(
        os.environ.get("CARE_TEAM_PLANS_TEST_POSTGRES_DOCKER") != "1",
        reason="explicit opt-in disposable Docker PostgreSQL contracts",
    ),
]


def insert(doc, language="en-US", payload=None):
    payload = payload if payload is not None else {"language": language, "sections": []}
    data = json.dumps(payload).replace("'", "''")
    return f"""INSERT INTO document_explanation_presentations
      (document_id,language,source_hash,presentation_version,payload)
      VALUES ('{doc}','{language}','{"a" * 64}',1,'{data}'::jsonb);"""


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_clients_cannot_read_or_write_presentations(sql, role):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    sql("SET ROLE service_role; " + insert(doc))
    assert "permission denied" in sql(
        f"SET ROLE {role}; SELECT * FROM document_explanation_presentations", succeeds=False
    )
    assert "permission denied" in sql(f"SET ROLE {role}; " + insert(doc), succeeds=False)
    assert "permission denied" in sql(
        f"SET ROLE {role}; DELETE FROM document_explanation_presentations", succeeds=False
    )


def test_cache_is_bounded_to_two_locales_and_cascades_on_document_removal(sql):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    sql("SET ROLE service_role; " + insert(doc) + insert(doc, "es-MX"))
    assert sql("SELECT count(*) FROM document_explanation_presentations") == "2"
    assert "duplicate key" in sql("SET ROLE service_role; " + insert(doc), succeeds=False)
    assert "violates check constraint" in sql(
        "SET ROLE service_role; " + insert(doc, "fr-FR"), succeeds=False
    )
    sql(f"DELETE FROM documents WHERE id='{doc}'")
    assert sql("SELECT count(*) FROM document_explanation_presentations") == "0"


@pytest.mark.parametrize(
    "payload", [{}, {"language": "es-MX"}, {"language": "en-US", "text": "x" * 131073}]
)
def test_cache_refuses_missing_or_mismatched_language_and_oversized_payload(sql, payload):
    two_teams(sql)
    doc = document(sql, team=TEAM, review="pending")
    assert "violates check constraint" in sql(
        "SET ROLE service_role; " + insert(doc, payload=payload), succeeds=False
    )
