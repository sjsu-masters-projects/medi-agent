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

The requester's design export (October 11) is preserved as
[version-controlled HTML references](../../docs/email-templates/README.md). Application
emails are rendered by `backend/src/app/services/email_templates.py` (escaped HTML and
plaintext, patient en-US/es-MX, clinician English in the MediAgent Pro blue). The
scanner-safe Supabase Reset password template, `supabase-password-recovery.html`, is
installed (October 12) and must be reinstalled after every change to that file.
Confirmation stays disabled. The reference's clinic-added footer does not substitute
for verified contact ownership or optional-email consent.

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

- [x] Verified sending domain and From values: `mail.mediagent.live`; SPF, DKIM and
  DMARC pass on delivered mail.
- [x] Supabase SMTP configured by operator, with the exact three-URL redirect allowlist.
- [x] Forgot/reset password in both portals: clinician and patient passed on production.
- [ ] Inbox receipt, link, operator password reset and fresh login: passed for the
  clinician; MFA after reset not exercised (the test account has no factor).
- [x] Invitation delivery, acceptance permissions and invalid/expired handling.
- [x] Consent, locale and verified contact eligibility; optional event integration
  (unread message, Spanish appointment notice, opt-out).
- [x] Durable retries/deduplication and recipient revocation tests (PostgreSQL suite).
- [x] Synthetic addresses are never sent to; genuine account and Auth email is never diverted.
- [ ] EN/ES templates visually checked on mobile; patient en-US/es-MX and clinician reset emails received and checked on desktop.
- [x] Focused backend/portal tests, lint/type/build and migration permission tests.
- [ ] Provider delivery status (needs a full-access Resend key).
- [x] Reviewed merge (#152, #156, #157), authorized rollout and deployed evidence recorded.

This contract extends NOT-001 with a separate channel; it does not change existing
review/publication gates or describe local tests as deployed acceptance.

## Implementation

- **Recovery:** `/forgot-password` and `/reset-password` in both portals. The backend
  builds the reset destination from the portal URL and locale and answers neutrally.
  The email links to the portal page with `token_hash`; the page removes it from history
  and calls `verifyOtp` only after **Continue**, so mail scanners cannot use the link up.
  Older `#access_token` links still work. The recovery session lives in an isolated,
  non-persisted client; a successful save signs out every session, then normal login
  (clinic and MFA checks) follows.
- **Contacts and preferences:** server-only `email_contacts` (057/058). A code proves
  mailbox ownership; verification does not opt in. Consent is stamped only when notices go
  from off to on. Patient controls are bilingual. Five codes per contact per day.
- **Preferences presentation (#158):** patient Profile shows an **EMAIL NOTICES /
  AVISOS POR CORREO** grouped card like the other Profile sections: address with a
  Verified / Not verified / Email unavailable chip, then Send code, code + Verify, or the
  notice checkboxes and Save, and one footnote. Demo addresses get one muted line and no
  controls. Clinician Settings shows the same states in a standard Settings card.
- **Event notices:** saved notification receipts enqueue opted-in email in
  `email_outbox`. Dispatch rechecks access, consent, the address and unread/current
  work, groups private messages (15 minutes) and shared reviews (1 hour), freezes retry
  payloads and leases rows with SKIP LOCKED. Links go to `/notifications` (patients) or
  `/alerts` (clinicians) with no identifiers.
- **Invitations:** opaque fragment tokens stored as hashes; sending grants nothing.
  Only clinic admins invite. Acceptance checks the address, inviter authority, expiry and
  revocation; signup claims the invitation in the same request, and an existing account
  uses **Sign in to accept**. History separates delivery from acceptance and supports
  revoking unused links.
- **No auth-schema reads:** a hosted migration cannot grant `service_role` access to
  `auth`, so the backend reads account addresses through the Auth Admin API and SQL
  compares them with the verified contact before every send and acceptance.
- **Provider states:** queued → accepted → delivered / bounced / failed / complained.
  Opened or clicked counts as delivered; a complaint withdraws optional-notice consent.
  Polling stops 72 hours after acceptance.

## Operations and configuration

- Backend: `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_CLINICIAN_ONBOARDING_FROM_EMAIL`,
  both portal URLs and `CRON_AUTH_TOKEN`; optional `EMAIL_CODE_HMAC_SECRET` (falls back to
  the Supabase JWT secret). See `CONTRIBUTING.md` and `.env.example`. Status
  reconciliation needs a **full-access** Resend key; a sending-only key still sends, logs
  one warning and leaves statuses at "accepted".
- Portals: `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` must be the
  project's exact public values. Supabase's `/verify` route does not check the key, so a
  wrong key only shows up when the password is saved.
- New invitations and codes send immediately; failures stay queued. Retries, notices and
  status checks run as the `email_dispatch` job after each reminder run, or through
  `POST /api/v1/cron/emails/dispatch` (`{"dry_run": true}` counts only). See the
  [scheduled jobs runbook](../CLOUD_INFRASTRUCTURE_GUIDE.md#5-scheduled-jobs-cloud-scheduler-and-run-logs).
- End-to-end QA uses dedicated fictional accounts whose genuine mailbox the operator owns.
  Do not change Morgan/Elena's login email. The operator types passwords and codes.

## Production status — October 12

Evidence: [deployed recheck](../../docs/deployed-recheck-2026-10-11.md#email-001-on-production-october-12).
Verified: invitation, verification code, unread-message and Spanish appointment notices,
opt-out, neutral reset request and the clinician and patient password resets (after both portals were
rebuilt with the correct public Supabase key; the earlier builds had it missing its first
character, so the save returned 401 "Invalid API key"). Open:

1. Run one real document upload, which also uses the public key (dashboard realtime is
   disabled in production).
2. Replace the sending-only Resend key with a full-access key so statuses reach delivered.
3. The first invitation landed in Spam; watch placement as the sending domain ages.

Pull requests: [#152](https://github.com/sjsu-masters-projects/medi-agent/pull/152),
[#156](https://github.com/sjsu-masters-projects/medi-agent/pull/156),
[#157](https://github.com/sjsu-masters-projects/medi-agent/pull/157),
[#158](https://github.com/sjsu-masters-projects/medi-agent/pull/158) (email preferences presentation).
