"""Cross-clinic scheduling and clinic-tagged appointments in disposable PostgreSQL 16.

CLN-003 slices E and F, migration 069. Reuses the notification-centre fixture, which applies the
real ledger in order and then 065-067 and 069. Tests marked ``before_clinic_scheduling`` seed rows
the way the deployed schema holds them and apply 069 themselves to check the backfill and its
fail-closed checks. Synthetic identities only; nothing here contacts a hosted database.
"""

import json
import os
import subprocess
from uuid import uuid4

import pytest

from tests.integration.test_clinic_memberships_postgres import (
    CLINIC,
    SECOND_CLINIC,
    link,
    new_clinician,
    second_clinic,
)
from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    FOREIGN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    TEAM,
    call,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check with 069",
)

MIGRATION = next(MIGRATIONS.glob("069_clinic_scheduling_and_tags.sql"))
# A day far enough ahead that nothing is "past"; offsets are minutes from 10:00 UTC.
BASE = "(date_trunc('day', clock_timestamp()) + interval '10 days 10 hours')"


def at(minutes):
    return f"{BASE} + interval '{minutes} minutes'"


def book(sql, patient, team, minutes, *, duration=30, status="confirmed", succeeds=True):
    key = str(uuid4())
    out = sql(
        f"""INSERT INTO appointments(id,patient_id,care_team_id,scheduled_at,duration_minutes,status)
        VALUES('{key}','{patient}','{team}',{at(minutes)},{duration},'{status}');""",
        succeeds=succeeds,
    )
    return key if succeeds else out


def two_clinic_clinician(sql):
    """CLINICIAN also belongs to a second clinic and holds a link there for FOREIGN."""
    second_clinic(sql)
    sql(f"""SET ROLE service_role;
      INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
        VALUES('{CLINICIAN}','{SECOND_CLINIC}','provider');""")
    return link(sql, CLINICIAN, patient=FOREIGN, clinic=SECOND_CLINIC)


def apply_scheduling(sql):
    return subprocess.run(
        sql.command,
        input="BEGIN;\n" + MIGRATION.read_text() + "\nCOMMIT;",
        capture_output=True,
        text=True,
        timeout=60,
    )


def propose(sql, team, minutes, *, actor=CLINICIAN, duration=30):
    slots = ",".join(f"({at(m)})" for m in minutes)
    out = sql(
        f"""SET ROLE service_role; SELECT propose_appointment_slots('{actor}','{team}',
        ARRAY[{slots}]::timestamptz[],{duration},'follow_up','Synthetic room','Synthetic reason')::text;"""
    )
    return json.loads(out)


# ── Backfill and fail-closed checks ────────────────────────────────────────────────────────


@pytest.mark.before_clinic_scheduling
def test_backfill_tags_each_appointment_with_its_links_clinic_and_clinician(sql):
    second_team = two_clinic_clinician(sql)
    here = book(sql, PATIENT, TEAM, 0, status="proposed")
    there = book(sql, FOREIGN, second_team, 60, status="scheduled")

    result = apply_scheduling(sql)

    assert result.returncode == 0, result.stderr
    rows = sql(
        f"""SELECT id||'|'||clinic_id||'|'||clinician_id FROM appointments
        WHERE id IN ('{here}','{there}') ORDER BY scheduled_at"""
    ).splitlines()
    assert rows == [f"{here}|{CLINIC}|{CLINICIAN}", f"{there}|{SECOND_CLINIC}|{CLINICIAN}"]
    # The backfill is an UPDATE of two columns only: no notification, no new expiry.
    assert sql("SELECT count(*) FROM appointments WHERE clinic_id IS NULL") == "0"
    assert (
        sql(
            """SELECT is_nullable FROM information_schema.columns
        WHERE table_name='appointments' AND column_name IN ('clinic_id','clinician_id')"""
        ).replace("\n", ",")
        == "NO,NO"
    )


@pytest.mark.before_clinic_scheduling
def test_backfill_stops_when_a_link_has_no_clinic_and_changes_nothing(sql):
    clinic_less = new_clinician(sql)
    team = link(sql, clinic_less)
    book(sql, PATIENT, team, 0, status="scheduled")
    book(sql, PATIENT, TEAM, 600, status="proposed")

    result = apply_scheduling(sql)

    assert result.returncode != 0
    assert "1 appointment(s) cannot be matched to exactly one care-team link" in result.stderr
    assert PATIENT not in result.stderr and team not in result.stderr
    assert (
        sql(
            """SELECT count(*) FROM information_schema.columns
        WHERE table_name='appointments' AND column_name='clinic_id'"""
        )
        == "0"
    )
    assert sql("SELECT to_regprocedure('private.appointment_link_guard()') IS NULL") == "t"


@pytest.mark.before_clinic_scheduling
def test_backfill_stops_on_existing_clinician_overlap_and_reports_counts_only(sql):
    second_team = two_clinic_clinician(sql)
    first = book(sql, PATIENT, TEAM, 0)
    second = book(sql, FOREIGN, second_team, 15)

    result = apply_scheduling(sql)

    assert result.returncode != 0
    assert (
        "1 overlapping confirmed/scheduled appointment pair(s) for 1 clinician(s)" in result.stderr
    )
    for identifier in (first, second, CLINICIAN, PATIENT, FOREIGN, SECOND_CLINIC):
        assert identifier not in result.stderr
    assert (
        sql(
            """SELECT count(*) FROM information_schema.columns
        WHERE table_name='appointments' AND column_name='clinician_id'"""
        )
        == "0"
    )
    # Nothing was cancelled to make the migration pass.
    assert sql("SELECT count(*) FROM appointments WHERE status='confirmed'") == "2"


# ── The clinician's one schedule ───────────────────────────────────────────────────────────


def test_constraint_present_and_no_appointment_without_a_clinic(sql):
    assert (
        sql(
            """SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint
        WHERE conrelid='appointments'::regclass AND contype='x'"""
        )
        == "appointments_clinician_no_overlap,appointments_patient_no_overlap"
    )
    book(sql, PATIENT, TEAM, 0)
    assert sql("SELECT count(*) FROM appointments WHERE clinic_id IS NULL") == "0"
    # Grants did not change: browser roles gained nothing on the new objects.
    assert (
        sql(
            """SELECT has_function_privilege('authenticated',
        'public.propose_appointment_slots(uuid,uuid,timestamptz[],integer,text,text,text)','EXECUTE')"""
        )
        == "f"
    )


@pytest.mark.parametrize("status", ["confirmed", "scheduled"])
def test_same_clinician_cannot_overlap_across_two_clinics(sql, status):
    second_team = two_clinic_clinician(sql)
    book(sql, PATIENT, TEAM, 0, status=status)

    error = book(sql, FOREIGN, second_team, 15, status=status, succeeds=False)

    assert "appointments_clinician_no_overlap" in error
    assert sql(f"SELECT count(*) FROM appointments WHERE patient_id='{FOREIGN}'") == "0"


def test_back_to_back_visits_and_other_clinicians_are_allowed(sql):
    second_team = two_clinic_clinician(sql)
    book(sql, PATIENT, TEAM, 0)
    # [start, end) permits an adjacent visit at the other clinic, and a gap before it.
    book(sql, FOREIGN, second_team, 30)
    book(sql, FOREIGN, second_team, -30)
    # A different clinician at the same time is untouched.
    other_team = link(sql, OTHER, patient=FOREIGN)
    book(sql, FOREIGN, other_team, 0)
    assert sql("SELECT count(*) FROM appointments") == "4"


def test_proposed_options_do_not_reserve_time(sql):
    second_team = two_clinic_clinician(sql)
    book(sql, PATIENT, TEAM, 0)
    book(sql, FOREIGN, second_team, 10, status="proposed")
    book(sql, FOREIGN, second_team, 10, status="cancelled")
    assert sql("SELECT count(*) FROM appointments") == "3"


def test_offer_checks_the_whole_schedule_and_names_only_the_clinic(sql):
    second_team = two_clinic_clinician(sql)
    book(sql, FOREIGN, second_team, 60)

    refused = propose(sql, TEAM, [0, 70, 120])

    assert refused["error"] == "clinician_conflict"
    (conflict,) = refused["conflicts"]
    assert conflict["clinic_name"] == "Second synthetic clinic"
    assert conflict["clinic_id"] == SECOND_CLINIC
    assert conflict["slot"] != conflict["starts_at"]
    assert set(conflict) == {"slot", "clinic_id", "clinic_name", "starts_at", "ends_at"}
    # Another clinic's patient never appears in the refusal.
    serialized = json.dumps(refused)
    assert FOREIGN not in serialized and "Foreign" not in serialized
    # An offer with a conflicting slot stores nothing: no partial offer.
    assert sql(f"SELECT count(*) FROM appointments WHERE patient_id='{PATIENT}'") == "0"
    assert sql("SELECT count(*) FROM appointment_offer_events") == "0"


def test_offer_reports_every_conflicting_slot_and_ignores_adjacent_ones(sql):
    second_team = two_clinic_clinician(sql)
    book(sql, FOREIGN, second_team, 60)
    book(sql, PATIENT, TEAM, 180)

    refused = propose(sql, TEAM, [30, 90, 150, 210, 240])  # 30 and 90 touch/overlap the first
    assert refused["error"] == "invalid"  # more than four slots

    refused = propose(sql, TEAM, [31, 61, 181, 300])
    assert [c["clinic_name"] for c in refused["conflicts"]] == [
        "Second synthetic clinic",
        "Second synthetic clinic",
        "Synthetic clinic",
    ]
    # Adjacent slots (ending exactly where a visit starts, or starting where it ends) are fine.
    accepted = propose(sql, TEAM, [30, 90])
    assert len(accepted["appointments"]) == 2


def test_a_clear_offer_carries_the_links_clinic_and_clinician(sql):
    offered = propose(sql, TEAM, [0, 60])

    rows = offered["appointments"]
    assert {r["clinic_id"] for r in rows} == {CLINIC}
    assert {r["clinician_id"] for r in rows} == {CLINICIAN}
    assert {r["status"] for r in rows} == {"proposed"}


def test_accepting_a_slot_the_clinician_has_since_lost_is_a_safe_conflict(sql):
    second_team = two_clinic_clinician(sql)
    first, second = (r["id"] for r in propose(sql, TEAM, [0, 120])["appointments"])
    # While the offer is open, the clinician books the first slot at the other clinic.
    book(sql, FOREIGN, second_team, 10)

    lost = json.loads(
        sql(
            f"""SET ROLE service_role; SELECT respond_to_appointment_offer(
            '{PATIENT}','{first}','accept',NULL)::text;"""
        )
    )

    assert lost == {"error": "conflict"}
    assert (
        sql(
            f"SELECT string_agg(status::text,',' ORDER BY scheduled_at) FROM appointments WHERE patient_id='{PATIENT}'"
        )
        == "proposed,proposed"
    )
    won = json.loads(
        sql(
            f"""SET ROLE service_role; SELECT respond_to_appointment_offer(
            '{PATIENT}','{second}','accept',NULL)::text;"""
        )
    )
    assert won["appointment"]["status"] == "confirmed"
    assert won["appointment"]["clinic_id"] == CLINIC


# ── The appointment always agrees with its link ─────────────────────────────────────────────


def test_an_appointment_cannot_name_a_clinic_other_than_its_links(sql):
    second_clinic(sql)
    key = str(uuid4())
    sql(
        f"""INSERT INTO appointments(id,patient_id,care_team_id,clinic_id,clinician_id,scheduled_at,status)
        VALUES('{key}','{PATIENT}','{TEAM}','{SECOND_CLINIC}','{OTHER}',{at(0)},'proposed');"""
    )
    assert sql(f"SELECT clinic_id||'|'||clinician_id FROM appointments WHERE id='{key}'") == (
        f"{CLINIC}|{CLINICIAN}"
    )
    sql(f"UPDATE appointments SET clinic_id='{SECOND_CLINIC}' WHERE id='{key}'")
    assert sql(f"SELECT clinic_id FROM appointments WHERE id='{key}'") == CLINIC


def test_a_link_without_a_clinic_cannot_hold_an_appointment(sql):
    clinic_less = new_clinician(sql)
    team = link(sql, clinic_less)
    error = book(sql, PATIENT, team, 0, status="proposed", succeeds=False)
    # The link guard (065) gives the link its clinician's clinic, so it only fails when none.
    assert "needs a care-team link that has a clinic" in error or "violates not-null" in error


def test_a_link_that_moves_to_another_clinic_carries_its_appointments(sql):
    second_clinic(sql)
    sql(f"""SET ROLE service_role; INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
      VALUES('{CLINICIAN}','{SECOND_CLINIC}','provider');""")
    key = book(sql, PATIENT, TEAM, 0, status="scheduled")

    sql(
        f"SET ROLE service_role; UPDATE care_teams SET clinic_id='{SECOND_CLINIC}' WHERE id='{TEAM}';"
    )

    assert sql(f"SELECT clinic_id FROM appointments WHERE id='{key}'") == SECOND_CLINIC


def test_a_link_handed_to_a_busy_clinician_fails_instead_of_double_booking(sql):
    book(sql, PATIENT, TEAM, 0, status="scheduled")
    other_team = link(sql, OTHER, patient=FOREIGN)
    book(sql, FOREIGN, other_team, 10, status="scheduled")

    error = sql(
        f"SET ROLE service_role; UPDATE care_teams SET clinician_id='{OTHER}' WHERE id='{TEAM}';",
        succeeds=False,
    )

    assert "appointments_clinician_no_overlap" in error
    assert sql(f"SELECT clinician_id FROM care_teams WHERE id='{TEAM}'") == CLINICIAN


# ── Slice F: the notification centre names the appointment's own clinic ─────────────────────


def test_reminder_and_appointment_items_name_the_appointments_clinic(sql):
    second_clinic(sql)
    sql(f"""SET ROLE service_role; INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
      VALUES('{OTHER}','{SECOND_CLINIC}','provider');""")
    second_team = link(sql, OTHER, patient=PATIENT, clinic=SECOND_CLINIC)
    visit = book(sql, PATIENT, second_team, 0, status="scheduled")
    sql(
        f"""INSERT INTO notifications(patient_id,notification_type,title,body,action_url,dedupe_key,metadata)
        VALUES('{PATIENT}','appointment','Upcoming appointment tomorrow','Synthetic','/visits',
          'appointment:{visit}:24h','{{"appointment_id":"{visit}"}}'::jsonb);"""
    )

    items = [i for i in call(sql)["items"] if i["category"] == "appointments"]

    assert {i["event_type"] for i in items} == {"appointment_changed", "appointment_reminder"}
    # The patient also has a link at the first clinic; neither item may be labelled with it.
    assert {i["clinic_name"] for i in items} == {"Second synthetic clinic"}
    assert {i["clinic_id"] for i in items} == {SECOND_CLINIC}


# ── Audit ───────────────────────────────────────────────────────────────────────────────────


def test_denial_events_gain_a_clinic_and_stay_append_only(sql):
    sql(
        f"""SET ROLE service_role; INSERT INTO authorization_denial_events(reason_code,clinic_id)
        VALUES('NO_CARE_TEAM_ASSIGNMENT','{CLINIC}');"""
    )
    assert sql("SELECT clinic_id FROM authorization_denial_events") == CLINIC
    for statement in (
        "UPDATE authorization_denial_events SET clinic_id=NULL",
        "DELETE FROM authorization_denial_events",
    ):
        error = sql(f"SET ROLE service_role; {statement};", succeeds=False)
        assert "permission denied" in error, statement
    for role in ("anon", "authenticated"):
        error = sql(
            f"SET ROLE {role}; SELECT clinic_id FROM authorization_denial_events;", succeeds=False
        )
        assert "permission denied" in error


@pytest.mark.before_clinic_scheduling
def test_platform_default_grants_on_the_denial_trail_are_restored_before_verification(sql):
    # Hosted projects keep the platform's default table grants, which 033 never revoked.
    sql(
        """GRANT ALL ON TABLE public.authorization_denial_events TO anon, authenticated, service_role"""
    )

    result = apply_scheduling(sql)

    assert result.returncode == 0, result.stderr
    granted = sql(
        """SELECT r.role || ':' || p.privilege
             FROM unnest(ARRAY['anon','authenticated','service_role']) r(role)
             CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE']) p(privilege)
            WHERE has_table_privilege(r.role, 'public.authorization_denial_events', p.privilege)
            ORDER BY 1"""
    ).splitlines()
    assert granted == ["service_role:INSERT", "service_role:SELECT"]
