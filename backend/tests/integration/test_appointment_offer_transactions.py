"""Real offer migrations on a disposable synthetic PostgreSQL cluster, never Supabase."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "src/app/db/migrations"


@pytest.fixture(scope="module")
def offer_db(tmp_path_factory):
    if any(shutil.which(tool) is None for tool in ("initdb", "pg_ctl", "psql")):
        pytest.skip("Local PostgreSQL binaries required for transaction tests")
    if not (Path(shutil.which("initdb")).resolve().parent / "postgres").exists():
        pytest.skip("PostgreSQL installation contains client tools only")
    base = tmp_path_factory.mktemp("offer-postgres")
    data = base / "data"
    # macOS pytest paths exceed the Unix socket filename limit.
    socket = Path(tempfile.mkdtemp(prefix="offer-pg-", dir="/tmp"))
    subprocess.run(
        ["initdb", "-D", str(data), "-A", "trust", "-U", "postgres"],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        [
            "pg_ctl",
            "-D",
            str(data),
            "-l",
            str(base / "server.log"),
            "-o",
            f"-k {socket} -h ''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )

    def sql(source, *, checked=True):
        result = subprocess.run(
            [
                "psql",
                "-X",
                "-h",
                str(socket),
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atq",
            ],
            input=source,
            capture_output=True,
            text=True,
            timeout=20,
            env={k: v for k, v in os.environ.items() if not k.startswith("PG")},
        )
        if checked:
            assert result.returncode == 0, result.stderr
        return result

    try:
        # Use the production appointments DDL. Unrelated parents and Auth helpers
        # are minimal stubs; restrictive group policies and function grants are real.
        initial = (MIGRATIONS / "001_initial_schema.sql").read_text()
        enums = "\n".join(
            re.findall(r"CREATE TYPE appointment_(?:type|status)_enum AS ENUM \([^;]+;", initial)
        )
        table = re.search(r"CREATE TABLE appointments \([\s\S]+?\n\);", initial)[0]
        security = (MIGRATIONS / "020_harden_database_security.sql").read_text()
        helpers = "\n".join(
            match.group(0)
            for match in re.finditer(
                r"CREATE OR REPLACE FUNCTION private\.(?:is_clinician|is_assigned_clinician)\([\s\S]+?\$\$;",
                security,
            )
        )
        sql(f"""
            CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
            CREATE SCHEMA auth;
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT nullif(current_setting('test.actor', true), '')::uuid $$;
            CREATE SCHEMA private;
            CREATE TABLE patients(id uuid PRIMARY KEY);
            CREATE TABLE clinicians(id uuid PRIMARY KEY, first_name text, last_name text);
            CREATE TABLE care_teams(id uuid PRIMARY KEY, patient_id uuid REFERENCES patients, clinician_id uuid REFERENCES clinicians, status text);
            CREATE TABLE documents(id uuid PRIMARY KEY);
            {enums} {table}
            {helpers}
            REVOKE ALL ON SCHEMA private FROM PUBLIC;
            GRANT USAGE ON SCHEMA private TO authenticated;
            REVOKE ALL ON FUNCTION private.is_clinician(), private.is_assigned_clinician(uuid) FROM PUBLIC;
            GRANT EXECUTE ON FUNCTION private.is_clinician(), private.is_assigned_clinician(uuid) TO authenticated;
            ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
            CREATE POLICY test_read ON appointments FOR SELECT TO authenticated USING (true);
            CREATE POLICY test_write ON appointments FOR UPDATE TO authenticated USING (true);
            CREATE POLICY test_insert ON appointments FOR INSERT TO authenticated WITH CHECK (true);
            GRANT USAGE ON SCHEMA public, auth TO authenticated, service_role;
            GRANT SELECT, INSERT, UPDATE ON appointments TO authenticated;
            GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO service_role;
        """)
        for name in [
            "038_appointment_proposal_lifecycle.sql",
            "039_appointment_patient_changes.sql",
            "040_appointment_offer_groups.sql",
            "041_atomic_appointment_offers.sql",
            "042_appointment_expired_status.sql",
            "043_appointment_booking_guards.sql",
        ]:
            if name == "043_appointment_booking_guards.sql":
                patient, clinician, team = (str(uuid4()) for _ in range(3))
                sql(
                    f"INSERT INTO patients VALUES ('{patient}'); INSERT INTO clinicians VALUES ('{clinician}', 'Synthetic', 'Backfill'); INSERT INTO care_teams VALUES ('{team}', '{patient}', '{clinician}', 'active'); INSERT INTO appointments(patient_id, care_team_id, scheduled_at, status, created_at, reason) VALUES ('{patient}', '{team}', now() + interval '1 day', 'proposed', now() - interval '8 days', 'Synthetic pre-Slice-5 offer');"
                )
            sql("BEGIN;\n" + (MIGRATIONS / name).read_text() + "\nCOMMIT;")
        yield sql
    finally:
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        shutil.rmtree(socket)


def create_offer(sql):
    patient, clinician, team = (str(uuid4()) for _ in range(3))
    sql(
        f"INSERT INTO patients VALUES ('{patient}'); INSERT INTO clinicians VALUES ('{clinician}', 'Synthetic', 'Clinician'); INSERT INTO care_teams VALUES ('{team}', '{patient}', '{clinician}', 'active');"
    )
    result = sql(
        f"SET ROLE service_role; SELECT propose_appointment_slots('{clinician}', '{team}', ARRAY[now() + interval '10 days', now() + interval '11 days', now() + interval '12 days'], 30, 'follow_up', 'Telehealth', 'Synthetic follow-up');"
    )
    return patient, clinician, team, json.loads(result.stdout)["appointments"]


def respond(sql, actor, row, action, note="NULL", *, checked=True):
    return sql(
        f"SET ROLE service_role; SELECT respond_to_appointment_offer('{actor}', '{row['id']}', '{action}', {note});",
        checked=checked,
    )


def test_accept_is_atomic_audited_and_isolated(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    _, _, _, other = create_offer(offer_db)
    assert (
        json.loads(respond(offer_db, patient, rows[1], "accept").stdout)["appointment"]["status"]
        == "confirmed"
    )
    group = rows[0]["proposal_group_id"]
    assert offer_db(
        f"SELECT status FROM appointments WHERE proposal_group_id = '{group}' ORDER BY scheduled_at;"
    ).stdout.splitlines() == ["withdrawn", "confirmed", "withdrawn"]
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE proposal_group_id = '{other[0]['proposal_group_id']}' AND status = 'proposed';"
        ).stdout.strip()
        == "3"
    )
    assert (
        offer_db(
            f"SELECT count(*) FROM appointment_offer_events WHERE proposal_group_id = '{group}';"
        ).stdout.strip()
        == "6"
    )
    assert json.loads(respond(offer_db, patient, rows[0], "accept").stdout)["error"] == "stale"
    assert (
        json.loads(respond(offer_db, patient, rows[1], "cancel").stdout)["appointment"]["status"]
        == "cancelled"
    )


@pytest.mark.parametrize(
    "action,new_status", [("decline", "declined"), ("request_alternative", "alternative_requested")]
)
def test_group_responses_change_all_slots_and_store_note(offer_db, action, new_status):
    patient, _, _, rows = create_offer(offer_db)
    respond(offer_db, patient, rows[0], action, "'  Afternoons please  '")
    assert (
        offer_db(
            f"SELECT status || ':' || patient_note FROM appointments WHERE proposal_group_id = '{rows[0]['proposal_group_id']}';"
        ).stdout.splitlines()
        == [f"{new_status}:Afternoons please"] * 3
    )


def test_concurrent_accepts_confirm_only_one_slot(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda row: json.loads(
                    offer_db(
                        f"BEGIN; SET ROLE service_role; SELECT respond_to_appointment_offer('{patient}', '{row['id']}', 'accept', NULL); SELECT pg_sleep(0.15); COMMIT;"
                    ).stdout
                ),
                rows[:2],
            )
        )
    assert sum("appointment" in r for r in results) == 1
    assert sum(r.get("error") == "stale" for r in results) == 1


def test_denials_direct_writes_and_append_only_audit(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    assert (
        json.loads(respond(offer_db, str(uuid4()), rows[0], "accept").stdout)["error"]
        == "forbidden"
    )
    assert json.loads(respond(offer_db, patient, rows[0], "cancel").stdout)["error"] == "stale"
    denied = offer_db(
        f"SET ROLE authenticated; SELECT respond_to_appointment_offer('{patient}', '{rows[0]['id']}', 'accept', NULL);",
        checked=False,
    )
    assert denied.returncode != 0 and "permission denied" in denied.stderr
    offer_db(
        f"SET ROLE authenticated; UPDATE appointments SET status = 'confirmed' WHERE id = '{rows[0]['id']}';"
    )
    assert (
        offer_db(f"SELECT status FROM appointments WHERE id = '{rows[0]['id']}';").stdout.strip()
        == "proposed"
    )
    denied = offer_db(
        f"SET ROLE authenticated; INSERT INTO appointments(patient_id, care_team_id, scheduled_at, proposal_group_id) SELECT patient_id, care_team_id, now() + interval '1 day', proposal_group_id FROM appointments WHERE id = '{rows[0]['id']}';",
        checked=False,
    )
    assert denied.returncode != 0 and "row-level security" in denied.stderr
    denied = offer_db(
        f"UPDATE appointment_offer_events SET action = 'accept' WHERE appointment_id = '{rows[0]['id']}';",
        checked=False,
    )
    assert denied.returncode != 0 and "append-only" in denied.stderr


def test_audit_failure_rolls_back_slot_changes(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    offer_db(
        "CREATE FUNCTION test_reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic audit failure'; END $$; CREATE TRIGGER test_audit_failure BEFORE INSERT ON appointment_offer_events FOR EACH ROW EXECUTE FUNCTION test_reject_audit();"
    )
    try:
        result = respond(offer_db, patient, rows[0], "accept", checked=False)
        assert result.returncode != 0 and "synthetic audit failure" in result.stderr
        assert (
            offer_db(
                f"SELECT count(*) FROM appointments WHERE proposal_group_id = '{rows[0]['proposal_group_id']}' AND status = 'proposed';"
            ).stdout.strip()
            == "3"
        )
    finally:
        offer_db(
            "DROP TRIGGER test_audit_failure ON appointment_offer_events; DROP FUNCTION test_reject_audit();"
        )


def test_database_rechecks_assignment_and_distinct_slots(offer_db):
    _, clinician, team, _ = create_offer(offer_db)
    invalid = offer_db(
        f"SET ROLE service_role; SELECT propose_appointment_slots('{clinician}', '{team}', ARRAY[now() + interval '1 day', now() + interval '1 day'], 30, 'follow_up', NULL, NULL);"
    )
    assert json.loads(invalid.stdout)["error"] == "invalid"
    offer_db(f"UPDATE care_teams SET status = 'inactive' WHERE id = '{team}';")
    invalid = offer_db(
        f"SET ROLE service_role; SELECT propose_appointment_slots('{clinician}', '{team}', ARRAY[now() + interval '1 day', now() + interval '2 days'], 30, 'follow_up', NULL, NULL);"
    )
    assert json.loads(invalid.stdout)["error"] == "forbidden"


def additional_offer(sql, clinician, team, start):
    result = sql(
        f"SET ROLE service_role; SELECT propose_appointment_slots('{clinician}', '{team}', "
        f"ARRAY['{start}'::timestamptz, '{start}'::timestamptz + interval '1 day'], "
        "30, 'follow_up', NULL, 'Synthetic competing offer');"
    )
    return json.loads(result.stdout)["appointments"]


def test_separate_overlapping_offers_are_atomic_and_cancel_releases_time(offer_db):
    patient, clinician, team, rows = create_offer(offer_db)
    other = additional_offer(offer_db, clinician, team, rows[0]["scheduled_at"])
    respond(offer_db, patient, rows[0], "accept")
    assert json.loads(respond(offer_db, patient, other[0], "accept").stdout)["error"] == "conflict"
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE proposal_group_id = '{other[0]['proposal_group_id']}' AND status = 'proposed';"
        ).stdout.strip()
        == "2"
    )
    assert (
        offer_db(
            f"SELECT count(*) FROM appointment_offer_events WHERE proposal_group_id = '{other[0]['proposal_group_id']}' AND action = 'accept';"
        ).stdout.strip()
        == "0"
    )
    respond(offer_db, patient, rows[0], "cancel")
    assert (
        json.loads(respond(offer_db, patient, other[0], "accept").stdout)["appointment"]["status"]
        == "confirmed"
    )


@pytest.mark.parametrize("attempt", range(5))
def test_concurrent_accepts_across_groups_confirm_only_one_booking(offer_db, attempt):
    patient, clinician, team, rows = create_offer(offer_db)
    other = additional_offer(offer_db, clinician, team, rows[0]["scheduled_at"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda row: json.loads(
                    offer_db(
                        f"BEGIN; SET ROLE service_role; SELECT respond_to_appointment_offer('{patient}', '{row['id']}', 'accept', NULL); SELECT pg_sleep(0.15); COMMIT;"
                    ).stdout
                ),
                [rows[0], other[0]],
            )
        )
    assert sum("appointment" in result for result in results) == 1
    assert sum(result.get("error") == "conflict" for result in results) == 1
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE patient_id = '{patient}' AND status = 'confirmed';"
        ).stdout.strip()
        == "1"
    )


def insert_legacy(sql, patient, team, start, *, status="scheduled", checked=True):
    return sql(
        f"SET ROLE service_role; INSERT INTO appointments(patient_id, care_team_id, scheduled_at, status) "
        f"VALUES ('{patient}', '{team}', '{start}', '{status}') RETURNING row_to_json(appointments);",
        checked=checked,
    )


def test_partial_overlap_direct_insert_update_adjacent_and_patient_isolation(offer_db):
    patient, _, team, rows = create_offer(offer_db)
    respond(offer_db, patient, rows[0], "accept")
    start = rows[0]["scheduled_at"]
    overlap = offer_db(
        f"SET ROLE service_role; INSERT INTO appointments(patient_id, care_team_id, scheduled_at) VALUES ('{patient}', '{team}', '{start}'::timestamptz + interval '15 minutes');",
        checked=False,
    )
    assert overlap.returncode != 0 and "appointments_patient_no_overlap" in overlap.stderr
    adjacent = offer_db(
        f"SET ROLE service_role; INSERT INTO appointments(patient_id, care_team_id, scheduled_at) VALUES ('{patient}', '{team}', '{start}'::timestamptz + interval '30 minutes') RETURNING id;"
    ).stdout.strip()
    overlap = offer_db(
        f"SET ROLE service_role; UPDATE appointments SET scheduled_at = '{start}'::timestamptz + interval '29 minutes' WHERE id = '{adjacent}';",
        checked=False,
    )
    assert overlap.returncode != 0 and "appointments_patient_no_overlap" in overlap.stderr
    overlap = offer_db(
        f"SET ROLE service_role; UPDATE appointments SET duration_minutes = 31 WHERE id = '{rows[0]['id']}';",
        checked=False,
    )
    assert overlap.returncode != 0 and "appointments_patient_no_overlap" in overlap.stderr
    other_patient, _, other_team, _ = create_offer(offer_db)
    assert insert_legacy(offer_db, other_patient, other_team, start).returncode == 0


def test_legacy_acceptance_uses_atomic_guards_and_audit(offer_db):
    patient, _, team, rows = create_offer(offer_db)
    first = json.loads(
        insert_legacy(offer_db, patient, team, rows[0]["scheduled_at"], status="proposed").stdout
    )
    second = json.loads(
        insert_legacy(offer_db, patient, team, rows[0]["scheduled_at"], status="proposed").stdout
    )
    assert (
        json.loads(respond(offer_db, patient, first, "accept").stdout)["appointment"]["status"]
        == "confirmed"
    )
    assert json.loads(respond(offer_db, patient, second, "accept").stdout)["error"] == "conflict"
    assert (
        offer_db(
            f"SELECT count(*) FROM appointment_offer_events WHERE appointment_id = '{first['id']}' AND proposal_group_id IS NULL AND action = 'accept';"
        ).stdout.strip()
        == "1"
    )


def age_offer(sql, rows):
    sql(
        f"UPDATE appointments SET created_at = clock_timestamp() - interval '168 hours', patient_note = 'Preserve this synthetic note' WHERE proposal_group_id = '{rows[0]['proposal_group_id']}';"
    )


def test_expiry_at_seven_days_is_persisted_audited_and_idempotent(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    age_offer(offer_db, rows)
    assert json.loads(respond(offer_db, patient, rows[0], "accept").stdout)["error"] == "expired"
    assert (
        offer_db(
            f"SELECT status || ':' || patient_note FROM appointments WHERE patient_id = '{patient}';"
        ).stdout.splitlines()
        == ["expired:Preserve this synthetic note"] * 3
    )
    assert (
        offer_db(
            f"SELECT count(*) FROM appointment_offer_events WHERE patient_id = '{patient}' AND action = 'expire' AND actor_id IS NULL AND previous_status = 'proposed';"
        ).stdout.strip()
        == "3"
    )
    assert (
        json.loads(
            offer_db(
                f"SET ROLE service_role; SELECT expire_appointment_proposals('{patient}', 'patient');"
            ).stdout
        )["expired_count"]
        == 0
    )
    denied = offer_db(
        f"UPDATE appointments SET status = 'confirmed' WHERE id = '{rows[0]['id']}';", checked=False
    )
    assert denied.returncode != 0 and "appointment_expired" in denied.stderr


def test_expiry_reads_are_scoped_to_patient_and_active_clinician_assignments(offer_db):
    patient, clinician, team, rows = create_offer(offer_db)
    other_patient, _, _, other = create_offer(offer_db)
    age_offer(offer_db, rows)
    age_offer(offer_db, other)
    assert (
        json.loads(respond(offer_db, other_patient, rows[0], "accept").stdout)["error"]
        == "forbidden"
    )
    assert (
        offer_db(f"SELECT status FROM appointments WHERE id = '{rows[0]['id']}';").stdout.strip()
        == "proposed"
    )
    offer_db(f"UPDATE care_teams SET status = 'inactive' WHERE id = '{team}';")
    assert (
        json.loads(
            offer_db(
                f"SET ROLE service_role; SELECT expire_appointment_proposals('{clinician}', 'clinician');"
            ).stdout
        )["expired_count"]
        == 0
    )
    offer_db(f"UPDATE care_teams SET status = 'active' WHERE id = '{team}';")
    assert (
        json.loads(
            offer_db(
                f"SET ROLE service_role; SELECT expire_appointment_proposals('{clinician}', 'clinician');"
            ).stdout
        )["expired_count"]
        == 3
    )
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE patient_id = '{other_patient}' AND status = 'proposed';"
        ).stdout.strip()
        == "3"
    )
    assert (
        json.loads(
            offer_db(
                f"SET ROLE service_role; SELECT expire_appointment_proposals('{other_patient}', 'patient');"
            ).stdout
        )["expired_count"]
        == 3
    )
    denied = offer_db(
        f"SET ROLE authenticated; SELECT expire_appointment_proposals('{patient}', 'patient');",
        checked=False,
    )
    assert denied.returncode != 0 and "permission denied" in denied.stderr


def test_elapsed_slot_expires_after_lock_wait_but_future_sibling_can_be_chosen(offer_db):
    patient, clinician, team, _ = create_offer(offer_db)
    rows = json.loads(
        offer_db(
            f"SET ROLE service_role; SELECT propose_appointment_slots('{clinician}', '{team}', ARRAY[clock_timestamp() + interval '1 second', clock_timestamp() + interval '2 days'], 30, 'follow_up', NULL, NULL);"
        ).stdout
    )["appointments"]
    # now() remains at transaction start; clock_timestamp() must reject the late response.
    result = offer_db(
        f"BEGIN; SET ROLE service_role; SELECT pg_sleep(1.1); SELECT respond_to_appointment_offer('{patient}', '{rows[0]['id']}', 'accept', NULL); COMMIT;"
    )
    assert json.loads(result.stdout)["error"] == "expired"
    result = json.loads(respond(offer_db, patient, rows[1], "accept").stdout)
    assert result["appointment"]["status"] == "confirmed"
    assert (
        offer_db(f"SELECT status FROM appointments WHERE id = '{rows[0]['id']}';").stdout.strip()
        == "expired"
    )


def test_past_legacy_booking_and_direct_expired_confirmation_are_rejected(offer_db):
    patient, _, team, rows = create_offer(offer_db)
    result = insert_legacy(offer_db, patient, team, "2000-01-01T00:00:00Z", checked=False)
    assert result.returncode != 0 and "appointment_past" in result.stderr
    age_offer(offer_db, rows)
    result = offer_db(
        f"UPDATE appointments SET status = 'confirmed' WHERE id = '{rows[0]['id']}';", checked=False
    )
    assert result.returncode != 0 and "appointment_expired" in result.stderr


def test_expiration_audit_failure_rolls_back_statuses(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    age_offer(offer_db, rows)
    offer_db(
        "CREATE FUNCTION test_expiry_audit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action = 'expire' THEN RAISE EXCEPTION 'synthetic expiry audit failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER test_expiry_failure BEFORE INSERT ON appointment_offer_events FOR EACH ROW EXECUTE FUNCTION test_expiry_audit_failure();"
    )
    try:
        result = offer_db(
            f"SET ROLE service_role; SELECT expire_appointment_proposals('{patient}', 'patient');",
            checked=False,
        )
        assert result.returncode != 0 and "synthetic expiry audit failure" in result.stderr
        assert (
            offer_db(
                f"SELECT count(*) FROM appointments WHERE patient_id = '{patient}' AND status = 'proposed';"
            ).stdout.strip()
            == "3"
        )
    finally:
        offer_db(
            "DROP TRIGGER test_expiry_failure ON appointment_offer_events; DROP FUNCTION test_expiry_audit_failure();"
        )


def test_existing_proposals_receive_creation_based_deadlines(offer_db):
    row = json.loads(
        offer_db(
            "SELECT row_to_json(a) FROM appointments a WHERE reason = 'Synthetic pre-Slice-5 offer';"
        ).stdout
    )
    assert row["proposal_expires_at"] is not None
    assert (
        offer_db(
            f"SELECT proposal_expires_at = created_at + interval '168 hours' FROM appointments WHERE id = '{row['id']}';"
        ).stdout.strip()
        == "t"
    )
    assert (
        json.loads(respond(offer_db, row["patient_id"], row, "accept").stdout)["error"] == "expired"
    )


def test_booking_intervals_use_elapsed_utc_minutes_across_dst(offer_db):
    assert (
        offer_db(
            "SET TIME ZONE 'America/Los_Angeles'; SELECT public.appointment_booking_window('2026-11-01T08:30:00Z', 60) = tsrange('2026-11-01 08:30:00', '2026-11-01 09:30:00', '[)');"
        ).stdout.strip()
        == "t"
    )


def test_patient_overlap_is_enforced_across_different_care_teams(offer_db):
    patient, _, _, rows = create_offer(offer_db)
    clinician, team = str(uuid4()), str(uuid4())
    offer_db(
        f"INSERT INTO clinicians VALUES ('{clinician}', 'Synthetic', 'Second'); INSERT INTO care_teams VALUES ('{team}', '{patient}', '{clinician}', 'active');"
    )
    other = additional_offer(offer_db, clinician, team, rows[0]["scheduled_at"])
    respond(offer_db, patient, rows[0], "accept")
    assert json.loads(respond(offer_db, patient, other[0], "accept").stdout)["error"] == "conflict"


@pytest.mark.parametrize("attempt", range(3))
def test_concurrent_direct_booking_and_acceptance_cannot_both_succeed(offer_db, attempt):
    patient, _, team, rows = create_offer(offer_db)
    start = rows[0]["scheduled_at"]
    commands = [
        f"BEGIN; SET ROLE service_role; INSERT INTO appointments(patient_id, care_team_id, scheduled_at) VALUES ('{patient}', '{team}', '{start}'); SELECT pg_sleep(0.15); COMMIT;",
        f"BEGIN; SET ROLE service_role; SELECT respond_to_appointment_offer('{patient}', '{rows[0]['id']}', 'accept', NULL); SELECT pg_sleep(0.15); COMMIT;",
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda source: offer_db(source, checked=False), commands))
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE patient_id = '{patient}' AND status IN ('scheduled', 'confirmed');"
        ).stdout.strip()
        == "1"
    )
    assert any(
        "conflict" in result.stdout or "appointments_patient_no_overlap" in result.stderr
        for result in results
    )


def test_preflight_finds_existing_overlap_without_repairing_it(offer_db):
    patient, _, team, rows = create_offer(offer_db)
    query = (MIGRATIONS.parents[3] / "scripts/appointment-booking-preflight.sql").read_text()
    result = offer_db(
        "BEGIN; ALTER TABLE appointments DROP CONSTRAINT appointments_patient_no_overlap; "
        f"INSERT INTO appointments(patient_id, care_team_id, scheduled_at) VALUES "
        f"('{patient}', '{team}', '{rows[0]['scheduled_at']}'), "
        f"('{patient}', '{team}', '{rows[0]['scheduled_at']}'::timestamptz + interval '15 minutes');\n"
        + query
        + "\nROLLBACK;"
    )
    assert len(result.stdout.strip().splitlines()) == 1
    assert result.stdout.startswith(patient)
    assert (
        offer_db(
            f"SELECT count(*) FROM appointments WHERE patient_id = '{patient}' AND status = 'scheduled';"
        ).stdout.strip()
        == "0"
    )


def test_audit_rls_is_patient_owned_or_actively_assigned(offer_db):
    patient, clinician, team, rows = create_offer(offer_db)
    group = rows[0]["proposal_group_id"]

    def visible(actor):
        return offer_db(
            f"SET ROLE authenticated; SET test.actor = '{actor}'; SELECT count(*) FROM appointment_offer_events WHERE proposal_group_id = '{group}';"
        ).stdout.strip()

    assert visible(patient) == "3"

    assert visible(clinician) == "3"
    assert visible(str(uuid4())) == "0"
    offer_db(f"UPDATE care_teams SET status = 'inactive' WHERE id = '{team}';")
    assert visible(clinician) == "0"
    assert visible(patient) == "3"


def test_slice5_read_only_verifier_accepts_migrated_schema(offer_db):
    source = (MIGRATIONS.parents[3] / "scripts/verify-appointment-slice5.sql").read_text()
    assert "Slice 5 schema and function permissions verified" in offer_db(source).stdout


def test_slice5_verifier_rejects_browser_rpc_access(offer_db):
    source = (MIGRATIONS.parents[3] / "scripts/verify-appointment-slice5.sql").read_text()
    offer_db("GRANT EXECUTE ON FUNCTION expire_appointment_proposals(uuid, text) TO authenticated;")
    try:
        result = offer_db(source, checked=False)
        assert result.returncode != 0 and "function grants are incorrect" in result.stderr
    finally:
        offer_db(
            "REVOKE EXECUTE ON FUNCTION expire_appointment_proposals(uuid, text) FROM authenticated;"
        )


def test_slice5_verifier_rejects_disabled_expiry_audit(offer_db):
    source = (MIGRATIONS.parents[3] / "scripts/verify-appointment-slice5.sql").read_text()
    offer_db("ALTER TABLE appointments DISABLE TRIGGER appointments_expiration_audit;")
    try:
        result = offer_db(source, checked=False)
        assert result.returncode != 0 and "trigger is missing or disabled" in result.stderr
    finally:
        offer_db("ALTER TABLE appointments ENABLE TRIGGER appointments_expiration_audit;")
