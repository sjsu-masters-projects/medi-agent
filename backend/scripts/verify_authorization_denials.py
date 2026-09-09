"""Drive the fixture's negative-access cases against a running API and prove each
denial was both refused and recorded.

`negative_access_cases` in the canonical synthetic fixture declares, for every case,
the HTTP status a caller must receive, the reason code the audit trail must record,
and — for the cross-clinic case — that nothing about the target may leak, "including
existence of the record". Nothing enforced that contract end to end: the denials were
verified once by hand, and two cases were checked against an endpoint that does not
correspond to their declared action, so their results did not mean what they appeared
to mean.

This script closes that gap. It maps each declared action to exactly one route, and
refuses to guess: a case whose action has no unambiguous route is reported as SKIPPED
with the reason, never silently redirected to a route that happens to return 403. A
false pass is worse than a reported gap, because it retires the question.

Requires a running backend and the service-role key, which reads the audit table
directly — the API deliberately never exposes it, and RLS grants no browser role
access to it.

    export MEDIAGENT_API_BASE_URL=http://localhost:8000
    export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
    export DEMO_ACCOUNT_PASSWORD=...
    python backend/scripts/verify_authorization_denials.py

Exits non-zero if any testable case fails. Skips are reported but do not fail the
run; they are tracked as open work in `.agent/TASKS.md`, not hidden here.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# `app` is not installed into the virtualenv — only pytest puts `src` on the path —
# so resolve both import roots here and let the script be run directly.
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR.parent / "src"))

from seed_demo_environment import clinic_code, fixture_email  # noqa: E402

from app.core.authorization_reasons import MFA_REQUIRED  # noqa: E402
from app.db.seed.demo_data import CANONICAL_FIXTURE_PATH  # noqa: E402

# Each declared action resolves to exactly one route. A case whose action is absent
# here is skipped rather than approximated: routing `view_medication_timeline` to the
# patient-chart endpoint produces a 403 that proves nothing about medication access.
ACTION_ROUTES: dict[str, tuple[str, str]] = {
    "open_patient_chart": ("GET", "/api/v1/clinicians/me/patients/{patient_id}"),
    "open_patient_chart_by_direct_id": ("GET", "/api/v1/clinicians/me/patients/{patient_id}"),
}

# Actions with no unambiguous route today, and why. Resolving these needs a product
# decision about which endpoint owns the action, not a guess from this script.
UNMAPPED_ACTIONS: dict[str, str] = {
    "list_patient_documents": (
        "/documents/patients/{id} is POST — it registers a clinician upload. No route "
        "lists a named patient's documents for a clinician: GET /documents/ is self-only "
        "and the review queue is not per-patient"
    ),
    "view_medication_timeline": (
        "no route owns a per-patient medication timeline for a clinician actor; "
        "candidates (deep-dive, medications) each cover more or less than the action"
    ),
    "view_document_metadata": (
        "no route returns document metadata for a named patient without also "
        "returning document content or requiring a document ID the case does not name"
    ),
}

# Actor kinds the fixture declares but the system does not persist.
UNSUPPORTED_ACTOR_FIELDS: dict[str, str] = {
    "actor_proxy_id": "proxy actors are intentionally not persisted, so no session can be established",
}


@dataclass
class Result:
    case_id: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        print(f"error: {name} is required", file=sys.stderr)
        raise SystemExit(2)
    return value


def _load_cases() -> list[dict[str, Any]]:
    fixture = json.loads(Path(CANONICAL_FIXTURE_PATH).read_text())
    return list(fixture["negative_access_cases"])


def _patient_ids_by_email(supabase_url: str, service_key: str) -> dict[str, str]:
    """Resolve fixture patients to real UUIDs.

    Patient rows are keyed by a unique email, and the fixture's source IDs map to
    those emails through the seeding adapter, so this stays in step with whatever
    the environment was actually seeded with.
    """
    response = httpx.get(
        f"{supabase_url}/rest/v1/patients",
        params={"select": "id,email"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    )
    response.raise_for_status()
    return {row["email"]: row["id"] for row in response.json()}


def _login(api_base: str, email: str, password: str, clinic: str | None) -> tuple[str, bool]:
    """Return the access token and whether the session still owes a second factor.

    `mfa_required` matters to the result: `require_role("clinician")` refuses an
    unverified session before it ever reaches the care-team check, so a case run on
    such a session exercises the MFA gate rather than the boundary it declares.
    """
    payload: dict[str, Any] = {"email": email, "password": password}
    if clinic:
        payload["clinic_code"] = clinic
    response = httpx.post(f"{api_base}/api/v1/auth/login", json=payload, timeout=30)
    response.raise_for_status()
    body = response.json()
    token = body.get("tokens", {}).get("access_token")
    if not token:
        raise RuntimeError(f"login for {email} returned no access token")
    return str(token), bool(body.get("mfa_required", False))


def _actor(case: dict[str, Any]) -> tuple[str, str | None] | None:
    """Return (fixture source ID, clinic code) for the case's actor, or None if unsupported."""
    for field in UNSUPPORTED_ACTOR_FIELDS:
        if case.get(field):
            return None
    if staff_id := case.get("actor_staff_id"):
        clinic = case.get("actor_clinic_id")
        return staff_id, clinic_code(clinic) if clinic else None
    if patient_id := case.get("actor_patient_id"):
        # Patient login takes no clinic code.
        return patient_id, None
    return None


def _leaked(body: str, target_id: str) -> bool:
    """A denial must not confirm the target exists, so the ID must not come back."""
    return target_id.lower() in body.lower()


def _audit_row(
    supabase_url: str,
    service_key: str,
    actor_id: str | None,
    target_id: str,
    since: datetime,
) -> dict[str, Any] | None:
    """Find the denial this request produced.

    Matching on `target_id` alone is not enough. A role-gate denial is raised from a
    dependency that never learns which patient was addressed, so `require_role` records
    the actor and the request path with a null target. The path still carries the
    target's UUID, so match on either and let the caller see which one hit.
    """
    params = {
        "select": "reason_code,actor_id,actor_role,target_type,target_id,request_path,created_at",
        "created_at": f"gte.{since.isoformat()}",
        "order": "created_at.desc",
        "limit": "50",
    }
    if actor_id:
        params["actor_id"] = f"eq.{actor_id}"
    response = httpx.get(
        f"{supabase_url}/rest/v1/authorization_denial_events",
        params=params,
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    )
    response.raise_for_status()
    needle = target_id.lower()
    for row in response.json():
        if str(row.get("target_id") or "").lower() == needle:
            return dict(row)
        if needle in str(row.get("request_path") or "").lower():
            return dict(row)
    return None


def _run_case(
    case: dict[str, Any],
    *,
    api_base: str,
    supabase_url: str,
    service_key: str,
    password: str,
    patient_ids: dict[str, str],
) -> Result:
    case_id = case["case_id"]
    action = case["attempted_action"]

    if reason := UNMAPPED_ACTIONS.get(action):
        return Result(case_id, "SKIP", f"action '{action}' has no route: {reason}")

    actor = _actor(case)
    if actor is None:
        field = next((f for f in UNSUPPORTED_ACTOR_FIELDS if case.get(f)), "actor")
        return Result(case_id, "SKIP", UNSUPPORTED_ACTOR_FIELDS.get(field, "unsupported actor"))

    actor_source_id, clinic = actor
    method, template = ACTION_ROUTES[action]

    target_email = fixture_email(case["target_patient_id"])
    target_uuid = patient_ids.get(target_email)
    if not target_uuid:
        return Result(case_id, "FAIL", f"target {case['target_patient_id']} not seeded")

    try:
        token, mfa_required = _login(api_base, fixture_email(actor_source_id), password, clinic)
    except Exception as error:  # noqa: BLE001 - report, do not abort the sweep
        return Result(case_id, "FAIL", f"login failed for {actor_source_id}: {error}")

    started = datetime.now(UTC)
    response = httpx.request(
        method,
        f"{api_base}{template.format(patient_id=target_uuid)}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    expected_status = case["expected_http_status"]
    if response.status_code != expected_status:
        return Result(
            case_id,
            "FAIL",
            f"expected HTTP {expected_status}, got {response.status_code}",
        )

    if _leaked(response.text, target_uuid):
        return Result(case_id, "FAIL", "response body disclosed the target patient ID")

    expected_reason = case.get("expected_reason_code")
    if not case.get("expected_audit_entry"):
        return Result(case_id, "PASS", f"HTTP {expected_status}, no audit entry required")

    row = _audit_row(supabase_url, service_key, None, target_uuid, started)
    if row is None:
        return Result(case_id, "FAIL", "denial was not recorded in authorization_denial_events")

    actual_reason = row.get("reason_code")
    if expected_reason and actual_reason != expected_reason:
        if actual_reason == MFA_REQUIRED and mfa_required:
            # The role guard refuses an unverified session before the care-team check,
            # so this case never reached the boundary it declares. Report the cause
            # rather than the symptom: the environment owes a second factor.
            return Result(
                case_id,
                "FAIL",
                f"actor {actor_source_id} has an unverified MFA session, so the request "
                f"was stopped by the MFA gate before reaching the "
                f"'{expected_reason}' boundary this case tests",
            )
        return Result(
            case_id,
            "FAIL",
            f"audited reason_code was '{actual_reason}', fixture declares '{expected_reason}'",
        )

    return Result(case_id, "PASS", f"HTTP {expected_status}, audited as {actual_reason}")


def main() -> int:
    api_base = _env("MEDIAGENT_API_BASE_URL", "http://localhost:8000").rstrip("/")
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    password = _env("DEMO_ACCOUNT_PASSWORD")

    patient_ids = _patient_ids_by_email(supabase_url, service_key)
    results = [
        _run_case(
            case,
            api_base=api_base,
            supabase_url=supabase_url,
            service_key=service_key,
            password=password,
            patient_ids=patient_ids,
        )
        for case in _load_cases()
    ]

    width = max(len(r.case_id) for r in results)
    for result in results:
        print(f"{result.status:<5} {result.case_id:<{width}}  {result.detail}")

    failed = [r for r in results if r.status == "FAIL"]
    skipped = [r for r in results if r.status == "SKIP"]
    print(
        f"\n{len(results) - len(failed) - len(skipped)} passed, "
        f"{len(failed)} failed, {len(skipped)} skipped"
    )
    if skipped:
        print("Skipped cases are unverified, not verified. They remain open work.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
