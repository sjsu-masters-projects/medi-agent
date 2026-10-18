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
    """Read auth.uid() from JWT claims. Table grants come from the harness's hosted defaults."""
    sql("""CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
        SELECT (nullif(current_setting('request.jwt.claims', true), '')::jsonb->>'sub')::uuid $$;
      GRANT USAGE ON SCHEMA auth TO authenticated;""")


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
    # The harness starts from hosted Supabase's default grants; 065 itself must take the write
    # privileges back.
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


# ── Slice B (066): one account, several clinics ───────────────────────────────────────


def clinic_op(sql, actor, action, payload=None, *, succeeds=True):
    data = json.dumps(payload or {}).replace("'", "''")
    out = sql(
        f"SET ROLE service_role; SELECT clinician_clinic_operation('{actor}','{action}','{data}');",
        succeeds=succeeds,
    )
    return json.loads(out) if succeeds else out


def code_of(sql, clinic):
    return sql(f"SELECT code FROM clinics WHERE id='{clinic}'")


def join(sql, clinician, clinic, role="nurse", **kwargs):
    payload = {"clinic_code": code_of(sql, clinic), "role": role}
    return clinic_op(sql, clinician, "join_code", payload, **kwargs)


def default_of(sql, clinician):
    return sql(f"SELECT clinic_id||'|'||role FROM clinicians WHERE id='{clinician}'")


def audit(sql, target):
    rows = sql(
        "SELECT clinic_id||'|'||action||'|'||coalesce(role::text,'-') "
        f"FROM clinic_membership_audit_events WHERE target_id='{target}' ORDER BY created_at"
    )
    return rows.splitlines()


def audit_full(sql, target):
    rows = sql(
        "SELECT actor_id||'|'||clinic_id||'|'||action||'|'||target_type||'|'||coalesce(role::text,'-') "
        f"FROM clinic_membership_audit_events WHERE target_id='{target}' ORDER BY created_at"
    )
    return [tuple(row.split("|")) for row in rows.splitlines()]


def as_service(statement):
    return f"SET ROLE service_role; {statement}"


def conversation(sql, actor, role, action, payload=None):
    data = json.dumps(payload or {})
    return json.loads(
        sql(
            as_service(
                f"SELECT care_conversation_operation('{actor}','{role}','{action}','{data}');"
            )
        )
    )


def test_joining_by_code_adds_a_membership_and_keeps_the_default_clinic(sql):
    second_clinic(sql)
    sql(as_service(f"UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';"))
    code = code_of(sql, SECOND_CLINIC)

    joined = clinic_op(
        sql, CLINICIAN, "join_code", {"clinic_code": f" {code.lower()} ", "role": "nurse"}
    )

    assert joined["status"] == "joined" and joined["clinic_id"] == SECOND_CLINIC
    assert joined["role"] == "nurse"
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "admin", "active"),
        (SECOND_CLINIC, "nurse", "active"),
    ]
    # The default clinic and the role held there are unchanged.
    assert default_of(sql, CLINICIAN) == f"{CLINIC}|admin"
    assert audit(sql, CLINICIAN) == [f"{SECOND_CLINIC}|joined_by_code|nurse"]
    listed = clinic_op(sql, CLINICIAN, "list")
    assert listed["default_clinic_id"] == CLINIC
    assert [(c["clinic_id"], c["role"]) for c in listed["clinics"]] == [
        (SECOND_CLINIC, "nurse"),
        (CLINIC, "admin"),
    ]

    # Already a member: nothing changes and nothing more is audited.
    again = join(sql, CLINICIAN, SECOND_CLINIC, role="provider")
    assert again["status"] == "already_member" and again["role"] == "nurse"
    assert len(audit(sql, CLINICIAN)) == 1


def test_an_open_code_never_grants_admin_or_reverses_a_removal(sql):
    second_clinic(sql)

    assert "invalid_role" in join(sql, CLINICIAN, SECOND_CLINIC, role="admin", succeeds=False)
    assert "clinic_code_invalid" in clinic_op(
        sql, CLINICIAN, "join_code", {"clinic_code": "NOPE0000", "role": "nurse"}, succeeds=False
    )
    sql(f"UPDATE clinics SET status='suspended' WHERE id='{SECOND_CLINIC}';")
    assert "clinic_code_inactive" in join(sql, CLINICIAN, SECOND_CLINIC, succeeds=False)
    sql(f"UPDATE clinics SET status='active' WHERE id='{SECOND_CLINIC}';")
    join(sql, CLINICIAN, SECOND_CLINIC)
    # The second clinic's admin removes the clinician; the open code cannot undo that.
    sql(
        as_service(
            "UPDATE clinic_memberships SET status='inactive' "
            f"WHERE clinician_id='{CLINICIAN}' AND clinic_id='{SECOND_CLINIC}';"
        )
    )
    assert "membership_inactive" in join(sql, CLINICIAN, SECOND_CLINIC, succeeds=False)
    assert [c["clinic_id"] for c in clinic_op(sql, CLINICIAN, "list")["clinics"]] == [CLINIC]
    # A suspended clinic is not offered by clinic pickers.
    sql(f"UPDATE clinics SET status='suspended' WHERE id='{CLINIC}';")
    assert clinic_op(sql, CLINICIAN, "list")["clinics"] == []


def test_a_first_clinic_joined_by_code_becomes_the_default(sql):
    second_clinic(sql)
    unattached = new_clinician(sql)

    join(sql, unattached, SECOND_CLINIC)

    assert default_of(sql, unattached) == f"{SECOND_CLINIC}|nurse"
    assert memberships(sql, unattached) == [(SECOND_CLINIC, "nurse", "active")]
    assert audit(sql, unattached) == [f"{SECOND_CLINIC}|joined_by_code|nurse"]


def test_a_changed_default_clinic_takes_that_clinics_role(sql):
    second_clinic(sql)
    sql(as_service(f"UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';"))
    join(sql, CLINICIAN, SECOND_CLINIC)

    # Removal from the default clinic moves the default to the remaining membership. Even a
    # write that names the old role cannot carry admin rights to the other clinic.
    sql(
        as_service(
            "UPDATE clinic_memberships SET status='inactive' "
            f"WHERE clinician_id='{CLINICIAN}' AND clinic_id='{CLINIC}'; "
            f"UPDATE clinicians SET clinic_id='{SECOND_CLINIC}', role='admin' "
            f"WHERE id='{CLINICIAN}';"
        )
    )

    assert default_of(sql, CLINICIAN) == f"{SECOND_CLINIC}|nurse"
    assert (
        sql(f"SELECT clinic_name FROM clinicians WHERE id='{CLINICIAN}'")
        == "Second synthetic clinic"
    )
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "admin", "inactive"),
        (SECOND_CLINIC, "nurse", "active"),
    ]


def test_clinic_operations_and_their_audit_are_backend_only(sql):
    signed_in(sql)
    assert "permission denied" in sql(
        as_user(CLINICIAN, f"SELECT clinician_clinic_operation('{CLINICIAN}','list','{{}}');"),
        succeeds=False,
    )
    assert "permission denied" in sql(
        as_user(CLINICIAN, "SELECT count(*) FROM clinic_membership_audit_events;"), succeeds=False
    )
    for statement in (
        "DELETE FROM clinic_membership_audit_events;",
        "UPDATE clinic_membership_audit_events SET role='admin';",
    ):
        assert "permission denied" in sql(as_service(statement), succeeds=False)


def invitation(sql, actor, action, payload, *, succeeds=True):
    data = json.dumps(payload).replace("'", "''")
    who = "NULL" if actor is None else f"'{actor}'"
    out = sql(
        as_service(f"SELECT clinician_email_invitation_operation({who},'{action}','{data}');"),
        succeeds=succeeds,
    )
    return json.loads(out) if succeeds else out


def email_invite(sql, admin, email, *, clinic=None, token="slice-b-token", role="nurse", **kwargs):
    payload = {"email": email, "role": role, "hash": token, "payload": {}}
    if clinic:
        payload["clinic_id"] = clinic
    return invitation(sql, admin, "create", payload, **kwargs)


def accept(sql, actor, email, token="slice-b-token"):
    return invitation(sql, actor, "accept", {"hash": token, "account_email": email})


def test_an_invitation_adds_a_clinic_to_an_account_that_has_one(sql):
    second_clinic(sql)
    admin = new_clinician(sql, clinic=SECOND_CLINIC, role="admin")
    sql(f"UPDATE clinicians SET email='one@example.com' WHERE id='{CLINICIAN}';")

    assert email_invite(sql, admin, "one@example.com", role="admin")["status"] == "queued"
    preview = invitation(sql, None, "preview", {"hash": "slice-b-token"})
    assert preview["clinic_name"] == "Second synthetic clinic"
    accepted = accept(sql, CLINICIAN, "one@example.com")

    assert accepted["status"] == "accepted" and accepted["clinic_id"] == SECOND_CLINIC
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "admin", "active"),
    ]
    # The default clinic and the role held there are unchanged: admin only at the second.
    assert default_of(sql, CLINICIAN) == f"{CLINIC}|provider"
    assert audit(sql, CLINICIAN) == [f"{SECOND_CLINIC}|joined_by_invitation|admin"]
    # Accepting again is idempotent; inviting a member again is refused.
    assert accept(sql, CLINICIAN, "one@example.com")["status"] == "accepted"
    assert len(audit(sql, CLINICIAN)) == 1
    assert "already_member" in email_invite(
        sql, admin, "one@example.com", token="again-token", succeeds=False
    )


def test_invitation_admin_rights_come_from_the_membership_at_that_clinic(sql):
    second_clinic(sql)
    # An admin at the second clinic only; the default clinic is the first.
    sql(
        as_service(
            "INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
            f"VALUES('{CLINICIAN}','{SECOND_CLINIC}','admin');"
        )
    )

    # Without a clinic the default clinic is used, where they are a provider.
    assert "admin_required" in email_invite(
        sql, CLINICIAN, "a@example.com", token="t-1", succeeds=False
    )
    created = email_invite(sql, CLINICIAN, "a@example.com", clinic=SECOND_CLINIC, token="t-2")
    assert created["status"] == "queued"
    history = invitation(sql, CLINICIAN, "list", {"clinic_id": SECOND_CLINIC})["items"]
    assert [item["email"] for item in history] == ["a@example.com"]
    assert "admin_required" in invitation(
        sql, CLINICIAN, "list", {"clinic_id": CLINIC}, succeeds=False
    )
    # The invitation is valid for its clinic whatever the inviter's default clinic is.
    preview = invitation(sql, None, "preview", {"hash": "t-2"})
    assert preview["clinic_name"] == "Second synthetic clinic"
    # An admin of another clinic cannot revoke it and learns nothing about it.
    other_admin = new_clinician(sql, clinic=CLINIC, role="admin")
    assert "invitation_unavailable" in invitation(
        sql, other_admin, "revoke", {"id": created["invitation_id"]}, succeeds=False
    )
    revoked = invitation(sql, CLINICIAN, "revoke", {"id": created["invitation_id"]})
    assert revoked["status"] == "revoked"
    # Losing the admin membership withdraws the right to invite there.
    sql(
        as_service(
            "UPDATE clinic_memberships SET role='provider' "
            f"WHERE clinician_id='{CLINICIAN}' AND clinic_id='{SECOND_CLINIC}';"
        )
    )
    assert "admin_required" in invitation(
        sql, CLINICIAN, "list", {"clinic_id": SECOND_CLINIC}, succeeds=False
    )


def test_a_second_clinic_link_has_its_own_clinic_tagged_conversation(sql):
    second_clinic(sql)
    join(sql, CLINICIAN, SECOND_CLINIC)
    link(sql, CLINICIAN, patient=FOREIGN, clinic=SECOND_CLINIC)
    recipient = {"recipient_id": CLINICIAN}

    thread = conversation(sql, FOREIGN, "patient", "open", recipient)
    recipients = conversation(sql, FOREIGN, "patient", "recipients")

    # The thread and the recipient carry the link's clinic and the role held there.
    assert thread["clinic_name"] == "Second synthetic clinic"
    assert [(r["clinic_name"], r["role"]) for r in recipients] == [
        ("Second synthetic clinic", "nurse")
    ]
    # One list holds the clinician's threads from both clinics.
    first = conversation(sql, PATIENT, "patient", "open", recipient)
    assert first["clinic_name"] == "Synthetic clinic"
    listed = conversation(sql, CLINICIAN, "clinician", "list")
    assert {t["id"] for t in listed} == {thread["id"], first["id"]}
    # Removal from the second clinic closes only that clinic's thread.
    sql(
        as_service(
            "UPDATE clinic_memberships SET status='inactive' "
            f"WHERE clinician_id='{CLINICIAN}' AND clinic_id='{SECOND_CLINIC}';"
        )
    )
    assert [t["id"] for t in conversation(sql, CLINICIAN, "clinician", "list")] == [first["id"]]


# ── Slice B: admin actions run in the clinic named in the request ──────────────────────


def staff_op(sql, actor, action, clinic, member, role=None, *, succeeds=True):
    payload = {"clinic_id": clinic, "member_id": member}
    if role:
        payload["role"] = role
    return clinic_op(sql, actor, action, payload, succeeds=succeeds)


def two_clinic_admin(sql):
    """CLINICIAN: provider by default at CLINIC, admin at SECOND_CLINIC; OTHER at both."""
    second_clinic(sql)
    sql(
        as_service(
            "INSERT INTO clinic_memberships(clinician_id,clinic_id,role) VALUES "
            f"('{CLINICIAN}','{SECOND_CLINIC}','admin'),('{OTHER}','{SECOND_CLINIC}','nurse');"
        )
    )


def test_an_admin_at_one_clinic_cannot_act_on_another(sql):
    two_clinic_admin(sql)

    # CLINICIAN is an admin at the second clinic only; at the first they are a provider.
    for action, role in (("set_member_role", "admin"), ("remove_member", None)):
        assert "admin_required" in staff_op(
            sql, CLINICIAN, action, CLINIC, OTHER, role, succeeds=False
        )
    assert memberships(sql, OTHER) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "nurse", "active"),
    ]
    # A clinic the actor does not belong to, and a member who is not at that clinic.
    third = str(uuid4())
    sql(f"INSERT INTO clinics(id,display_name,canonical_name) VALUES('{third}','Third','third');")
    assert "admin_required" in staff_op(
        sql, CLINICIAN, "remove_member", third, OTHER, succeeds=False
    )
    stranger = new_clinician(sql, clinic=CLINIC)
    assert "member_unavailable" in staff_op(
        sql, CLINICIAN, "remove_member", SECOND_CLINIC, stranger, succeeds=False
    )
    assert "self_change" in staff_op(
        sql, CLINICIAN, "set_member_role", SECOND_CLINIC, CLINICIAN, "nurse", succeeds=False
    )
    assert "clinic_unavailable" in staff_op(
        sql, CLINICIAN, "remove_member", str(uuid4()), OTHER, succeeds=False
    )


def test_a_role_change_at_one_clinic_never_reaches_another(sql):
    two_clinic_admin(sql)

    result = staff_op(sql, CLINICIAN, "set_member_role", SECOND_CLINIC, OTHER, "admin")

    assert result["role"] == "admin"
    assert memberships(sql, OTHER) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "admin", "active"),
    ]
    # OTHER's default clinic is the first: their legacy role there is untouched.
    assert default_of(sql, OTHER) == f"{CLINIC}|provider"
    assert audit_full(sql, OTHER) == [
        (CLINICIAN, SECOND_CLINIC, "member_role_changed", "clinician", "admin")
    ]


def test_removal_from_the_default_clinic_keeps_the_others(sql):
    second_clinic(sql)
    admin = new_clinician(sql, clinic=CLINIC, role="admin")
    sql(
        as_service(
            "INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
            f"VALUES('{OTHER}','{SECOND_CLINIC}','nurse');"
        )
    )

    staff_op(sql, admin, "remove_member", CLINIC, OTHER)

    assert memberships(sql, OTHER) == [
        (CLINIC, "provider", "inactive"),
        (SECOND_CLINIC, "nurse", "active"),
    ]
    # The remaining clinic becomes the default, with the role held there.
    assert default_of(sql, OTHER) == f"{SECOND_CLINIC}|nurse"
    assert audit_full(sql, OTHER) == [(admin, CLINIC, "member_removed", "clinician", "provider")]

    # Removal from the last clinic leaves no default, as staff removal did before.
    second_admin = new_clinician(sql, clinic=SECOND_CLINIC, role="admin")
    staff_op(sql, second_admin, "remove_member", SECOND_CLINIC, OTHER)
    assert (
        sql(f"SELECT coalesce(clinic_id::text,'none') FROM clinicians WHERE id='{OTHER}'") == "none"
    )
    assert [m[2] for m in memberships(sql, OTHER)] == ["inactive", "inactive"]
    # No default clinic means no clinic-scoped role: a stale admin never remains.
    assert sql(f"SELECT role FROM clinicians WHERE id='{OTHER}'") == "provider"


def test_removing_an_admin_from_their_last_clinic_resets_the_role(sql):
    admin = new_clinician(sql, clinic=CLINIC, role="admin")
    other_admin = new_clinician(sql, clinic=CLINIC, role="admin")
    staff_op(sql, admin, "remove_member", CLINIC, other_admin)
    assert (
        sql(
            f"SELECT coalesce(clinic_id::text,'none')||'|'||role FROM clinicians WHERE id='{other_admin}'"
        )
        == "none|provider"
    )
    assert sql("SELECT count(*) FROM clinicians WHERE clinic_id IS NULL AND role='admin'") == "0"


def test_the_deployed_backends_direct_writes_still_keep_memberships_in_step(sql):
    """The previous backend changes roles and removes staff by updating clinicians directly.

    Those writes are mirrored into memberships. They are not audited: the trigger sees no
    actor, and the audit trail records only the RPC paths and signup, so the count is unchanged.
    """
    staff = new_clinician(sql, clinic=CLINIC, role="nurse")
    audited = sql("SELECT count(*) FROM clinic_membership_audit_events")

    sql(f"SET ROLE service_role; UPDATE clinicians SET role='admin' WHERE id='{staff}';")
    assert memberships(sql, staff) == [(CLINIC, "admin", "active")]

    sql(f"SET ROLE service_role; UPDATE clinicians SET clinic_id=NULL WHERE id='{staff}';")
    assert memberships(sql, staff) == [(CLINIC, "admin", "inactive")]

    assert sql("SELECT count(*) FROM clinic_membership_audit_events") == audited


# ── Slice B: the audit trail ───────────────────────────────────────────────────────────


def test_every_membership_change_and_clinic_action_is_audited(sql):
    second_clinic(sql)
    admin = new_clinician(sql, clinic=SECOND_CLINIC, role="admin")
    # Signup with a clinic: the account itself is the actor.
    assert audit_full(sql, admin) == [
        (admin, SECOND_CLINIC, "joined_at_signup", "clinician", "admin")
    ]
    # A patient invite code: the issuing clinician and the code's clinic.
    code_row = invite(sql, CLINICIAN, "AUDIT001")
    assert audit_full(sql, code_row) == [
        (CLINICIAN, CLINIC, "patient_invite_code_created", "care_team", "-")
    ]
    # Email invitations: create, then revoke.
    created = email_invite(sql, admin, "audit@example.com", token="audit-token")
    invitation(sql, admin, "revoke", {"id": created["invitation_id"]})
    assert audit_full(sql, created["invitation_id"]) == [
        (admin, SECOND_CLINIC, "email_invitation_created", "invitation", "nurse"),
        (admin, SECOND_CLINIC, "email_invitation_revoked", "invitation", "-"),
    ]
    # No name or email address is stored anywhere in the trail.
    columns = sql(
        "SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns "
        "WHERE table_name='clinic_membership_audit_events'"
    )
    assert columns == "action,actor_id,clinic_id,created_at,id,role,target_id,target_type"
    assert "@" not in sql(
        "SELECT string_agg(row_to_json(e)::text, '') FROM clinic_membership_audit_events e"
    )


def test_the_audit_trail_is_append_only_for_every_role(sql):
    second_clinic(sql)
    new_clinician(sql, clinic=SECOND_CLINIC)
    signed_in(sql)

    for statement in (
        "UPDATE clinic_membership_audit_events SET role='admin';",
        "DELETE FROM clinic_membership_audit_events;",
        "TRUNCATE clinic_membership_audit_events;",
    ):
        # The service role has no such privilege; even the owner is stopped by the trigger.
        assert "permission denied" in sql(as_service(statement), succeeds=False)
        assert "append-only" in sql(statement, succeeds=False)
        assert "permission denied" in sql(as_user(CLINICIAN, statement), succeeds=False)
    insert = (
        "INSERT INTO clinic_membership_audit_events(actor_id,clinic_id,action,target_type,target_id) "
        f"VALUES('{CLINICIAN}','{CLINIC}','joined_by_code','clinician','{CLINICIAN}');"
    )
    for role in ("authenticated", "anon"):
        assert "permission denied" in sql(f"SET ROLE {role}; {insert}", succeeds=False)
        assert "permission denied" in sql(
            f"SET ROLE {role}; SELECT count(*) FROM clinic_membership_audit_events;", succeeds=False
        )
    assert sql("SELECT count(*) FROM clinic_membership_audit_events") == "1"


def test_browser_roles_cannot_write_clinicians_memberships_or_the_audit(sql):
    signed_in(sql)
    for role in ("anon", "authenticated"):
        for table in ("clinicians", "clinic_memberships", "clinic_membership_audit_events"):
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert (
                    sql(f"SELECT has_table_privilege('{role}','{table}','{privilege}')") == "f"
                ), (role, table, privilege)
    assert "permission denied" in sql(
        as_user(
            CLINICIAN,
            f"UPDATE clinic_memberships SET role='admin' WHERE clinician_id='{CLINICIAN}';",
        ),
        succeeds=False,
    )


# ── Slice D (067): default clinic, leaving a clinic, and clinic settings ─────────────────


def two_clinics(sql, role_at_second="nurse"):
    """CLINICIAN is a provider at CLINIC (the default) and holds ``role_at_second`` at the other."""
    second_clinic(sql)
    sql(
        as_service(
            "INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
            f"VALUES ('{CLINICIAN}','{SECOND_CLINIC}','{role_at_second}');"
        )
    )


def test_make_default_ends_no_membership_and_is_audited(sql):
    two_clinics(sql)

    made = clinic_op(sql, CLINICIAN, "set_default", {"clinic_id": SECOND_CLINIC})

    assert made["default_clinic_id"] == SECOND_CLINIC and made["role"] == "nurse"
    # The role and name follow the membership; the old default stays an active membership.
    assert default_of(sql, CLINICIAN) == f"{SECOND_CLINIC}|nurse"
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "nurse", "active"),
    ]
    assert audit_full(sql, CLINICIAN) == [
        (CLINICIAN, SECOND_CLINIC, "default_clinic_changed", "clinician", "nurse")
    ]
    # Choosing the current default again changes and audits nothing.
    clinic_op(sql, CLINICIAN, "set_default", {"clinic_id": SECOND_CLINIC})
    assert len(audit(sql, CLINICIAN)) == 1
    # A clinic without an active membership cannot be made the default.
    third = str(uuid4())
    sql(f"INSERT INTO clinics(id,display_name,canonical_name) VALUES('{third}','Third','third');")
    assert "clinic_unavailable" in clinic_op(
        sql, CLINICIAN, "set_default", {"clinic_id": third}, succeeds=False
    )
    assert default_of(sql, CLINICIAN) == f"{SECOND_CLINIC}|nurse"


def test_a_legacy_move_of_the_default_still_ends_the_old_membership(sql):
    second_clinic(sql)

    sql(f"UPDATE clinicians SET clinic_id='{SECOND_CLINIC}' WHERE id='{CLINICIAN}';")

    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "provider", "inactive"),
        (SECOND_CLINIC, "provider", "active"),
    ]


def test_leaving_ends_the_membership_and_only_the_callers_links_there(sql):
    two_clinics(sql)
    mine = link(sql, CLINICIAN, patient=FOREIGN, clinic=SECOND_CLINIC)
    pending = str(uuid4())
    sql(
        f"""INSERT INTO care_teams(id,clinician_id,role,status,invite_code,clinic_id)
      VALUES('{pending}','{CLINICIAN}','provider','pending','LEAVE001','{SECOND_CLINIC}');"""
    )
    colleague = link(sql, OTHER, patient=FOREIGN, clinic=CLINIC)
    default_link = sql(
        f"SELECT id FROM care_teams WHERE clinician_id='{CLINICIAN}' AND clinic_id='{CLINIC}' "
        "AND patient_id IS NOT NULL"
    )

    left = clinic_op(sql, CLINICIAN, "leave", {"clinic_id": SECOND_CLINIC})

    assert left["status"] == "left" and left["links_ended"] == 1
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "provider", "active"),
        (SECOND_CLINIC, "nurse", "inactive"),
    ]
    status = lambda team: sql(f"SELECT status FROM care_teams WHERE id='{team}'")  # noqa: E731
    assert (status(mine), status(pending)) == ("inactive", "inactive")
    # Another clinician's link at the clinic, and the caller's links elsewhere, are untouched.
    assert status(colleague) == "active" and status(default_link) == "active"
    # Nothing is deleted.
    assert sql("SELECT count(*) FROM patients") == "2"
    ended = [
        a[2:] for a in audit_full(sql, mine) + audit_full(sql, pending) if a[2] == "care_link_ended"
    ]
    assert ended == [("care_link_ended", "care_team", "-")] * 2
    assert audit_full(sql, CLINICIAN)[-1] == (
        CLINICIAN,
        SECOND_CLINIC,
        "member_left",
        "clinician",
        "nurse",
    )
    # Leaving a clinic again, or one never joined, is refused.
    assert "clinic_unavailable" in clinic_op(
        sql, CLINICIAN, "leave", {"clinic_id": SECOND_CLINIC}, succeeds=False
    )


def test_removal_ends_the_removed_members_links_at_that_clinic_only(sql):
    two_clinics(sql)
    admin = new_clinician(sql, clinic=CLINIC, role="admin")
    mine = link(sql, CLINICIAN, patient=FOREIGN, clinic=CLINIC)
    elsewhere = link(sql, CLINICIAN, patient=PATIENT, clinic=SECOND_CLINIC)
    colleague = link(sql, OTHER, patient=FOREIGN, clinic=CLINIC)
    pending = str(uuid4())
    sql(
        f"""INSERT INTO care_teams(id,clinician_id,role,status,invite_code,clinic_id)
      VALUES('{pending}','{CLINICIAN}','provider','pending','REMOVE001','{CLINIC}');"""
    )

    removed = staff_op(sql, admin, "remove_member", CLINIC, CLINICIAN)

    assert removed["status"] == "removed" and removed["links_ended"] >= 1
    status = lambda team: sql(f"SELECT status FROM care_teams WHERE id='{team}'")  # noqa: E731
    assert (status(mine), status(pending)) == ("inactive", "inactive")
    assert status(elsewhere) == "active" and status(colleague) == "active"
    # The removed member's roster is what they still hold at their other clinic.
    roster = sql(
        f"SELECT string_agg(patient_id::text, ',') FROM care_teams WHERE clinician_id='{CLINICIAN}' "
        "AND status='active' AND patient_id IS NOT NULL"
    )
    assert roster == PATIENT
    ended = [
        a for a in audit_full(sql, mine) + audit_full(sql, pending) if a[2] == "care_link_ended"
    ]
    assert [a[0] for a in ended] == [admin, admin]
    assert audit_full(sql, CLINICIAN)[-1][2] == "member_removed"


def test_leaving_the_default_clinic_moves_the_default(sql):
    two_clinics(sql)

    clinic_op(sql, CLINICIAN, "leave", {"clinic_id": CLINIC})

    assert default_of(sql, CLINICIAN) == f"{SECOND_CLINIC}|nurse"
    assert memberships(sql, CLINICIAN) == [
        (CLINIC, "provider", "inactive"),
        (SECOND_CLINIC, "nurse", "active"),
    ]


def test_the_last_clinic_and_the_sole_admin_cannot_leave(sql):
    second_clinic(sql)
    # One clinic only.
    assert "last_clinic" in clinic_op(
        sql, CLINICIAN, "leave", {"clinic_id": CLINIC}, succeeds=False
    )
    # The sole admin of a clinic, who belongs to another clinic as well.
    admin = new_clinician(sql, clinic=CLINIC, role="admin")
    sql(
        as_service(
            f"INSERT INTO clinic_memberships(clinician_id,clinic_id,role) "
            f"VALUES ('{admin}','{SECOND_CLINIC}','provider');"
        )
    )
    assert "sole_admin" in clinic_op(sql, admin, "leave", {"clinic_id": CLINIC}, succeeds=False)
    # With a second admin they may leave.
    sql(
        as_service(
            f"UPDATE clinic_memberships SET role='admin' WHERE clinician_id='{CLINICIAN}' "
            f"AND clinic_id='{CLINIC}';"
        )
    )
    clinic_op(sql, admin, "leave", {"clinic_id": CLINIC})
    assert (CLINIC, "admin", "inactive") in memberships(sql, admin)
    assert default_of(sql, admin) == f"{SECOND_CLINIC}|provider"
    # Refusals audit nothing.
    assert [a[2] for a in audit_full(sql, admin)].count("member_left") == 1


def test_only_that_clinics_admin_can_rename_it(sql):
    two_clinics(sql, role_at_second="admin")
    other_name = "Another synthetic clinic"
    sql(
        f"INSERT INTO clinics(id,display_name,canonical_name) "
        f"VALUES('{uuid4()}','{other_name}','{other_name.lower()}');"
    )

    renamed = clinic_op(
        sql,
        CLINICIAN,
        "update_clinic",
        {"clinic_id": SECOND_CLINIC, "display_name": "  Renamed   Clinic "},
    )

    assert renamed["clinic_name"] == "Renamed Clinic"
    assert sql(
        f"SELECT display_name||'|'||canonical_name FROM clinics WHERE id='{SECOND_CLINIC}'"
    ) == ("Renamed Clinic|renamed clinic")
    assert audit_full(sql, SECOND_CLINIC) == [
        (CLINICIAN, SECOND_CLINIC, "clinic_renamed", "clinic", "admin")
    ]
    # A provider at the first clinic cannot rename it; neither can a non-member.
    assert "admin_required" in clinic_op(
        sql,
        CLINICIAN,
        "update_clinic",
        {"clinic_id": CLINIC, "display_name": "Nope"},
        succeeds=False,
    )
    assert "clinic_unavailable" in clinic_op(
        sql,
        new_clinician(sql, clinic=CLINIC),
        "update_clinic",
        {"clinic_id": SECOND_CLINIC, "display_name": "Nope"},
        succeeds=False,
    )
    assert "clinic_name_taken" in clinic_op(
        sql,
        CLINICIAN,
        "update_clinic",
        {"clinic_id": SECOND_CLINIC, "display_name": other_name.upper()},
        succeeds=False,
    )
    assert "invalid_name" in clinic_op(
        sql,
        CLINICIAN,
        "update_clinic",
        {"clinic_id": SECOND_CLINIC, "display_name": " x "},
        succeeds=False,
    )


def test_the_new_audit_actions_keep_the_trail_append_only_and_backend_only(sql):
    two_clinics(sql)
    clinic_op(sql, CLINICIAN, "set_default", {"clinic_id": SECOND_CLINIC})
    signed_in(sql)
    for statement in (
        "UPDATE clinic_membership_audit_events SET role='admin';",
        "DELETE FROM clinic_membership_audit_events;",
    ):
        assert "append-only" in sql(statement, succeeds=False)
        assert "permission denied" in sql(as_user(CLINICIAN, statement), succeeds=False)
    # An action outside the vocabulary is still refused by the table.
    assert "violates check constraint" in sql(
        "INSERT INTO clinic_membership_audit_events(actor_id,clinic_id,action,target_type,target_id) "
        f"VALUES('{CLINICIAN}','{CLINIC}','made_up','clinic','{CLINIC}');",
        succeeds=False,
    )
    for name in ("set_default", "leave", "update_clinic"):
        assert "permission denied" in sql(
            f"SET ROLE authenticated; SELECT clinician_clinic_operation('{CLINICIAN}','{name}','{{}}');",
            succeeds=False,
        )


def test_invitation_admin_rights_do_not_read_clinicians_role(sql):
    """Admin at a non-default clinic invites there while the legacy role says provider."""
    two_clinics(sql, role_at_second="admin")
    assert sql(f"SELECT role FROM clinicians WHERE id='{CLINICIAN}'") == "provider"

    created = email_invite(sql, CLINICIAN, "member-admin@example.com", clinic=SECOND_CLINIC)

    assert created["status"] == "queued"
    assert "admin_required" in email_invite(
        sql, CLINICIAN, "member-two@example.com", clinic=CLINIC, token="t2", succeeds=False
    )
