"""Real database email ownership, consent, queue and retry boundaries."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.integration.test_notification_centre_postgres import (
    CLINICIAN,
    MIGRATIONS,
    PATIENT,
    document,
    send,
    thread,
)

pytest_plugins = ["tests.integration.test_notification_centre_postgres"]

pytestmark = pytest.mark.skipif(
    os.environ.get("EMAIL_TEST_POSTGRES_DOCKER") != "1",
    reason="disposable offline PostgreSQL opt-in",
)


@pytest.fixture
def email_sql(sql):
    sql("ALTER TABLE auth.users ADD COLUMN email text;")
    sql(
        f"UPDATE auth.users SET email=CASE WHEN id='{PATIENT}' THEN 'patient@example.com' ELSE 'clinician@example.com' END;"
    )
    sql((MIGRATIONS / "057_email_delivery.sql").read_text())
    return sql


def account(sql, action="get", payload=None, *, actor=PATIENT, role="patient"):
    data = json.dumps(payload or {}).replace("'", "''")
    return json.loads(
        sql(
            f"SET ROLE service_role; SELECT email_account_operation('{actor}','{role}','{action}','{data}');"
        )
    )


def delivery(sql, action="claim", payload=None):
    data = json.dumps(payload or {}).replace("'", "''")
    return json.loads(
        sql(f"SET ROLE service_role; SELECT email_delivery_operation('{action}','{data}');")
    )


def verified(sql, *, actor=PATIENT, role="patient"):
    account(sql, actor=actor, role=role)
    account(
        sql,
        "challenge",
        {
            "hash": "hash",
            "key": f"verify/{uuid4()}",
            "payload": {
                "from": "demo@example.com",
                "to": ["patient@example.com"],
                "subject": "Verify",
                "text": "Code",
            },
        },
        actor=actor,
        role=role,
    )
    assert account(sql, "verify", {"hash": "hash"}, actor=actor, role=role)["verified"]


def test_browser_cannot_read_or_invoke_delivery(email_sql):
    for role in ("anon", "authenticated"):
        assert "permission denied" in email_sql(
            f"SET ROLE {role}; SELECT * FROM email_outbox;", succeeds=False
        )
        assert "permission denied" in email_sql(
            f"SET ROLE {role}; SELECT email_delivery_operation('claim');", succeeds=False
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


def test_address_change_revokes_verification_and_consent(email_sql):
    verified(email_sql)
    account(email_sql, "preferences", {"messages": True})
    email_sql(f"UPDATE auth.users SET email='new@example.com' WHERE id='{PATIENT}';")
    value = account(email_sql)
    assert not value["verified"] and value["preferences"] == {}


def test_synthetic_address_never_enqueues(email_sql):
    email_sql(f"UPDATE auth.users SET email='morgan@accounts.mediagent.live' WHERE id='{PATIENT}';")
    assert (
        account(email_sql, "challenge", {"hash": "hash", "key": "v", "payload": {}})["status"]
        == "synthetic"
    )
    assert delivery(email_sql)["items"] == []


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
    delivery(email_sql, "finish", {"id": row["id"], "lease": row["lease"], "provider_id": "stale"})
    assert email_sql("SELECT count(*) FROM email_outbox WHERE provider_id='stale';") == "0"
    delivery(
        email_sql, "finish", {"id": retry["id"], "lease": retry["lease"], "provider_id": "accepted"}
    )
    assert email_sql("SELECT state FROM email_outbox;") == "accepted"


def test_no_retry_past_provider_retention(email_sql):
    account(email_sql)
    account(email_sql, "challenge", {"hash": "hash", "key": "old", "payload": {}})
    email_sql("UPDATE email_outbox SET created_at=clock_timestamp()-interval '24 hours';")
    assert delivery(email_sql)["items"] == []
    assert email_sql("SELECT state FROM email_outbox;") == "failed"


def invitation(sql, action, payload, *, actor=CLINICIAN, succeeds=True):
    data = json.dumps(payload).replace("'", "''")
    result = sql(
        f"SET ROLE service_role; SELECT clinician_email_invitation_operation('{actor}','{action}','{data}');",
        succeeds=succeeds,
    )
    return json.loads(result) if succeeds else result


def create_invitation(sql):
    sql(f"UPDATE clinicians SET role='admin' WHERE id='{CLINICIAN}';")
    return invitation(
        sql,
        "create",
        {
            "email": "new@example.com",
            "role": "nurse",
            "hash": "secret-hash",
            "payload": {
                "to": ["new@example.com"],
                "from": "demo@example.com",
                "subject": "Invite",
                "text": "Synthetic",
            },
        },
    )


def test_invitation_does_not_grant_membership_and_accepts_once(email_sql):
    value = create_invitation(email_sql)
    assert value["status"] == "queued"
    assert email_sql("SELECT count(*) FROM clinicians WHERE email='new@example.com';") == "0"
    new = str(uuid4())
    email_sql(
        f"INSERT INTO auth.users(id,email) VALUES('{new}','new@example.com'); INSERT INTO clinicians(id,email,first_name,last_name,specialty) VALUES('{new}','new@example.com','Demo','Invite','Synthetic');"
    )
    assert (
        invitation(email_sql, "accept", {"hash": "secret-hash"}, actor=new)["status"] == "accepted"
    )
    assert email_sql(f"SELECT role FROM clinicians WHERE id='{new}';") == "nurse"
    assert (
        invitation(email_sql, "accept", {"hash": "secret-hash"}, actor=new)["status"] == "accepted"
    )


def test_invitation_wrong_account_and_revocation(email_sql):
    value = create_invitation(email_sql)
    assert "not for this account" in invitation(
        email_sql, "accept", {"hash": "secret-hash"}, actor=CLINICIAN, succeeds=False
    )
    assert invitation(email_sql, "revoke", {"id": value["invitation_id"]})["status"] == "revoked"
    assert "invalid or expired" in invitation(
        email_sql, "preview", {"hash": "secret-hash"}, succeeds=False
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
