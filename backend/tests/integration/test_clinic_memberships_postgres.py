"""Clinic memberships and clinic-tagged care-team links in disposable PostgreSQL 16.

CLN-003 slice A, migration 065. Reuses the notification-centre fixture, which applies the
real ledger in order and then 065. Tests marked ``before_clinic_memberships`` seed rows the
way the deployed schema holds them and apply 065 themselves to check the backfill.
Synthetic identities only; nothing here contacts a hosted database.
"""

import json
import os
import subprocess
from uuid import uuid4

import pytest

from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    FOREIGN,
    MIGRATIONS,
    OTHER,
    PATIENT,
    TEAM,
    apply_clinic_memberships,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("NOTIFICATION_CENTRE_TEST_POSTGRES_DOCKER") != "1",
    reason="explicit opt-in disposable Docker PostgreSQL contract check with 065",
)

CLINIC = "00000000-0000-0000-0000-000000000007"
SECOND_CLINIC = "00000000-0000-0000-0000-000000000008"
MIGRATION = next(MIGRATIONS.glob("065_clinic_memberships.sql"))


def second_clinic(sql):
    sql(f"""INSERT INTO clinics(id,display_name,canonical_name) VALUES
      ('{SECOND_CLINIC}','Second synthetic clinic','second synthetic clinic');""")


def new_clinician(sql, *, clinic=None, role="provider"):
    key = str(uuid4())
    clinic_sql = f"'{clinic}'" if clinic else "NULL"
    sql(f"""INSERT INTO auth.users VALUES ('{key}');
      INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id,role)
      VALUES('{key}','{key}@synthetic.invalid','Synthetic','Staff','Synthetic',
        'Synthetic clinic',{clinic_sql},'{role}');""")
    return key


def memberships(sql, clinician):
    rows = sql(f"""SELECT clinic_id||'|'||role||'|'||status FROM clinic_memberships
      WHERE clinician_id='{clinician}' ORDER BY clinic_id""")
    return [tuple(row.split("|")) for row in rows.splitlines()]


def link(sql, clinician, *, patient=PATIENT, clinic=None, succeeds=True):
    key = str(uuid4())
    columns = "id,patient_id,clinician_id,role,status" + (",clinic_id" if clinic else "")
    values = f"'{key}','{patient}','{clinician}','primary_care','active'" + (
        f",'{clinic}'" if clinic else ""
    )
    out = sql(
        f"SET ROLE service_role; INSERT INTO care_teams({columns}) VALUES({values});",
        succeeds=succeeds,
    )
    return key if succeeds else out


def clinic_of(sql, team):
    return sql(f"SELECT coalesce(clinic_id::text,'none') FROM care_teams WHERE id='{team}'")


def as_user(user, query):
    claims = json.dumps({"sub": user})
    return f"SET ROLE authenticated; SET request.jwt.claims='{claims}'; {query}"


def signed_in(sql):
    """Read auth.uid() from JWT claims and give browser roles hosted-default table grants."""
    sql("""CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
        SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb->>'sub')::uuid $$;
      GRANT USAGE ON SCHEMA auth TO authenticated;
      GRANT SELECT ON patients, care_teams, medications, clinicians TO authenticated;""")


# ── Backfill ───────────────────────────────────────────────────────────────────────────


@pytest.mark.before_clinic_memberships
def test_backfill_one_membership_per_clinician_and_a_clinic_per_link(sql):
    second_clinic(sql)
    nurse = new_clinician(sql, clinic=SECOND_CLINIC, role="nurse")
    admin = new_clinician(sql, clinic=CLINIC, role="admin")
    unattached = new_clinician(sql)
    nurse_team = link(sql, nurse, patient=FOREIGN)
    unattached_team = link(sql, unattached)
    pending = str(uuid4())
    sql(f"""INSERT INTO care_teams(id,clinician_id,role,status,invite_code)
      VALUES('{pending}','{nurse}','provider','pending','SYNTH001');""")

    result = subprocess.run(
        sql.command,
        input=MIGRATION.read_text(),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    # Counts only: the verification notice never names a clinician.
    assert "1 clinician(s) have no clinic and received no membership" in result.stderr
    assert unattached not in result.stderr
    assert memberships(sql, CLINICIAN) == [(CLINIC, "provider", "active")]
    assert memberships(sql, OTHER) == [(CLINIC, "provider", "active")]
    assert memberships(sql, admin) == [(CLINIC, "admin", "active")]
    assert memberships(sql, nurse) == [(SECOND_CLINIC, "nurse", "active")]
    assert memberships(sql, unattached) == []
    assert clinic_of(sql, TEAM) == CLINIC
    assert clinic_of(sql, nurse_team) == SECOND_CLINIC
    assert clinic_of(sql, pending) == SECOND_CLINIC
    assert clinic_of(sql, unattached_team) == "none"
    assert sql("""SELECT string_agg(pg_get_constraintdef(oid), ';') FROM pg_constraint
      WHERE conrelid='care_teams'::regclass AND contype='u'""") == (
        "UNIQUE (patient_id, clinician_id, clinic_id)"
    )


@pytest.mark.before_clinic_memberships
def test_the_migration_fails_closed_and_leaves_nothing_behind(sql):
    # A schema without the constraint 065 replaces is unexpected: stop, change nothing.
    sql("ALTER TABLE care_teams DROP CONSTRAINT care_teams_patient_id_clinician_id_key;")

    error = sql("BEGIN;\n" + MIGRATION.read_text() + "\nCOMMIT;", succeeds=False)

    assert "no UNIQUE (patient_id, clinician_id) constraint to replace" in error
    assert sql("SELECT to_regclass('public.clinic_memberships') IS NULL") == "t"
    assert (
        sql(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='care_teams' AND column_name='clinic_id'"
        )
        == "0"
    )


@pytest.mark.before_clinic_memberships
def test_verification_rejects_a_link_left_without_its_clinicians_clinic(sql):
    # Simulate a backfill gap: a link written between the backfill and the check.
    body = MIGRATION.read_text().replace(
        "-- ── 4. Fail-closed verification",
        "ALTER TABLE care_teams DISABLE TRIGGER care_teams_clinic_guard;\n"
        f"UPDATE care_teams SET clinic_id = NULL WHERE id = '{TEAM}';\n"
        "-- ── 4. Fail-closed verification",
    )

    error = sql("BEGIN;\n" + body + "\nCOMMIT;", succeeds=False)

    assert "Every care-team link needs a clinic unless its clinician has none" in error
    assert sql("SELECT to_regclass('public.clinic_memberships') IS NULL") == "t"
    apply_clinic_memberships(sql)
    assert clinic_of(sql, TEAM) == CLINIC


# ── Links per clinic ───────────────────────────────────────────────────────────────────


def test_one_clinician_can_hold_a_link_per_clinic_for_the_same_patient(sql):
    second_clinic(sql)
    sql(f"""SET ROLE service_role; INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
      VALUES('{CLINICIAN}','{SECOND_CLINIC}','provider');""")

    second = link(sql, CLINICIAN, clinic=SECOND_CLINIC)

    assert clinic_of(sql, second) == SECOND_CLINIC
    assert (
        sql(f"""SELECT count(*) FROM care_teams
      WHERE patient_id='{PATIENT}' AND clinician_id='{CLINICIAN}' AND status='active'""")
        == "2"
    )
    duplicate = link(sql, CLINICIAN, clinic=CLINIC, succeeds=False)
    assert "care_teams_patient_clinician_clinic_key" in duplicate


def test_a_link_needs_an_active_membership_at_its_clinic_and_keeps_it(sql):
    second_clinic(sql)

    error = link(sql, OTHER, patient=FOREIGN, clinic=SECOND_CLINIC, succeeds=False)
    assert "clinic where the clinician is an active member" in error

    sql(f"UPDATE clinicians SET clinic_id='{SECOND_CLINIC}' WHERE id='{OTHER}';")
    error = link(sql, OTHER, patient=FOREIGN, clinic=CLINIC, succeeds=False)
    assert "clinic where the clinician is an active member" in error

    error = sql(f"UPDATE care_teams SET clinic_id=NULL WHERE id='{TEAM}';", succeeds=False)
    assert "A care-team link keeps its clinic" in error
    error = sql(
        f"UPDATE care_teams SET clinic_id='{SECOND_CLINIC}' WHERE id='{TEAM}';", succeeds=False
    )
    assert "clinic where the clinician is an active member" in error
    # A link reassigned to another clinician follows that clinician's clinic.
    sql(f"UPDATE care_teams SET clinician_id='{OTHER}' WHERE id='{TEAM}';")
    assert clinic_of(sql, TEAM) == SECOND_CLINIC
    sql(f"UPDATE care_teams SET clinician_id='{CLINICIAN}' WHERE id='{TEAM}';")
    assert clinic_of(sql, TEAM) == CLINIC
    # Ordinary updates that leave the clinic alone are untouched.
    sql(f"UPDATE care_teams SET status='inactive' WHERE id='{TEAM}';")
    assert clinic_of(sql, TEAM) == CLINIC


def test_a_clinician_without_a_clinic_keeps_one_link_per_patient(sql):
    unattached = new_clinician(sql)
    first = link(sql, unattached)

    assert clinic_of(sql, first) == "none"
    duplicate = link(sql, unattached, succeeds=False)
    assert "uq_care_teams_patient_clinician_without_clinic" in duplicate


# ── Invite codes ───────────────────────────────────────────────────────────────────────


def invite(sql, clinician, code, *, clinic=None):
    key = str(uuid4())
    clinic_column, clinic_value = (",clinic_id", f",'{clinic}'") if clinic else ("", "")
    sql(f"""SET ROLE service_role; INSERT INTO care_teams(id,clinician_id,invite_code,
        invite_expires_at,status,role{clinic_column})
      VALUES('{key}','{clinician}','{code}',clock_timestamp()+interval '7 days','pending',
        'provider'{clinic_value});""")
    return key


def claim(sql, code, patient):
    # The patient join flow claims the pending row; it never writes the clinic.
    return sql(f"""SET ROLE service_role; UPDATE care_teams SET patient_id='{patient}',
        status='active', invite_claimed_at=clock_timestamp()
      WHERE invite_code='{code}' AND status='pending' AND patient_id IS NULL
      RETURNING coalesce(clinic_id::text,'none');""")


def test_joining_with_an_invite_code_links_at_the_codes_clinic(sql):
    second_clinic(sql)
    sql(f"""SET ROLE service_role; INSERT INTO clinic_memberships(clinician_id,clinic_id,role)
      VALUES('{OTHER}','{SECOND_CLINIC}','provider');""")
    invite(sql, OTHER, "SECOND01", clinic=SECOND_CLINIC)
    # The deployed backend sends no clinic: the code takes the clinician's clinic.
    legacy = invite(sql, OTHER, "LEGACY01")
    invite(sql, OTHER, "LEGACY02")

    assert clinic_of(sql, legacy) == CLINIC
    assert claim(sql, "SECOND01", PATIENT) == SECOND_CLINIC
    assert claim(sql, "LEGACY01", PATIENT) == CLINIC
    # One clinician, one patient, two clinics: two links. A second at the same clinic is refused.
    assert sql(f"""SELECT string_agg(clinic_id::text, ',' ORDER BY clinic_id) FROM care_teams
      WHERE patient_id='{PATIENT}' AND clinician_id='{OTHER}' AND status='active'""") == (
        f"{CLINIC},{SECOND_CLINIC}"
    )
    error = sql(
        f"""SET ROLE service_role; UPDATE care_teams SET patient_id='{PATIENT}', status='active'
      WHERE invite_code='LEGACY02';""",
        succeeds=False,
    )
    assert "care_teams_patient_clinician_clinic_key" in error


# ── Compatibility mirror ───────────────────────────────────────────────────────────────


def test_legacy_clinic_and_role_changes_keep_memberships_in_step(sql):
    second_clinic(sql)
    joined = new_clinician(sql, clinic=CLINIC, role="nurse")
    assert memberships(sql, joined) == [(CLINIC, "nurse", "active")]

    sql(f"SET ROLE service_role; UPDATE clinicians SET role='admin' WHERE id='{joined}';")
    assert memberships(sql, joined) == [(CLINIC, "admin", "active")]

    # Profile clinic change or invitation acceptance moves the clinician.
    sql(
        f"SET ROLE service_role; UPDATE clinicians SET clinic_id='{SECOND_CLINIC}' WHERE id='{joined}';"
    )
    assert memberships(sql, joined) == [
        (CLINIC, "admin", "inactive"),
        (SECOND_CLINIC, "admin", "active"),
    ]

    # Staff removal detaches the clinician.
    sql(f"SET ROLE service_role; UPDATE clinicians SET clinic_id=NULL WHERE id='{joined}';")
    assert [m[2] for m in memberships(sql, joined)] == ["inactive", "inactive"]

    sql(
        f"SET ROLE service_role; UPDATE clinicians SET clinic_id='{CLINIC}', role='provider' "
        f"WHERE id='{joined}';"
    )
    assert memberships(sql, joined) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "admin", "inactive"),
    ]
    # Exactly one active membership per clinician, equal to the legacy columns.
    assert (
        sql("""SELECT count(*) FROM clinicians c WHERE c.clinic_id IS NOT NULL AND
      (SELECT count(*) FROM clinic_memberships m WHERE m.clinician_id=c.id AND m.status='active'
         AND m.clinic_id=c.clinic_id AND m.role=c.role) <> 1""")
        == "0"
    )


def test_a_deleted_clinician_takes_their_memberships_with_them(sql):
    gone = new_clinician(sql, clinic=CLINIC)

    sql(f"DELETE FROM auth.users WHERE id='{gone}';")

    assert memberships(sql, gone) == []


# ── Access rules ───────────────────────────────────────────────────────────────────────


def test_access_is_still_the_care_team_link_and_membership_widens_nothing(sql):
    signed_in(sql)
    sql(f"""INSERT INTO medications(patient_id,name,dosage,frequency)
      VALUES('{PATIENT}','Synthetic medicine','1 tablet','daily');""")

    # The assigned clinician sees exactly the linked patient, as before 065.
    assert sql(as_user(CLINICIAN, "SELECT string_agg(id::text, ',') FROM patients")) == PATIENT
    assert sql(as_user(CLINICIAN, "SELECT count(*) FROM medications")) == "1"
    assert sql(as_user(CLINICIAN, f"SELECT private.is_assigned_clinician('{PATIENT}')")) == "t"
    # A member of the same clinic with no care-team link sees no patient.
    assert sql(as_user(OTHER, f"SELECT private.is_clinic_member('{CLINIC}')")) == "t"
    assert sql(as_user(OTHER, f"SELECT private.is_assigned_clinician('{PATIENT}')")) == "f"
    assert sql(as_user(OTHER, "SELECT count(*) FROM patients")) == "0"
    assert sql(as_user(OTHER, "SELECT count(*) FROM medications")) == "0"
    # Each clinician reads only their own memberships.
    assert (
        sql(as_user(OTHER, "SELECT string_agg(clinician_id::text, ',') FROM clinic_memberships"))
        == OTHER
    )
    assert sql(as_user(PATIENT, "SELECT count(*) FROM clinic_memberships")) == "0"
    assert sql(as_user(PATIENT, f"SELECT private.is_clinic_member('{CLINIC}')")) == "f"
    # A suspended clinic or an inactive membership is not membership.
    sql(f"UPDATE clinics SET status='suspended' WHERE id='{CLINIC}';")
    assert sql(as_user(OTHER, f"SELECT private.is_clinic_member('{CLINIC}')")) == "f"
    sql(f"UPDATE clinics SET status='active' WHERE id='{CLINIC}';")
    sql(f"UPDATE clinic_memberships SET status='inactive' WHERE clinician_id='{OTHER}';")
    assert sql(as_user(OTHER, f"SELECT private.is_clinic_member('{CLINIC}')")) == "f"


def test_no_policy_or_access_helper_reads_memberships(sql):
    assert (
        sql("""SELECT string_agg(policyname, ',') FROM pg_policies
      WHERE coalesce(qual,'') || coalesce(with_check,'') ~ '(clinic_memberships|is_clinic_member)'
         OR tablename = 'clinic_memberships'""")
        == "clinic_memberships_own_select"
    )
    assert (
        sql("""SELECT count(*) FROM pg_proc WHERE proname='is_assigned_clinician'
      AND prosrc ~ 'clinic_(id|memberships)|is_clinic_member'""")
        == "0"
    )


def test_memberships_are_written_only_by_the_service_role(sql):
    signed_in(sql)
    insert = (
        f"INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
        f"VALUES('{OTHER}','{CLINIC}','admin');"
    )

    assert "permission denied" in sql(as_user(OTHER, insert), succeeds=False)
    assert "permission denied" in sql(
        as_user(OTHER, f"UPDATE clinic_memberships SET role='admin' WHERE clinician_id='{OTHER}';"),
        succeeds=False,
    )
    assert "permission denied" in sql(
        "SET ROLE anon; SELECT count(*) FROM clinic_memberships;", succeeds=False
    )
    assert "permission denied" in sql(
        "SET ROLE service_role; DELETE FROM clinic_memberships;", succeeds=False
    )
    assert "permission denied" in sql(
        f"SET ROLE anon; SELECT private.is_clinic_member('{CLINIC}');", succeeds=False
    )


@pytest.mark.before_clinic_memberships
def test_a_signed_in_clinician_cannot_promote_or_move_themselves(sql):
    # Hosted Supabase grants browser roles table privileges by default; 065 itself must take
    # the write privileges back.
    sql("GRANT INSERT, UPDATE, DELETE ON clinicians TO authenticated, anon;")
    apply_clinic_memberships(sql)
    signed_in(sql)
    second_clinic(sql)
    before = memberships(sql, CLINICIAN)

    for statement in (
        f"UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';",
        f"UPDATE clinicians SET clinic_id='{SECOND_CLINIC}' WHERE id='{CLINICIAN}';",
        f"DELETE FROM clinicians WHERE id='{CLINICIAN}';",
    ):
        assert "permission denied for table clinicians" in sql(
            as_user(CLINICIAN, statement), succeeds=False
        )
    newcomer = str(uuid4())
    sql(f"INSERT INTO auth.users VALUES ('{newcomer}');")
    insert = (
        "INSERT INTO clinicians(id,email,first_name,last_name,specialty,clinic_name,clinic_id,role) "
        f"VALUES('{newcomer}','{newcomer}@synthetic.invalid','Synthetic','Staff','Synthetic',"
        f"'Synthetic clinic','{CLINIC}','admin');"
    )
    assert "permission denied for table clinicians" in sql(
        as_user(newcomer, insert), succeeds=False
    )
    assert "permission denied" in sql(
        f"SET ROLE anon; UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';", succeeds=False
    )

    assert memberships(sql, CLINICIAN) == before
    assert memberships(sql, newcomer) == []
    assert sql(f"SELECT role FROM clinicians WHERE id='{CLINICIAN}'") == "provider"
    # Reading one's own row is unchanged.
    assert sql(as_user(CLINICIAN, "SELECT count(*) FROM clinicians WHERE id=auth.uid()")) == "1"
    # The only SQL function that writes clinicians is for the service role alone.
    assert (
        sql(
            "SELECT has_function_privilege('authenticated',"
            "'public.clinician_email_invitation_operation(uuid,text,jsonb)','EXECUTE')"
        )
        == "f"
    )
    # Profile updates through the service role still work and stay mirrored.
    sql(
        f"SET ROLE service_role; UPDATE clinicians SET specialty='Synthetic cardiology', "
        f"role='nurse' WHERE id='{CLINICIAN}';"
    )
    assert sql(f"SELECT specialty FROM clinicians WHERE id='{CLINICIAN}'") == "Synthetic cardiology"
    assert memberships(sql, CLINICIAN) == [(CLINIC, "nurse", "active")]
