"""Timeline selections and private-thread authorization on real offline migrations.

The SQL transport preserves selected columns, filters, FK joins, ordering and
limits. It does not emulate a hosted PostgREST schema cache or HTTP transport.
"""

import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.clinician_service import ClinicianService
from app.services.patient_timeline_service import SOURCES
from app.services.risk_score_service import RiskScoreService
from tests.integration.reconciliation_postgres_adapter import PostgresDatabase, literal
from tests.integration.test_clinic_memberships_postgres import CLINIC, link
from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    TEAM,
    appointment,
    document,
    send,
    thread,
)
from tests.integration.test_symptom_intake_postgres import call_sql, confirmation, ready

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]
pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit offline PostgreSQL opt-in",
)


class TimelineDatabase(PostgresDatabase):
    def __init__(self, execute):
        super().__init__(execute)
        self.failures = []
        self.message_threads = []

    def table(self, name):
        return TimelineQuery(self, name)

    def rpc(self, name, params):
        if name == "care_conversation_operation":
            self.message_threads.append(params["p_payload"]["conversation_id"])
        return super().rpc(name, params)


class TimelineQuery:
    def __init__(self, database, name):
        self.database, self.name = database, name
        self.columns, self.joins, self.filters, self.ordering = [], [], [], []
        self.maximum = None

    def select(self, fields):
        scalar, _, nested = fields.partition(
            ","
            + next(
                (
                    source.parent
                    for source in SOURCES
                    if source.table == self.name and source.parent
                ),
                "__no_parent__",
            )
            + "!inner("
        )
        self.columns = [f"{self.name}.{field}" for field in scalar.split(",")]
        if nested:
            source = next(source for source in SOURCES if source.table == self.name)
            # Require a real FK, as the API's embedded relationship does.
            foreign_key = self.database.execute(
                "SELECT count(*) FROM pg_constraint c JOIN pg_attribute a "
                "ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1] "
                f"WHERE c.contype='f' AND c.conrelid='public.{self.name}'::regclass "
                f"AND c.confrelid='public.{source.parent}'::regclass "
                f"AND a.attname={literal(source.reference)};"
            )
            assert foreign_key == "1"
            self.joins.append(
                f"JOIN {source.parent} ON {self.name}.{source.reference}={source.parent}.id"
            )
            # Exercise the embedded patient_id column too, not only its filter.
            self.columns.append(f"{source.parent}.patient_id")
        return self

    def eq(self, field, value):
        return self._filter(field, "=", literal(value))

    def in_(self, field, values):
        members = ",".join(literal(value) for value in values) or "NULL"
        return self._filter(field, "IN", f"({members})")

    def gte(self, field, value):
        return self._filter(field, ">=", literal(value))

    def _filter(self, field, operator, value):
        column = field if "." in field else f"{self.name}.{field}"
        self.filters.append(f"{column} {operator} {value}")
        return self

    @property
    def not_(self):
        return self

    def is_(self, field, value):
        assert value == "null"
        return self._filter(field, "IS NOT", "NULL")

    def order(self, field, *, desc=False, nullsfirst=None):
        direction = "DESC" if desc else "ASC"
        nulls = "" if nullsfirst is None else " NULLS FIRST" if nullsfirst else " NULLS LAST"
        self.ordering.append(f"{self.name}.{field} {direction}{nulls}")
        return self

    def limit(self, maximum):
        self.maximum = int(maximum)
        return self

    def execute(self):
        where = " AND ".join(self.filters) or "true"
        ordering = " ORDER BY " + ",".join(self.ordering) if self.ordering else ""
        limit = f" LIMIT {self.maximum}" if self.maximum is not None else ""
        statement = (
            "SET ROLE service_role; SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]') "
            f"FROM (SELECT {','.join(self.columns)} FROM {self.name} {' '.join(self.joins)} "
            f"WHERE {where}{ordering}{limit}) t;"
        )
        try:
            return SimpleNamespace(data=json.loads(self.database.execute(statement)))
        except AssertionError:
            self.database.failures.append(self.name)
            raise


@pytest.fixture
def timeline_sql(sql):
    for name in (
        "010_chat_state_and_a2a_tasks.sql",
        "051_health_knowledge_and_chat_sessions.sql",
        "059_chat_safety_alerts.sql",
        "060_confirmed_symptom_intake.sql",
    ):
        sql((MIGRATIONS / name).read_text())
    # Care-team ownership columns the timeline reads (the real definitions are migrations
    # 083 and 084; this reduced schema only needs their shape). Shared: unrouted/unowned.
    sql("""
      ALTER TABLE documents ADD COLUMN IF NOT EXISTS care_team_id uuid,
        ADD COLUMN IF NOT EXISTS routing_state text NOT NULL DEFAULT 'unrouted';
      ALTER TABLE adr_assessments ADD COLUMN IF NOT EXISTS reviewed_by_care_team_id uuid;
      ALTER TABLE source_provenances ADD COLUMN IF NOT EXISTS care_team_id uuid;
      CREATE TABLE IF NOT EXISTS care_plans(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id uuid NOT NULL, care_team_id uuid, ownership_state text NOT NULL DEFAULT 'owned');
      ALTER TABLE care_plan_versions ADD COLUMN IF NOT EXISTS care_plan_id uuid;
      GRANT ALL ON care_plans TO service_role;
    """)
    return sql


def seed_events(sql):
    med, plan, fact, adr, recommendation = [str(uuid4()) for _ in range(5)]
    preview = ready(sql)
    snapshot = preview["preview"]
    preview = json.loads(
        sql(
            call_sql(
                "answer",
                {
                    "intake_id": preview["id"],
                    "expected_revision": preview["revision"],
                    "mutation_id": str(uuid4()),
                    "answer": {
                        "question_id": "severity",
                        "state": "answered",
                        "value": 4,
                        "locale": "en-US",
                        "wording": "4",
                    },
                },
            )
        )
    )
    snapshot["answers"] = preview["answers"]
    preview = json.loads(
        sql(
            call_sql(
                "preview",
                {
                    "intake_id": preview["id"],
                    "expected_revision": preview["revision"],
                    "preview": snapshot,
                },
            )
        )
    )
    symptom = json.loads(sql(call_sql("confirm", confirmation(preview))))["confirmed_report_id"]
    doc = document(sql)
    visit = appointment(sql, "scheduled")
    sql(f"""
      UPDATE documents SET review_status='approved',reviewed_at=clock_timestamp() WHERE id='{doc}';
      INSERT INTO medications(id,patient_id,name,dosage,frequency)
        VALUES('{med}','{PATIENT}','Synthetic medication','1 mg','daily');
      INSERT INTO adherence_logs(patient_id,target_type,target_id,status)
        VALUES('{PATIENT}','medication','{med}','taken');
      INSERT INTO appointment_offer_events(appointment_id,patient_id,proposal_group_id,actor_id,action,new_status)
        VALUES('{visit}','{PATIENT}','{uuid4()}','{CLINICIAN}','propose','scheduled');
      INSERT INTO care_plans(id,patient_id,care_team_id) VALUES('{plan}','{PATIENT}','{TEAM}');
      INSERT INTO care_plan_versions(id,patient_id,version_number,care_plan_id)
        VALUES('{plan}','{PATIENT}',1,'{plan}');
      INSERT INTO care_plan_audit_events(plan_version_id,actor_id,event_type)
        VALUES('{plan}','{CLINICIAN}','created');
      INSERT INTO clinical_facts(id,patient_id,fact_type,subject_type)
        VALUES('{fact}','{PATIENT}','medication','patient');
      INSERT INTO clinical_fact_audit_events(fact_id,actor_id,event_type)
        VALUES('{fact}','{CLINICIAN}','created');
      INSERT INTO adr_assessments(id,patient_id,symptom_report_id,suspect_medication_id,
        suspect_medication_name,naranjo_score,causality)
        VALUES('{adr}','{PATIENT}','{symptom}','{med}','Synthetic medication',2,'Possible');
      INSERT INTO adr_assessment_audit_events(adr_assessment_id,actor_id,event_type)
        VALUES('{adr}','{CLINICIAN}','information_requested');
      INSERT INTO clinical_recommendations(id,patient_id,action_type,evidence,rationale,proposer_type)
        VALUES('{recommendation}','{PATIENT}','synthetic_test','[{{}}]','Excluded rationale','test');
      INSERT INTO clinical_action_audit_records(recommendation_id,actor_id,event_type)
        VALUES('{recommendation}','{CLINICIAN}','proposed');
    """)
    own_thread = thread(sql)
    send(sql, own_thread)
    return own_thread


@pytest.mark.asyncio
async def test_every_source_selection_executes_as_service_role_and_returns_real_events(
    timeline_sql,
):
    own_thread = seed_events(timeline_sql)
    db = TimelineDatabase(timeline_sql)
    result = await ClinicianService(db).get_patient_timeline(UUID(CLINICIAN), UUID(PATIENT))
    assert db.failures == []
    assert len(result.sources) == len(SOURCES)
    assert all(
        source.status == "available" and source.returned >= 1 for source in result.sources
    ), [
        (s.source, s.status, s.returned)
        for s in result.sources
        if s.status != "available" or s.returned < 1
    ]
    assert all(source.omitted_invalid == 0 for source in result.sources)
    assert {event.domain for event in result.events} == {
        "document",
        "approval",
        "medication",
        "symptom",
        "adherence",
        "message",
        "appointment",
        "action",
    }
    assert db.message_threads == [own_thread]
    for event in result.events:
        assert all(not field.endswith("_id") for field in event.details)
    assert "sender_name" not in result.model_dump_json()
    assert "Synthetic message" not in result.model_dump_json()
    assert "Excluded rationale" not in result.model_dump_json()
    freshness = await RiskScoreService(db)._fetch_source_freshness(UUID(PATIENT))
    assert all(source.status == "available" and source.latest_at for source in freshness)
    assert db.failures == []


@pytest.mark.asyncio
async def test_real_rpc_excludes_another_clinicians_thread(timeline_sql):
    own_thread = seed_events(timeline_sql)
    link(timeline_sql, OTHER)
    other_thread = json.loads(
        timeline_sql(
            f"SET ROLE service_role; SELECT care_conversation_operation('{PATIENT}','patient','open',"
            f"'{json.dumps({'recipient_id': OTHER})}'::jsonb);"
        )
    )["id"]
    send(timeline_sql, other_thread, actor=OTHER)
    db = TimelineDatabase(timeline_sql)
    result = await ClinicianService(db).get_patient_timeline(UUID(CLINICIAN), UUID(PATIENT))
    assert db.message_threads == [own_thread]
    assert other_thread not in result.model_dump_json()
    assert OTHER not in result.model_dump_json()
    assert all(
        event.details == {"sender_role": "clinician"}
        for event in result.events
        if event.domain == "message"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation", ["membership", "clinic", "conversation_clinic", "assignment"]
)
async def test_real_rpc_denies_stale_thread_even_with_a_patient_assignment(
    timeline_sql, revocation
):
    own_thread = seed_events(timeline_sql)
    # Keep a separate active assignment in a second clinic: broad patient access alone
    # must never authorize reading the old private conversation.
    second = str(uuid4())
    timeline_sql(f"""INSERT INTO clinics(id,display_name,canonical_name)
      VALUES('{second}','Second synthetic clinic','second synthetic timeline clinic');
      INSERT INTO clinic_memberships(clinician_id,clinic_id,role,status)
        VALUES('{CLINICIAN}','{second}','provider','active');""")
    link(timeline_sql, CLINICIAN, clinic=second)
    if revocation == "membership":
        timeline_sql(
            f"UPDATE clinic_memberships SET status='inactive' WHERE clinician_id='{CLINICIAN}' AND clinic_id='{CLINIC}';"
        )
    elif revocation == "clinic":
        timeline_sql(f"UPDATE clinics SET status='suspended' WHERE id='{CLINIC}';")
    elif revocation == "conversation_clinic":
        timeline_sql(f"UPDATE care_conversations SET clinic_id='{second}' WHERE id='{own_thread}';")
    else:
        timeline_sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    db = TimelineDatabase(timeline_sql)
    result = await ClinicianService(db).get_patient_timeline(UUID(CLINICIAN), UUID(PATIENT))
    coverage = next(
        source
        for source in result.sources
        if source.source.startswith("care_conversation_messages")
    )
    assert coverage.status == "unavailable"
    assert not any(event.domain == "message" for event in result.events)
