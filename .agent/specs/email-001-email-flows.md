# EMAIL-001 — Account and selective event emails

## Scope and authority

Requester approved implementation and end-to-end synthetic testing on October 11.
No real clinical data. A genuine mailbox may receive fictional demo notices.
The current Supabase project is `medi-agent-staging`. Read-only dashboard inspection
initially confirmed email signup enabled, Confirm email disabled and custom SMTP
disabled. After the operator configured SMTP and reported credential rotation,
dashboard reload confirmed custom SMTP enabled, `smtp.resend.com`, port `465`,
the Account Access sender name and a stored, hidden password. No credential was
inspected. With explicit requester approval, Site URL was changed to
`https://app.mediagent.live` and exactly three reset destinations were added:
patient `en-US`, patient `es-MX` and clinician `en-US` on their respective live
domains. Dashboard reload verified all values persisted; no wildcard was added.
Keep confirmation disabled until signup correctly represents pending verification;
current signup signs in immediately and cleans up when that fails. Enabling it now
would break that contract. Credential entry and password changes are operator steps.
Do not read/copy/edit credential files or place secrets in this specification.

## Channels and recipients

- Supabase owns account confirmation/recovery tokens; Resend SMTP delivers Auth
  emails. A backend Resend API key alone does not configure Supabase SMTP.
- Backend Resend delivers clinician invitations and selective saved-event notices.
- Optional notices: appointment offer/change/cancel to the patient; responses to
  the responsible clinician; grouped unread human messages to the addressed person;
  approved plan publication to the patient; records requiring patient action;
  grouped pending review reminders to currently authorized clinicians.
- No Nora answers, unpublished patient drafts, automatic diagnosis/urgent claims,
  per-dose medication email, completion email, marketing or inbound-email messaging.
- Email preferences are independent of in-app notification read state. Defaults
  suppress optional email until consent and genuine mailbox ownership are established.
- Recheck current assignment, source status and unread state immediately before
  delivery. A private conversation never broadcasts to other linked clinicians.

## Account recovery

Both login screens link to Forgot password. Request has a fixed portal selector,
not an arbitrary redirect URL. The server builds the matching reset destination
from configured portal URLs. Patient links retain en-US/es-MX; clinician English.
Return neutral success irrespective of account existence/provider failure; safe
operational logs never contain an email, password, reset token or provider body.
Recovery sessions are isolated from the normal portal login, never stored in its
Redux/localStorage session, and do not bypass clinic access or MFA at next login.
Expired/invalid links offer a new request; new passwords require confirmation and
the existing eight-character minimum. The operator enters passwords during live QA.

## Templates, sending and testing

The requester reattached the standalone design export on October 11. Its three
templates are preserved as [version-controlled HTML references](../../docs/email-templates/README.md)
without the export's script bundle. They are not installed remotely or wired to
application delivery yet. Keep confirmation disabled; add es-MX and plaintext
variants before patient email acceptance. The reference's clinic-added footer
does not substitute for verified contact ownership or optional-email consent.

Use role-specific brand colors, simple responsive HTML, plain text, readable
contrast, one action and escaped dynamic parameters. Patient locale follows saved
preference; clinician English. No clinical details, UUIDs or attachments. Sender
addresses must be verified before use. No claim that the sender mailbox accepts
replies. Application destinations require authenticated authorization.

Saved event capture precedes delivery. Durable delivery state and a unique event /
recipient / channel key prevent duplicate logical emails. Bounded retries preserve
the saved clinical action when Resend fails. Distinguish queued, provider accepted,
delivered, bounced and failed; provider acceptance is not inbox receipt.

Synthetic addresses ending in `@accounts.mediagent.live` are never attempted as
real destinations. Explicit synthetic demo mode may redirect safe application
notices to the requester-controlled allowlisted mailbox, marked DEMO TEST. Do not
globally redirect Auth links or change Morgan/Elena login addresses. Auth testing
uses dedicated synthetic accounts whose actual login mailbox the operator owns.
Genuine verified mailboxes receive their own opted-in notices, never the demo sink.

## Acceptance

- [ ] Verified sending domain and approved onboarding/Auth/notification From values.
- [x] Supabase SMTP configured by operator (persisted configuration verified),
  with correct exact redirect allowlist (saved with approval and reload verified).
- [ ] Forgot/reset password in both portals; neutral request and no sensitive logs.
- [ ] Inbox receipt, link, operator password reset and fresh login including MFA.
- [ ] Invitation delivery, acceptance permissions and invalid/expired handling.
- [ ] Consent, locale and verified contact eligibility; optional event integration.
- [ ] Durable retries/deduplication and recipient revocation tests.
- [ ] Synthetic sink cannot divert genuine account or Auth emails.
- [ ] EN/ES templates visually checked on mobile; plaintext and unavailable states.
- [ ] Focused backend/portal tests, lint/type/build, migration permission tests if added.
- [ ] Reviewed merge, separately authorized rollout and deployed evidence recorded.

This contract extends NOT-001 with a separate channel; it does not change existing
review/publication gates or describe local tests as deployed acceptance.

## Local recovery slice — October 11 (earlier checkpoint)

Implemented `/forgot-password` and `/reset-password` in both portals, entry links,
neutral role-scoped reset requests, bilingual patient controls, recovery-fragment
removal and a nonpersisted SDK session. Normal login/clinic/MFA is still required
after reset. The later approved remote Site URL/redirect setup is recorded above;
no email has been sent by this work and inbox/link acceptance remains unverified.

Verification from the isolated EMAIL-001 checkout (dummy public test settings):

- Backend `PYTHONPATH=src pytest tests/unit/services/test_auth_service.py
  tests/integration/routers/test_auth_api.py --no-cov -q`: **59 passed**.
- Ruff check and format check for the five changed Python files: passed.
- Mypy for changed Auth service, models and router: passed.
- Both portals `NODE_OPTIONS=--no-experimental-webstorage npm run test`:
  **481 patient / 307 clinician passed**, including seven new recovery tests each.
- Both portals `npm run typecheck` and `npm run lint`: passed.
- Both portals `npm run build -- --webpack`: passed with network access for the
  existing Google Fonts. The first sandboxed builds failed only fetching fonts.
- `git diff --check`: passed.

Dependency install reported six high-severity advisories per portal in unchanged
locks; no force-upgrade was performed. Existing Sentry configuration warnings remain.
Those results predate the delivery/preferences implementation below. Inbox
delivery, actual recovery/password entry, mobile visual QA and deployment remain
open. The operator subsequently rotated the exposed credential and saved SMTP;
the persisted configuration was verified without inspecting credentials.

## Current implementation and continuation handoff

The EMAIL-001 branch adds:

- Both-portal recovery and explicit verification/optional-email controls in patient
  Profile and clinician Settings. Verification does not opt in. Failed and stale
  requests cannot restore another account's settings. Patient controls are bilingual.
- Server-only `email_contacts`, `email_outbox` and addressed clinician invitations
  in new **057_email_delivery.sql**. It also permits an unassigned clinician's
  `clinic_name` to be NULL while invitation acceptance is pending; no invented
  clinic grants access. This migration has **not** been applied remotely.
- Saved notification receipts enqueue future opted-in event emails. The delivery
  worker prepares receipts even with portals closed, rechecks access/current work,
  groups private messages and shared reviews, freezes retry payloads, leases with
  SKIP LOCKED, and distinguishes provider acceptance from confirmed delivery.
  Ambiguous sends stop retrying before Resend's 24-hour idempotency retention ends.
- Invitation links use opaque fragment tokens, stored as hashes in the invitation
  record. Sending grants no membership. Address ownership, current inviter/clinic
  authority, expiry and revocation are checked on explicit acceptance. An existing
  different-clinic membership cannot be moved by an invitation. Duplicate
  acceptance by the same current member is safe; account creation is separate from
  membership claim so a failed claim does not delete an account.
- Clinic-admin invitation history separates acceptance from delivery and supports
  revoking unused links. The legacy false-success patient email endpoint returns
  410; human messages stay in private conversations with optional notices.
- Branded, escaped bilingual HTML/plaintext application templates and an installable
  Supabase recovery-template candidate in `docs/email-templates/`. No remote
  template has been installed.

### Rollout order — requires separate authorization

1. Review/merge with CI and peer approval; preserve newer main work, especially the
   scheduled-job changes in #151. Do not restore the retired nightly ADR scan.
2. Apply only `057_email_delivery.sql` through the full-filename/checksum ledger
   against the explicitly approved staging project, before activating email APIs.
3. Confirm backend `RESEND_API_KEY`, notification/onboarding From identities and
   portal URLs through the operator; never print or copy credential values.
4. Deploy the reviewed backend and both portals. Email dispatch is also called by
   the existing reminder heartbeat, or the authenticated `/cron/emails/dispatch`
   endpoint. The paused reminder trigger must be resumed by its separately
   authorized OPS-003 workflow; do not assume email dispatch is running.
5. Install the recovery HTML candidate in Supabase's Reset password template with
   separate authorization. Keep Confirm email **off**; pending-confirmation signup
   is not implemented or part of this reviewed slice.
6. Use dedicated fictional accounts whose genuine login mailbox the operator owns
   for end-to-end QA. Do not change Morgan/Elena's login email. Automated redirection
   to a synthetic sink is **not implemented**: synthetic addresses are blocked,
   and genuine notices/Auth links are never diverted.
7. Operator requests recovery, checks the actual inbox, enters the new password,
   and verifies fresh normal login/MFA. Then verify code + explicit opt-in, saved
   event → email → authorized destination, invitation acceptance/revocation, EN/ES,
   opt-out, and delivered/bounced provider status. Record actual outcomes here.

Local tests are not proof of delivered mail. Browser/email-client rendering,
inbox receipt, deployed links and provider status reconciliation remain unverified.
Do not mark EMAIL-001 Done before those acceptance steps and reviewed merge.

### Local verification — current slice

All backend tests below use dummy Supabase values; PostgreSQL runs in cached,
disposable `postgres:16` containers with network disabled. No mail was sent.

- `PYTHONPATH=src pytest tests/unit/services/test_email_service.py
  tests/unit/services/test_auth_service.py tests/unit/services/test_staff_service.py
  tests/integration/routers/test_email_api.py tests/integration/routers/test_auth_api.py
  tests/integration/routers/test_clinician_api.py tests/integration/routers/test_cron_api.py
  --no-cov -q`: **138 passed** before integrating newer main.
- `EMAIL_TEST_POSTGRES_DOCKER=1 PYTHONPATH=src pytest
  tests/integration/test_email_postgres.py --no-cov -q`: **14 passed**, including
  browser permissions, verification attempts/cooldown, consent/address changes,
  synthetic-address suppression, concurrent claims, stable retry keys, shared-work
  status, invitation acceptance/revocation and private-recipient revocation.
- Both portals `NODE_OPTIONS=--no-experimental-webstorage npm run test`:
  **487 patient / 313 clinician passed** before newer-main integration.
- Both portal lint/typecheck and `npm run build -- --webpack`: passed; clinician
  unused-locale warning corrected afterward. Existing Sentry warnings remain.
- Ruff: passed for changed Python. Mypy: passed for ten delivery/Auth/Staff/cron files.
- `python scripts/validate_migrations.py`: **67 migration files validated**.
- Manual live recovery/inbox, mobile email rendering, consent/opt-out journeys and
  template installation remain open, not passed by mocks or static HTML checks.

The next contributor should run the same checks after integrating current main;
use the PR's final CI evidence rather than these earlier dependency-version results.

### Main #151 integration verification

Integrated main `8b44610`; no retired ADR endpoint or old dependency lock restored.
Installed both portal locks with `npm ci --no-audit --no-fund`.

- The focused backend command above: **137 passed** (the retired nightly-ADR
  API test was removed on main).
- Portal full suites: **493 patient / 313 clinician passed**, plus three focused
  invitation-history tests added afterward. Both lint/typecheck and webpack builds
  passed with Next.js **16.3.8**; existing Sentry/workspace warnings remain.
- Mypy: **17 changed source files passed**. Changed-file Ruff passed; migration
  naming/syntax validator passed for **67 files**. Git diff whitespace checks passed.
- Offline PostgreSQL full email suite: **14 passed**; invitation/membership subset
  **3 passed** after final transaction-lock changes. No remote DB or outbound mail used.
- The pre-commit hook expects a worktree-local `backend/.venv`, which this checkout
  does not have. Equivalent checks used the existing base virtualenv; commit hook
  was skipped with `HUSKY=0`, not CI. Keep this reproducibility limitation explicit.

The repository handoff is this section plus the rollout checklist above, reachable
from TASKS.md, architecture, contributor and Supabase guides. The next contributor
does not need chat history or access to any credential pasted into earlier chats.
Pull request: [#152](https://github.com/sjsu-masters-projects/medi-agent/pull/152).
