"""REC lifecycle contracts against real migrations in offline PostgreSQL 16.

Opt in with NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER=1. Only platform auth
objects and fictional evidence are bootstrapped; application objects are real.
The container lifecycle belongs to the shared harness, which this suite imports.
"""

from __future__ import annotations

import json
import os
import subprocess
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.reconciliation import ReconciliationDecisionRequest
from app.services.clinical_fact_service import ClinicalFactService
from app.services.clinical_reconciliation_service import ClinicalReconciliationService
from tests.integration.reconciliation_postgres_adapter import PostgresDatabase, literal
from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    FOREIGN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    postgres,  # noqa: F401 -- shared container fixture, never modified here
)

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check",
)


@pytest.fixture
def sql(postgres):  # noqa: F811 -- pytest fixture imported from the shared harness
    database = "reconciliation_" + uuid4().hex
    subprocess.run(
        postgres,
        input=f"CREATE DATABASE {database};",
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    command = postgres + ["-d", database]

    def execute(statement, *, succeeds=True):
        result = subprocess.run(
            command,
            input="SET statement_timeout='12s';\n" + statement,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert (result.returncode == 0) is succeeds, result.stderr
        return result.stdout.strip() if succeeds else result.stderr

    execute.command = command

    execute("""CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
      CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;""")
    for name in (
        "001_initial_schema.sql",
        "002_rls_policies.sql",
        "005_document_parse_tracking.sql",
        "006_care_team_invite_compat.sql",
        "007_clinic_identity_foundation.sql",
        "012_document_review_queue.sql",
        "013_cron_scheduler_foundation.sql",
        "014_patient_timezones_and_reminder_schedules.sql",
        "017_clinical_facts_provenance.sql",
        "018_smart_fhir_imports.sql",
        "022_grant_service_role_seed_access.sql",
        "029_safe_external_record_reconciliation.sql",
        "030_audited_fhir_candidate_reprojection.sql",
        "031_fix_fhir_candidate_reprojection_source_version.sql",
        "032_allow_audited_legacy_fhir_provenance_reprojection.sql",
    ):
        execute((MIGRATIONS / name).read_text())
    execute(
        MIGRATIONS.joinpath("020_harden_database_security.sql")
        .read_text()
        .split("-- Public helper functions remain")[0]
    )
    execute(
        MIGRATIONS.parents[3].joinpath("tests/integration/notification_centre_seed.sql").read_text()
    )
    try:
        yield execute
    finally:
        subprocess.run(
            postgres,
            input=f"DROP DATABASE {database} WITH (FORCE);",
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        )


def rows(sql, table):
    return json.loads(
        sql(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id), '[]') FROM {table} t;")
    )


def rpc(sql, name, args, *, role="service_role", succeeds=True):
    result = sql(
        f"SET ROLE {role}; SELECT {name}({','.join(literal(v) for v in args)});",
        succeeds=succeeds,
    )
    return json.loads(result) if succeeds else result


def fact(sql, *, kind="medication", value=None, patient=PATIENT, version="v1"):
    key = str(uuid4())
    value = (
        value
        if value is not None
        else {"name": "Synthetic medicine", "dosage": "10 mg", "frequency": "daily"}
    )
    sql(f"""INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type,value,external_source_version)
      VALUES('{key}','{patient}','{kind}','{kind}',{literal(value)},{literal(version)});
      INSERT INTO clinical_fact_audit_events(fact_id,actor_id,event_type)
      VALUES('{key}','{CLINICIAN}','created');""")
    return key


def decide(
    sql,
    key,
    decision="add",
    *,
    target=None,
    patch=None,
    selected=None,
    actor=CLINICIAN,
    token=None,
    note=None,
    succeeds=True,
    role="service_role",
):
    patch = (
        patch
        if patch is not None
        else {"name": "Synthetic medicine", "dosage": "10 mg", "frequency": "daily"}
    )
    return rpc(
        sql,
        "apply_clinical_fact_reconciliation",
        [
            key,
            actor,
            decision,
            target,
            patch,
            selected if selected is not None else sorted(patch),
            note,
            token or str(uuid4()),
        ],
        succeeds=succeeds,
        role=role,
    )


def source(sql, key, *, document=False, version="v1"):
    source_id, provenance_id, resource_id = (str(uuid4()) for _ in range(3))
    if document:
        sql(f"""INSERT INTO documents(id,patient_id,uploaded_by,uploaded_by_role,document_type,
          file_name,file_url,file_size_bytes,review_status) VALUES('{source_id}','{PATIENT}',
          '{PATIENT}','patient','other','synthetic.pdf','synthetic',10,'pending');""")
        reference = f"documents/{source_id}"
    else:
        sql(f"""INSERT INTO fhir_imports(id,clinician_id,patient_id,issuer,external_patient_id)
          VALUES('{source_id}','{CLINICIAN}','{PATIENT}','https://synthetic.invalid/fhir','external-one');
          INSERT INTO fhir_import_resources(id,import_id,issuer,resource_type,external_resource_id,
          version_id,dedupe_key,content_hash,raw_resource) VALUES('{resource_id}','{source_id}',
          'https://synthetic.invalid/fhir','MedicationStatement','med-one',{literal(version)},
          '{resource_id}','synthetic-hash','{{"resourceType":"MedicationStatement","id":"med-one"}}');""")
        reference = f"fhir_import_resources/{resource_id}"
    sql(f"""INSERT INTO source_provenances(id,artifact_type,source_system,source_reference,document_id)
      VALUES('{provenance_id}','{"document" if document else "fhir_resource"}','synthetic',
      '{reference}',{literal(source_id if document else None)});
      INSERT INTO evidence_citations(fact_id,provenance_id,excerpt,location)
      VALUES('{key}','{provenance_id}','Synthetic medicine 10 mg daily','{{"page":1}}');""")
    return source_id, resource_id


def reproject(
    sql,
    key,
    resource,
    *,
    token=None,
    candidate_version="v1",
    version="v1",
    content_hash="synthetic-hash",
    actor=CLINICIAN,
    value=None,
    succeeds=True,
    role="service_role",
):
    return rpc(
        sql,
        "apply_pending_fhir_candidate_reprojection_v2",
        [
            key,
            actor,
            "synthetic-mapper/2",
            candidate_version,
            resource,
            version,
            content_hash,
            value
            if value is not None
            else {"name": "Synthetic medicine", "dosage": "20 mg", "frequency": "daily"},
            token or str(uuid4()),
        ],
        succeeds=succeeds,
        role=role,
    )


def protected_history(sql):
    medication = str(uuid4())
    sql(f"""INSERT INTO medications(id,patient_id,name,dosage,frequency,instructions)
      VALUES('{medication}','{PATIENT}','Unrelated medicine','5 mg','daily','Retain');
      INSERT INTO reminder_schedules(patient_id,target_type,target_id,timezone,times_of_day)
      VALUES('{PATIENT}','medication','{medication}','America/Los_Angeles','["09:00"]');
      INSERT INTO adherence_logs(patient_id,target_type,target_id,status,notes)
      VALUES('{PATIENT}','medication','{medication}','taken','Synthetic history');""")
    # Include unrelated evidence/audit, not only an empty canonical list.
    fact(sql, kind="condition", value={"name": "Unrelated evidence"})
    return medication, {
        table: rows(sql, table)
        for table in (
            "medications",
            "reminder_schedules",
            "adherence_logs",
            "clinical_facts",
            "clinical_fact_audit_events",
        )
    }


def assert_history(sql, before, *, changed_medication=None):
    for table, original in before.items():
        current = {row["id"]: row for row in rows(sql, table)}
        for row in original:
            if table == "medications" and row["id"] == changed_medication:
                continue
            assert current[row["id"]] == row
        if table in {"reminder_schedules", "adherence_logs"}:
            assert rows(sql, table) == original


def test_add_selected_update_replay_and_append_only_history(sql):
    local, before = protected_history(sql)
    key = fact(sql)
    token = str(uuid4())
    result = decide(sql, key, token=token)
    assert result["replayed"] is False
    assert decide(sql, key, token=token)["event_id"] == result["event_id"]
    assert decide(sql, key, token=token)["replayed"] is True
    assert len(rows(sql, "medications")) == 2
    event = rows(sql, "clinical_fact_reconciliation_events")[0]
    assert event["candidate_snapshot"] == {
        "name": "Synthetic medicine",
        "dosage": "10 mg",
        "frequency": "daily",
    }
    assert event["target_before"] is None
    assert event["target_after"]["id"] == result["target_id"]
    assert event["source_version"] == "v1"
    assert "append-only" in sql(
        "UPDATE clinical_fact_reconciliation_events SET note='rewrite';", succeeds=False
    )
    update = fact(sql, value={"name": "Do not copy", "dosage": "20 mg", "frequency": "weekly"})
    old = next(row for row in rows(sql, "medications") if row["id"] == local)
    patched = decide(sql, update, "update", target=local, patch={"dosage": "20 mg"})
    assert patched["target_before"] == old
    assert patched["target_after"] == {**old, "dosage": "20 mg"}
    assert_history(sql, before, changed_medication=local)
    assert "only pending" in decide(sql, key, succeeds=False)
    assert "another reconciliation" in decide(sql, update, token=token, succeeds=False)


@pytest.mark.parametrize(
    "decision,state,review",
    [
        ("keep_existing", "kept_existing", "approved"),
        ("defer", "deferred", "pending_review"),
        ("reject", "rejected", "rejected"),
        ("mark_reviewed", "reviewed_evidence", "approved"),
    ],
)
def test_nonprojecting_decisions_and_deferred_resume(sql, decision, state, review):
    _, before = protected_history(sql)
    key = fact(sql, kind="observation" if decision == "mark_reviewed" else "medication")
    result = decide(sql, key, decision, patch={}, note="Synthetic clinician decision")
    saved = next(row for row in rows(sql, "clinical_facts") if row["id"] == key)
    assert (saved["reconciliation_state"], saved["review_state"]) == (state, review)
    assert result["target_after"] is None
    assert_history(sql, before)
    assert rows(sql, "medications") == before["medications"]
    if decision == "defer":
        decide(sql, key)
        assert len(rows(sql, "clinical_fact_reconciliation_events")) == 2


@pytest.mark.parametrize(
    "failure",
    [
        "foreign_target",
        "foreign_fact",
        "inactive",
        "selection",
        "invalid_route",
        "evidence_only",
        "missing_note",
    ],
)
def test_failed_decision_is_atomic(sql, failure):
    _, before = protected_history(sql)
    key = fact(
        sql,
        patient=FOREIGN if failure == "foreign_fact" else PATIENT,
        kind="observation" if failure == "evidence_only" else "medication",
    )
    args = {}
    expected = "not assigned"
    if failure == "foreign_target":
        target = str(uuid4())
        sql(
            f"INSERT INTO medications(id,patient_id,name,dosage,frequency) VALUES('{target}','{FOREIGN}','Foreign','1 mg','daily');"
        )
        args = {"decision": "update", "target": target}
        expected = "target not found"
    elif failure == "inactive":
        sql("UPDATE care_teams SET status='inactive';")
    elif failure == "selection":
        args, expected = {"selected": []}, "explicitly selected"
    elif failure == "invalid_route":
        args, expected = (
            {
                "patch": {
                    "name": "Synthetic",
                    "dosage": "1 mg",
                    "frequency": "daily",
                    "route": "not-a-route",
                }
            },
            "invalid input value",
        )
    elif failure == "evidence_only":
        expected = "cannot modify"
    elif failure == "missing_note":
        args, expected = {"decision": "reject"}, "note is required"
    snapshots = {
        table: rows(sql, table)
        for table in (
            "clinical_facts",
            "clinical_fact_audit_events",
            "clinical_fact_reconciliation_events",
            "medications",
        )
    }
    assert expected in decide(sql, key, succeeds=False, **args)
    for table, snapshot in snapshots.items():
        assert rows(sql, table) == snapshot
    assert_history(sql, before)


@pytest.mark.parametrize(
    "kind,patch,table",
    [
        ("condition", {"name": "Synthetic condition", "icd10_code": "Z00.0"}, "conditions"),
        ("allergy", {"allergen": "Synthetic allergen", "reaction": "rash"}, "allergies"),
    ],
)
def test_other_projectable_types_keep_absent_fields_unknown(sql, kind, patch, table):
    key = fact(sql, kind=kind, value=patch)
    result = decide(sql, key, patch=patch)
    assert result["target_after"]["id"] == rows(sql, table)[0]["id"]
    if kind == "allergy":
        assert rows(sql, table)[0]["severity"] == "unknown"


@pytest.mark.parametrize("document", [False, True])
@pytest.mark.parametrize("decision", [None, "add", "keep_existing", "defer", "reject"])
def test_source_withdrawal_removes_only_untouched_evidence(sql, document, decision):
    _, before = protected_history(sql)
    key = fact(sql)
    imported, _ = source(sql, key, document=document)
    if decision:
        decide(sql, key, decision, note="Retain decision")
    truth = rows(sql, "medications")
    events = rows(sql, "clinical_fact_reconciliation_events")
    result = rpc(
        sql,
        "withdraw_unapplied_document_source" if document else "withdraw_unapplied_fhir_import",
        [imported, PATIENT, CLINICIAN],
    )
    assert result["can_delete"] is (decision is None)
    assert rows(sql, "medications") == truth
    assert rows(sql, "clinical_fact_reconciliation_events") == events
    remaining = [row for row in rows(sql, "clinical_facts") if row["id"] == key]
    if decision:
        assert remaining[0]["reconciliation_state"] == "source_withdrawn"
        assert remaining[0]["source_withdrawn_at"]
        assert rows(sql, "source_provenances")[0]["withdrawn_at"]
        assert rows(sql, "evidence_citations")
        assert any(
            row["event_type"] == "source_withdrawn"
            for row in rows(sql, "clinical_fact_audit_events")
        )
    else:
        assert not remaining
        assert not rows(sql, "source_provenances")
        assert not rows(sql, "evidence_citations")
    assert_history(sql, before)


def test_reprojection_legacy_source_replay_audit_and_withdrawal(sql):
    _, before = protected_history(sql)
    key = fact(sql, version="legacy-marker")
    imported, resource = source(sql, key, version=None)
    raw = rows(sql, "fhir_import_resources")
    token = str(uuid4())
    args = {"candidate_version": "legacy-marker", "version": "synthetic-hash", "token": token}
    result = reproject(sql, key, resource, **args)
    assert result["replayed"] is False
    assert reproject(sql, key, resource, **args) == {**result, "replayed": True}
    revision = rows(sql, "clinical_fact_mapping_revisions")[0]
    assert revision["prior_value"]["dosage"] == "10 mg"
    assert revision["projected_value"]["dosage"] == "20 mg"
    assert revision["source_version"] == "synthetic-hash"
    audit = next(
        row for row in rows(sql, "clinical_fact_audit_events") if row["event_type"] == "reprojected"
    )
    assert audit["event_data"]["candidate_source_version"] == "legacy-marker"
    assert audit["event_data"]["source_resource_id"] == resource
    assert rows(sql, "fhir_import_resources") == raw
    assert "append-only" in sql("DELETE FROM clinical_fact_mapping_revisions;", succeeds=False)
    assert (
        rpc(sql, "withdraw_unapplied_fhir_import", [imported, PATIENT, CLINICIAN])["can_delete"]
        is False
    )
    assert rows(sql, "clinical_fact_mapping_revisions") == [revision]
    assert rows(sql, "fhir_import_resources") == raw
    assert rows(sql, "medications") == before["medications"]
    assert_history(sql, before)


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("candidate", "candidate source version changed"),
        ("version", "stored FHIR source changed"),
        ("hash", "stored FHIR source changed"),
        ("resource", "does not directly cite"),
        ("actor", "not assigned"),
        ("corrected", "clinician-touched"),
        ("deferred", "only untouched pending"),
    ],
)
def test_reprojection_rechecks_dry_run_and_review_eligibility(sql, failure, expected):
    key = fact(sql)
    _, resource = source(sql, key)
    args = {}
    if failure == "candidate":
        args["candidate_version"] = "stale"
    elif failure == "version":
        args["version"] = "stale"
    elif failure == "hash":
        args["content_hash"] = "stale"
    elif failure == "resource":
        resource = source(sql, fact(sql))[1]
    elif failure == "actor":
        args["actor"] = OTHER
    elif failure == "corrected":
        sql(
            f"INSERT INTO clinical_fact_audit_events(fact_id,actor_id,event_type) VALUES('{key}','{CLINICIAN}','corrected');"
        )
    elif failure == "deferred":
        decide(sql, key, "defer", note="Needs review")
    snapshot = rows(sql, "clinical_facts")
    assert expected in reproject(sql, key, resource, succeeds=False, **args)
    assert rows(sql, "clinical_facts") == snapshot
    assert not rows(sql, "clinical_fact_mapping_revisions")


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_invoke_lifecycle_rpcs(sql, role):
    key = fact(sql)
    imported, resource = source(sql, key)
    assert "permission denied" in decide(sql, key, role=role, succeeds=False)
    assert "permission denied" in reproject(sql, key, resource, role=role, succeeds=False)
    for name in ("withdraw_unapplied_document_source", "withdraw_unapplied_fhir_import"):
        assert "permission denied" in rpc(
            sql, name, [imported, PATIENT, CLINICIAN], role=role, succeeds=False
        )
    assert not rows(sql, "clinical_fact_reconciliation_events")
    assert not rows(sql, "clinical_fact_mapping_revisions")


def service_decision(sql, key, *, request=None, patient=PATIENT):
    service = ClinicalReconciliationService(PostgresDatabase(sql))
    return service.decide(
        fact_id=UUID(key),
        patient_id=UUID(patient),
        actor_id=UUID(CLINICIAN),
        request=request or ReconciliationDecisionRequest(decision="add", idempotency_key=uuid4()),
    )


def test_service_requires_identity_confirmation_then_replays_committed_result(sql):
    key = fact(sql)
    imported, _ = source(sql, key)
    with pytest.raises(ValidationError, match="Confirm the external patient identity"):
        service_decision(sql, key)
    assert not rows(sql, "medications")
    assert not rows(sql, "clinical_fact_reconciliation_events")
    binding = str(uuid4())
    sql(f"""INSERT INTO external_patient_bindings(id,issuer,external_patient_id,patient_id,confirmed_by)
      VALUES('{binding}','https://synthetic.invalid/fhir','external-one','{PATIENT}','{CLINICIAN}');
      UPDATE fhir_imports SET external_patient_binding_id='{binding}',identity_confirmed_at=now()
      WHERE id='{imported}';""")
    request = ReconciliationDecisionRequest(decision="add", idempotency_key=uuid4())
    result = service_decision(sql, key, request=request)
    snapshot = {
        table: rows(sql, table)
        for table in (
            "medications",
            "clinical_facts",
            "clinical_fact_reconciliation_events",
            "clinical_fact_audit_events",
        )
    }
    assert service_decision(sql, key, request=request) == {**result, "replayed": True}
    for table, original in snapshot.items():
        assert rows(sql, table) == original
    changed = ReconciliationDecisionRequest(
        decision="reject", note="Different decision", idempotency_key=request.idempotency_key
    )
    with pytest.raises(ValidationError, match="another reconciliation"):
        service_decision(sql, key, request=changed)
    with pytest.raises(NotFoundError):
        service_decision(sql, key, request=request, patient=FOREIGN)


def test_binding_uniqueness_prevents_external_identity_reassignment(sql):
    sql(f"""INSERT INTO external_patient_bindings(issuer,external_patient_id,patient_id,confirmed_by)
      VALUES('https://synthetic.invalid/fhir','external-one','{PATIENT}','{CLINICIAN}');""")
    error = sql(
        f"""SET ROLE service_role;
      INSERT INTO external_patient_bindings(issuer,external_patient_id,patient_id,confirmed_by)
      VALUES('https://synthetic.invalid/fhir','external-one','{FOREIGN}','{CLINICIAN}');""",
        succeeds=False,
    )
    assert "duplicate key" in error
    assert len(rows(sql, "external_patient_bindings")) == 1


def test_revoked_assignment_blocks_saved_replay_without_snapshot_or_mutation(sql):
    local, _ = protected_history(sql)
    key = fact(sql)
    source(sql, key, document=True)
    request = ReconciliationDecisionRequest(
        decision="update",
        target_id=UUID(local),
        selected_fields=["dosage"],
        note="Reviewed dose",
        idempotency_key=uuid4(),
    )
    service_decision(sql, key, request=request)
    assert service_decision(sql, key, request=request)["replayed"] is True
    sql("UPDATE care_teams SET status='inactive';")
    snapshot = {
        table: rows(sql, table)
        for table in (
            "medications",
            "reminder_schedules",
            "adherence_logs",
            "clinical_facts",
            "clinical_fact_reconciliation_events",
            "clinical_fact_audit_events",
            "source_provenances",
            "evidence_citations",
        )
    }
    attempts = [
        request,
        request.model_copy(update={"selected_fields": ["frequency"]}),
        request.model_copy(update={"note": "Changed note"}),
        ReconciliationDecisionRequest(
            decision="reject", note="Reviewed dose", idempotency_key=request.idempotency_key
        ),
    ]
    for attempt in attempts:
        before = attempt.model_dump(mode="json")
        with pytest.raises(AuthorizationError, match="not assigned") as denied:
            service_decision(sql, key, request=attempt)
        assert denied.value.reason_code == "NO_CARE_TEAM_ASSIGNMENT"
        assert not hasattr(denied.value, "target_before")
        assert not hasattr(denied.value, "target_after")
        assert attempt.model_dump(mode="json") == before
    for table, original in snapshot.items():
        assert rows(sql, table) == original


@pytest.mark.parametrize("allergen", ["NKDA", "No known drug allergies", "Sin alergias conocidas"])
def test_absence_of_allergy_is_reviewable_evidence_without_positive_allergen(sql, allergen):
    key = fact(sql, kind="allergy", value={"allergen": allergen})
    service = ClinicalReconciliationService(PostgresDatabase(sql))
    preview = service.preview(fact_id=UUID(key), patient_id=UUID(PATIENT))
    assert preview["projectable"] is False
    assert preview["candidate_fields"] == {}
    with pytest.raises(ValidationError, match="evidence-only"):
        service_decision(sql, key)
    service_decision(
        sql,
        key,
        request=ReconciliationDecisionRequest(decision="mark_reviewed", idempotency_key=uuid4()),
    )
    assert rows(sql, "allergies") == []
    saved = rows(sql, "clinical_facts")[0]
    assert saved["value"] == {"allergen": allergen}
    assert saved["reconciliation_state"] == "reviewed_evidence"


def test_correction_preserves_source_and_resets_review_before_selected_reconciliation(sql):
    _, before = protected_history(sql)
    key = fact(sql)
    source(sql, key, document=True)
    citations = rows(sql, "evidence_citations")
    provenance = rows(sql, "source_provenances")
    original = next(row for row in rows(sql, "clinical_facts") if row["id"] == key)
    sql(
        f"UPDATE clinical_facts SET reviewed_by='{CLINICIAN}',reviewed_at=now(),review_note='Old draft note' WHERE id='{key}';"
    )
    service = ClinicalFactService(PostgresDatabase(sql))
    correction = {"name": "Corrected synthetic medicine", "dosage": "20 mg", "frequency": "daily"}
    result = service.correct(
        UUID(key),
        UUID(PATIENT),
        actor_id=UUID(CLINICIAN),
        value=correction,
        note="Corrected from cited page",
    )
    assert result["review_state"] == "pending_review"
    assert result["reviewed_by"] is result["reviewed_at"] is result["review_note"] is None
    audit = next(
        row for row in rows(sql, "clinical_fact_audit_events") if row["event_type"] == "corrected"
    )
    assert audit["event_data"] == {
        "before": original["value"],
        "after": correction,
        "note": "Corrected from cited page",
    }
    assert rows(sql, "evidence_citations") == citations
    assert rows(sql, "source_provenances") == provenance
    service_decision(sql, key)
    assert rows(sql, "clinical_fact_reconciliation_events")[0]["candidate_snapshot"] == correction
    with pytest.raises(ValidationError, match="Only pending"):
        service.correct(
            UUID(key),
            UUID(PATIENT),
            actor_id=UUID(CLINICIAN),
            value={"name": "Late rewrite"},
            note="Too late",
        )
    assert_history(sql, before)


@pytest.mark.parametrize(
    "migration,version",
    [
        ("030_audited_fhir_candidate_reprojection.sql", "v1"),
        ("031_fix_fhir_candidate_reprojection_source_version.sql", None),
    ],
)
def test_original_reprojection_contract_and_hash_fallback_before_v2(sql, migration, version):
    # Exercise each historical callable body, then restore the actual 032 privilege
    # boundary. Each test owns a disposable database; no migration bytes change.
    sql((MIGRATIONS / migration).read_text())
    expected_version = version or "synthetic-hash"
    key = fact(sql, version=expected_version)
    source(sql, key, version=version)
    result = rpc(
        sql,
        "apply_pending_fhir_candidate_reprojection",
        [
            key,
            CLINICIAN,
            "synthetic-mapper/2",
            expected_version,
            {"name": "Updated display"},
            str(uuid4()),
        ],
    )
    assert result["replayed"] is False
    assert rows(sql, "clinical_fact_mapping_revisions")[0]["source_version"] == expected_version
    assert not rows(sql, "medications")
    sql(
        "DROP FUNCTION apply_pending_fhir_candidate_reprojection_v2(uuid,uuid,text,text,uuid,text,text,jsonb,uuid);"
    )
    sql((MIGRATIONS / "032_allow_audited_legacy_fhir_provenance_reprojection.sql").read_text())
    assert (
        sql(
            "SELECT has_function_privilege('service_role', 'apply_pending_fhir_candidate_reprojection(uuid,uuid,text,text,jsonb,uuid)', 'execute');"
        )
        == "f"
    )


def test_document_retry_is_authorized_bounded_and_preserves_existing_evidence(sql):
    for migration in ("034_document_ingestion_safety.sql", "036_document_ingestion_worker.sql"):
        sql((MIGRATIONS / migration).read_text())
    _, before = protected_history(sql)
    key = fact(sql)
    document, _ = source(sql, key, document=True)
    sql(
        f"UPDATE documents SET parse_status='failed',parse_attempts=1,parse_failure_code='provider_unavailable' WHERE id='{document}';"
    )
    evidence = {
        table: rows(sql, table)
        for table in (
            "clinical_facts",
            "source_provenances",
            "evidence_citations",
            "clinical_fact_audit_events",
        )
    }
    for patient, actor, expected in (
        (FOREIGN, CLINICIAN, "not found for patient"),
        (PATIENT, OTHER, "not assigned"),
    ):
        assert expected in rpc(
            sql, "enqueue_document_ingestion_retry", [document, patient, actor], succeeds=False
        )
    assert (
        rpc(sql, "enqueue_document_ingestion_retry", [document, PATIENT, CLINICIAN])["status"]
        == "pending"
    )
    assert "not eligible" in rpc(
        sql, "enqueue_document_ingestion_retry", [document, PATIENT, CLINICIAN], succeeds=False
    )
    attempt = rpc(sql, "claim_document_ingestion", [document, PATIENT, CLINICIAN, "false"])
    assert attempt["attempt"] == 2
    assert "already processing" in rpc(
        sql, "claim_document_ingestion", [document, PATIENT, CLINICIAN, "false"], succeeds=False
    )
    sql(f"UPDATE documents SET parse_status='failed',parse_attempts=3 WHERE id='{document}';")
    assert "attempt limit" in rpc(
        sql, "enqueue_document_ingestion_retry", [document, PATIENT, CLINICIAN], succeeds=False
    )
    assert len(rows(sql, "document_ingestion_runs")) == 1
    for table, snapshot in evidence.items():
        assert rows(sql, table) == snapshot
    assert_history(sql, before)
