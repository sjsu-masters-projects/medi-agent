# SAFE-003 safety gap hardening

Requester-authorized October 30, 2026 as a separate PR from UX-007 (#232).

## Acceptance path

- Mid-intake medication errors interrupt the draft atomically, persist an urgent
  alert, preserve private draft answers, create no report/ADR task and retry
  failed delivery. All deterministic floor rules persist with their own urgency.
- Chat escalation events retain the actual final urgency.
- Model/override escalations register an immutable pending alert against the saved
  turn, with rule, urgency and delivery state. Existing worker delivery retries it
  without duplicate messages; cross-patient/session links are rejected.
- The legacy patient ADR list and response endpoints return no Naranjo score or causality, even if
  the data source contains them. Clinician review fields remain intact.
- Failed fact translation logs exception type and count only, with no traceback,
  model output or fact text.
- Clinician visit edits and their field changes commit with append-only audit in
  one RPC. Authorization and current lifecycle are rechecked under locks, grouped
  offers keep shared details, and an audit failure rolls the edit back.
- Unsupported-dose detection remains monitoring-only by requester decision.
  Blocking needs a later explicit decision; no clinical validation is claimed.

## Verification and rollout

Meaningful unit/API tests, disposable PostgreSQL contracts for authorization,
idempotency, delivery retry, privacy and rollback; Ruff, mypy, migration validation,
Spanish receipt freshness, docs links and CI. No hosted SQL, deploy or merge is
requested. Additive migrations must be applied to the exact authorized target
before deploying dependent backend code. Safety/peer review and synthetic live
acceptance remain separate gates.
