"""Real database email ownership, consent, queue, retry and locking boundaries.

Applies 057 exactly as it is in the ledger, removes every service_role privilege on the
auth schema (hosted migrations cannot grant it), then applies 058. Nothing below may
need the auth schema at runtime: the backend passes the Auth address in.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    PATIENT,
    document,
    finish,
    send,
    thread,
    wait_event,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("EMAIL_TEST_POSTGRES_DOCKER") != "1",
    reason="disposable offline PostgreSQL opt-in",
)

CLINIC = "00000000-0000-0000-0000-000000000007"
ADDRESSES = {PATIENT: "patient@example.com", CLINICIAN: "clinician@example.com"}


@pytest.fixture
def email_sql(sql):
    # The base ``sql`` fixture already applies 057, the auth-privilege revoke and 058.
    return sql


def encode(payload):
    return json.dumps(payload or {}).replace("'", "''")


def account(sql, action="get", payload=None, *, actor=PATIENT, role="patient", email=None):
    data = encode({**(payload or {}), "account_email": email or ADDRESSES[actor]})
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT email_account_operation('{actor}','{role}','{action}','{data}');"
        )
    )


def delivery(sql, action="claim", payload=None):
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT email_delivery_operation('{action}','{encode(payload)}');"
        )
    )


def challenge(sql, *, actor=PATIENT, role="patient", key=None):
    return account(
        sql,
        "challenge",
        {
            "hash": "hash",
            "key": key or f"verify/{uuid4()}",
            "payload": {
                "from": "demo@example.com",
                "to": [ADDRESSES[actor]],
                "subject": "Verify",
                "text": "Code",
            },
        },
        actor=actor,
        role=role,
    )


def verified(sql, *, actor=PATIENT, role="patient"):
    account(sql, actor=actor, role=role)
    challenge(sql, actor=actor, role=role)
    assert account(sql, "verify", {"hash": "hash"}, actor=actor, role=role)["verified"]


def test_browser_cannot_read_or_invoke_delivery(email_sql):
    for role in ("anon", "authenticated"):
        assert "permission denied" in email_sql(
            f"SET ROLE {role}; SELECT * FROM email_outbox;", succeeds=False
        )
        assert "permission denied" in email_sql(
            f"SET ROLE {role}; SELECT email_delivery_operation('claim');", succeeds=False
        )


def test_no_runtime_dependency_on_the_auth_schema(email_sql):
    assert email_sql("SELECT has_schema_privilege('service_role','auth','USAGE');") == "f"
    assert email_sql("SELECT has_table_privilege('service_role','auth.users','SELECT');") == "f"
    verified(email_sql)
    challenge(email_sql)
    assert len(delivery(email_sql)["items"]) == 0  # the newest code was already verified


def test_missing_account_address_is_refused(email_sql):
    assert "Email unavailable" in email_sql(
        f"SET ROLE service_role; SELECT email_account_operation('{PATIENT}','patient','get','{{}}');",
        succeeds=False,
    )


def test_defaults_off_and_verification_does_not_opt_in(email_sql):
    value = account(email_sql)
    assert not value["verified"] and value["preferences"] == {}
    verified(email_sql)
    assert account(email_sql)["preferences"] == {}


def test_code_attempt_limit_and_cooldown(email_sql):
    account(email_sql)
    data = {"hash": "right", "key": f"verify/{uuid4()}", "payload": {}}
    assert account(email_sql, "challenge", data)["status"] == "queued"
    assert account(email_sql, "challenge", data)["status"] == "wait"
    for _ in range(5):
        assert not account(email_sql, "verify", {"hash": "wrong"})["verified"]
    assert not account(email_sql, "verify", {"hash": "right"})["verified"]


def test_daily_challenge_cap(email_sql):
    account(email_sql)
    for _ in range(5):
        assert challenge(email_sql)["status"] == "queued"
        email_sql(
            "UPDATE email_contacts SET challenge_sent_at=clock_timestamp()-interval '2 minutes';"
        )
    assert challenge(email_sql)["status"] == "limit"
    email_sql(
        "UPDATE email_contacts SET challenge_window_start=clock_timestamp()-interval '25 hours';"
    )
    assert challenge(email_sql)["status"] == "queued"


def test_new_code_supersedes_unsent_code_and_verification_clears_it(email_sql):
    account(email_sql)
    first = challenge(email_sql)["outbox_id"]
    email_sql("UPDATE email_contacts SET challenge_sent_at=clock_timestamp()-interval '2 minutes';")
    second = challenge(email_sql)["outbox_id"]
    assert email_sql(f"SELECT state, payload IS NULL FROM email_outbox WHERE id='{first}';") == (
        "suppressed|t"
    )
    assert account(email_sql, "verify", {"hash": "hash"})["verified"]
    assert email_sql(f"SELECT state, payload IS NULL FROM email_outbox WHERE id='{second}';") == (
        "suppressed|t"
    )


def test_consent_is_stamped_only_when_notices_turn_on(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    email_sql("UPDATE email_contacts SET consent_at='2026-01-01T00:00:00Z';")
    account(email_sql, "preferences", {"messages": True, "appointments": True})
    assert email_sql("SELECT consent_at::date FROM email_contacts;") == "2026-01-01"
    account(email_sql, "preferences", {"messages": False})
    assert email_sql("SELECT consent_at IS NULL FROM email_contacts;") == "t"


def test_address_change_revokes_verification_and_consent(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    value = account(email_sql, email="new@example.com")
    assert not value["verified"] and value["preferences"] == {}


def test_synthetic_address_never_enqueues(email_sql):
    assert (
        account(
            email_sql,
            "challenge",
            {"hash": "hash", "key": "v", "payload": {}},
            email="morgan@accounts.mediagent.live",
        )["status"]
        == "synthetic"
    )
    assert delivery(email_sql)["items"] == []


def test_freeze_stops_send_when_auth_address_changed(email_sql):
    account(email_sql)
    challenge(email_sql)
    [row] = delivery(email_sql)["items"]
    frozen = delivery(
        email_sql,
        "freeze",
        {
            "id": row["id"],
            "lease": row["lease"],
            "payload": None,
            "account_email": "other@example.com",
        },
    )
    assert frozen == {}
    assert email_sql("SELECT state, payload IS NULL FROM email_outbox;") == "suppressed|t"


def test_single_row_claim_takes_only_that_row(email_sql):
    account(email_sql)
    account(email_sql, actor=CLINICIAN, role="clinician")
    own = challenge(email_sql)["outbox_id"]
    challenge(email_sql, actor=CLINICIAN, role="clinician")
    items = delivery(email_sql, "claim", {"id": own, "kinds": ["verification"]})["items"]
    assert [row["id"] for row in items] == [own]
    assert delivery(email_sql, "claim", {"kinds": ["invitation"]})["items"] == []


def test_clinic_review_queue_rechecks_source_status(email_sql):
    verified(email_sql, actor=CLINICIAN, role="clinician")
    account(email_sql, "preferences", {"reviews": True}, actor=CLINICIAN, role="clinician")
    doc = document(email_sql)
    email_sql("UPDATE email_outbox SET available_at=clock_timestamp()-interval '1 second';")
    email_sql(f"UPDATE documents SET review_status='approved' WHERE id='{doc}';")
    assert not any(x["kind"] == "notice" for x in delivery(email_sql)["items"])


def test_claim_once_lease_and_idempotency_key_persist(email_sql):
    account(email_sql)
    account(
        email_sql,
        "challenge",
        {"hash": "hash", "key": "verify/stable", "payload": {"to": ["patient@example.com"]}},
    )
    first = delivery(email_sql)["items"]
    assert len(first) == 1
    assert delivery(email_sql)["items"] == []
    row = first[0]
    delivery(email_sql, "finish", {"id": row["id"], "lease": row["lease"], "provider_id": None})
    email_sql("UPDATE email_outbox SET available_at=clock_timestamp()-interval '1 second';")
    retry = delivery(email_sql)["items"][0]
    assert retry["dedupe_key"] == row["dedupe_key"] and retry["lease"] != row["lease"]
    assert retry["generation"] == row["generation"] == 0
    delivery(email_sql, "finish", {"id": row["id"], "lease": row["lease"], "provider_id": "stale"})
    assert email_sql("SELECT count(*) FROM email_outbox WHERE provider_id='stale';") == "0"
    delivery(
        email_sql, "finish", {"id": retry["id"], "lease": retry["lease"], "provider_id": "accepted"}
    )
    assert email_sql(
        "SELECT state, payload IS NULL, accepted_at IS NOT NULL FROM email_outbox;"
    ) == ("accepted|t|t")


def test_no_retry_past_provider_retention(email_sql):
    account(email_sql)
    account(email_sql, "challenge", {"hash": "hash", "key": "old", "payload": {}})
    email_sql("UPDATE email_outbox SET created_at=clock_timestamp()-interval '24 hours';")
    assert delivery(email_sql)["items"] == []
    assert email_sql("SELECT state FROM email_outbox;") == "failed"


def provider_row(sql, *, kind="notice", accepted="10 minutes", state="accepted"):
    key = str(uuid4())
    sql(
        f"""INSERT INTO email_outbox(id,user_id,kind,dedupe_key,state,provider_id,accepted_at)
        VALUES('{key}','{PATIENT}','{kind}','{key}','{state}','provider-{key}',
        clock_timestamp()-interval '{accepted}');"""
    )
    return key


def test_status_polling_cutoff_and_mapping(email_sql):
    account(email_sql)
    recent = provider_row(email_sql)
    provider_row(email_sql, accepted="73 hours")
    assert [row["id"] for row in delivery(email_sql, "accepted")["items"]] == [recent]
    delivery(
        email_sql,
        "status",
        {"id": recent, "provider_id": f"provider-{recent}", "state": "accepted"},
    )
    # A checked row waits for the next poll interval.
    assert delivery(email_sql, "accepted")["items"] == []
    email_sql("UPDATE email_outbox SET status_checked_at=clock_timestamp()-interval '10 minutes';")
    delivery(
        email_sql,
        "status",
        {"id": recent, "provider_id": f"provider-{recent}", "state": "delivered"},
    )
    delivery(
        email_sql,
        "status",
        {"id": recent, "provider_id": f"provider-{recent}", "state": "accepted"},
    )
    assert email_sql(f"SELECT state FROM email_outbox WHERE id='{recent}';") == "delivered"
    assert "Invalid delivery status" in email_sql(
        f"""SET ROLE service_role; SELECT email_delivery_operation('status','{encode({"id": recent, "provider_id": "p", "state": "queued"})}');""",
        succeeds=False,
    )


def test_complaint_is_not_a_bounce_and_withdraws_notice_consent(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    row = provider_row(email_sql)
    delivery(
        email_sql, "status", {"id": row, "provider_id": f"provider-{row}", "state": "complained"}
    )
    assert email_sql(
        f"SELECT state, complained_at IS NOT NULL FROM email_outbox WHERE id='{row}';"
    ) == ("delivered|t")
    value = account(email_sql)
    assert value["verified"] and value["preferences"] == {}
    assert email_sql("SELECT consent_at IS NULL FROM email_contacts;") == "t"


def test_dry_run_counts_without_claiming(email_sql):
    account(email_sql)
    challenge(email_sql)
    assert delivery(email_sql, "pending") == {"due": 1, "awaiting_status": 0}
    assert email_sql("SELECT state, lease IS NULL FROM email_outbox;") == "queued|t"


def invitation(sql, action, payload, *, actor=CLINICIAN, succeeds=True):
    data = encode(payload)
    who = "NULL" if actor is None else f"'{actor}'"
    result = sql(
        f"SET ROLE service_role; SELECT clinician_email_invitation_operation({who},'{action}','{data}');",
        succeeds=succeeds,
    )
    return json.loads(result) if succeeds else result


def create_invitation(sql, email="new@example.com", token="secret-hash", role="nurse"):
    sql(f"UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';")
    return invitation(
        sql,
        "create",
        {
            "email": email,
            "role": role,
            "hash": token,
            "payload": {
                "to": [email],
                "from": "demo@example.com",
                "subject": "Invite",
                "text": "Synthetic",
            },
        },
    )


def invitee(sql, email="new@example.com"):
    new = str(uuid4())
    sql(
        f"INSERT INTO auth.users(id) VALUES('{new}'); INSERT INTO clinicians(id,email,first_name,last_name,specialty) VALUES('{new}','{email}','Demo','Invite','Synthetic');"
    )
    return new


def accept(sql, actor, *, token="secret-hash", email="new@example.com", succeeds=True):
    return invitation(
        sql, "accept", {"hash": token, "account_email": email}, actor=actor, succeeds=succeeds
    )


def test_invitation_does_not_grant_membership_and_accepts_once(email_sql):
    value = create_invitation(email_sql)
    assert value["status"] == "queued" and value["outbox_id"]
    preview = invitation(email_sql, "preview", {"hash": "secret-hash"}, actor=None)
    assert preview["clinic_name"] == "Synthetic clinic" and "clinic_code" not in preview
    new = invitee(email_sql)
    accepted = accept(email_sql, new)
    assert accepted["status"] == "accepted" and accepted["clinic_id"] == CLINIC
    assert "clinic_code" in accepted
    assert (
        email_sql(f"SELECT role, clinic_id FROM clinicians WHERE id='{new}';") == f"nurse|{CLINIC}"
    )
    assert accept(email_sql, new)["status"] == "accepted"
    # The unsent link leaves the outbox once membership is accepted.
    assert email_sql("SELECT state, payload IS NULL FROM email_outbox;") == "suppressed|t"


def test_invitation_requires_the_invited_auth_address(email_sql):
    create_invitation(email_sql)
    new = invitee(email_sql)
    assert "not for this account" in accept(
        email_sql, new, email="other@example.com", succeeds=False
    )


def test_invitation_wrong_account_and_revocation(email_sql):
    value = create_invitation(email_sql)
    assert "not for this account" in accept(
        email_sql, CLINICIAN, email="clinician@example.com", succeeds=False
    )
    assert invitation(email_sql, "revoke", {"id": value["invitation_id"]})["status"] == "revoked"
    assert email_sql("SELECT state, payload IS NULL FROM email_outbox;") == "suppressed|t"
    assert "invalid or expired" in invitation(
        email_sql, "preview", {"hash": "secret-hash"}, actor=None, succeeds=False
    )
    assert delivery(email_sql)["items"] == []


def test_existing_clinic_membership_cannot_be_moved(email_sql):
    create_invitation(email_sql)
    email_sql(f"UPDATE clinicians SET email='clinician@example.com' WHERE id='{CLINICIAN}';")
    assert "must not be changed" in invitation(
        email_sql,
        "create",
        {"email": "clinician@example.com", "role": "admin", "hash": "other", "payload": {}},
        succeeds=False,
    )


def test_reinvite_replaces_a_link_whose_delivery_stopped(email_sql):
    first = create_invitation(email_sql)
    assert create_invitation(email_sql, token="second")["status"] == "already_pending"
    email_sql("UPDATE email_outbox SET state='failed',payload=NULL;")
    second = create_invitation(email_sql, token="third")
    assert second["status"] == "queued" and second["invitation_id"] != first["invitation_id"]
    assert (
        email_sql(
            f"SELECT revoked_at IS NOT NULL FROM clinician_email_invitations WHERE id='{first['invitation_id']}';"
        )
        == "t"
    )


def test_invitation_history_takes_no_row_locks(email_sql):
    create_invitation(email_sql)
    holder = email_sql.start(
        f"BEGIN; SELECT 1 FROM clinics WHERE id='{CLINIC}' FOR UPDATE;"
        f" SELECT 1 FROM clinicians WHERE id='{CLINICIAN}' FOR UPDATE; SELECT pg_sleep(4); COMMIT;",
        "holder",
    )
    wait_event(email_sql, "holder")
    started = time.monotonic()
    assert len(invitation(email_sql, "list", {})["items"]) == 1
    assert time.monotonic() - started < 3
    finish(holder)


def wait_lock(sql, name):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (
            sql(
                f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{name}' AND wait_event_type='Lock'"
            )
            == "1"
        ):
            return
        time.sleep(0.03)
    pytest.fail(f"Session {name} did not wait for a lock")


def assert_lockable(sql, statement):
    # NOWAIT fails the statement (and this assertion) if another session holds the rows.
    sql(f"BEGIN; {statement} NOWAIT; ROLLBACK;")


@pytest.mark.parametrize("action", ["accept", "create"])
def test_invitation_operations_lock_the_clinic_first(email_sql, action):
    create_invitation(email_sql)
    new = invitee(email_sql)
    holder = email_sql.start(
        f"BEGIN; SELECT 1 FROM clinics WHERE id='{CLINIC}' FOR UPDATE; SELECT pg_sleep(3); COMMIT;",
        "holder",
    )
    wait_event(email_sql, "holder")
    if action == "accept":
        statement = (
            f"SET ROLE service_role; SELECT clinician_email_invitation_operation('{new}','accept',"
            f"'{encode({'hash': 'secret-hash', 'account_email': 'new@example.com'})}');"
        )
    else:
        statement = (
            f"SET ROLE service_role; SELECT clinician_email_invitation_operation('{CLINICIAN}','create',"
            f"'{encode({'email': 'later@example.com', 'role': 'nurse', 'hash': 'later', 'payload': {}})}');"
        )
    claimant = email_sql.start(statement, "claimant")
    wait_lock(email_sql, "claimant")
    # While it waits for the clinic, it holds no clinician or invitation row lock.
    assert_lockable(
        email_sql, f"SELECT 1 FROM clinicians WHERE id IN ('{CLINICIAN}','{new}') FOR UPDATE"
    )
    assert_lockable(email_sql, "SELECT 1 FROM clinician_email_invitations FOR UPDATE")
    finish(holder)
    assert '"status"' in finish(claimant)


def test_concurrent_invitation_operations_do_not_deadlock(email_sql):
    tokens = [f"token-{index}" for index in range(4)]
    invitees = []
    for index, token in enumerate(tokens):
        address = f"invitee{index}@example.com"
        create_invitation(email_sql, email=address, token=token)
        invitees.append((invitee(email_sql, address), token, address))

    def work(index):
        if index < 4:
            actor, token, address = invitees[index]
            return accept(email_sql, actor, token=token, email=address)["status"]
        if index < 7:
            return create_invitation(
                email_sql, email=f"extra{index}@example.com", token=f"x{index}"
            )["status"]
        return str(len(invitation(email_sql, "list", {})["items"]))

    with ThreadPoolExecutor(max_workers=10) as workers:
        results = list(workers.map(work, range(10)))
    assert results[:4] == ["accepted"] * 4
    assert results[4:7] == ["queued"] * 3


def test_concurrent_workers_do_not_claim_the_same_send(email_sql):
    account(email_sql)
    account(email_sql, "challenge", {"hash": "hash", "key": "race", "payload": {}})
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: delivery(email_sql)["items"], range(2)))
    assert sum(len(rows) for rows in results) == 1


def test_grouped_reviews_keep_other_pending_work(email_sql):
    verified(email_sql, actor=CLINICIAN, role="clinician")
    account(email_sql, "preferences", {"reviews": True}, actor=CLINICIAN, role="clinician")
    document(email_sql)
    latest = document(email_sql)
    delivery(email_sql)
    email_sql(
        f"UPDATE documents SET review_status='approved' WHERE id='{latest}'; UPDATE email_outbox SET available_at=clock_timestamp()-interval '1 second';"
    )
    notices = [row for row in delivery(email_sql)["items"] if row["kind"] == "notice"]
    assert len(notices) == 1


def test_stopped_group_is_reopened_by_a_new_unread_item(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    conversation = thread(email_sql)
    send(email_sql, conversation)
    delivery(email_sql)
    email_sql(
        f"UPDATE notification_receipts SET read_at=clock_timestamp() WHERE recipient_id='{PATIENT}';"
        " UPDATE email_outbox SET available_at=clock_timestamp()-interval '1 second';"
    )
    delivery(email_sql)
    assert email_sql("SELECT state, generation FROM email_outbox WHERE kind='notice';") == (
        "suppressed|0"
    )
    send(email_sql, conversation)
    delivery(email_sql)
    rows = email_sql("SELECT state, generation, attempts FROM email_outbox WHERE kind='notice';")
    if len(rows.splitlines()) == 2:
        pytest.skip("the two messages fell into different 15-minute summaries")
    assert rows == "queued|1|0"


def test_private_message_email_only_addressed_recipient_and_revocation(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    conversation = thread(email_sql)
    send(email_sql, conversation)
    send(email_sql, conversation)
    delivery(email_sql)
    assert email_sql("SELECT count(*) FROM email_outbox WHERE kind='notice';") == "1"
    assert (
        email_sql(
            f"SELECT count(*) FROM email_outbox WHERE kind='notice' AND user_id<>'{PATIENT}';"
        )
        == "0"
    )
    email_sql(
        "UPDATE care_teams SET status='inactive'; UPDATE email_outbox SET available_at=clock_timestamp()-interval '1 second';"
    )
    assert not any(row["kind"] == "notice" for row in delivery(email_sql)["items"])
