# Transactional email design reference

These three standalone HTML templates were extracted from the requester-provided
`MediAgent Emails (standalone).html` on October 11, 2026. They preserve the supplied
design without copying its JavaScript bundle or preview wrapper. The governing
delivery and acceptance contract is [EMAIL-001](../../.agent/specs/email-001-email-flows.md).

## Integration boundaries

- `password-recovery.html`: Supabase Auth template candidate. Keep
  `{{ .ConfirmationURL }}` and `{{ .Email }}` as Supabase placeholders. Installing
  a dashboard template is a separately authorized remote configuration change.
- `signup-confirmation.html`: reference only while confirmation is disabled.
  Do not enable confirmation until signup supports pending verification.
- `care-plan-updated.html`: application-email reference, not an active sender.
  Substitute only authoritative published-plan data, escape dynamic values and
  require verified mailbox ownership and optional-email consent. Never manufacture
  clinician approval, clinic address or publication date to fill a placeholder.

These supplied examples are English. Patient delivery also needs reviewed es-MX
copy, plain text and safe links. Do not infer eligibility from the example footer
that says a clinic added the patient: email consent is a separate requirement.

## Implemented adapters

`backend/src/app/services/email_templates.py` uses the reference palette and
responsive table layout with escaped bilingual HTML and plaintext. Application
notices contain no clinical details, filenames, patient identifiers or message
bodies. The supplied files above remain unchanged references, not active senders.

`supabase-password-recovery.html` is the deployable Auth-template candidate.
Its standard Go-template `eq` condition selects es-MX only for the exact approved
Spanish patient reset URL; English patient and clinician links use English.
Install it in the **Reset password** template only, with separate authorization.
Suggested shared subject: `MediAgent — Password reset / Restablecer contraseña`.
Keep `{{ .ConfirmationURL }}` intact. Do not activate signup confirmation.
Supabase controls Auth MIME delivery; the backend plaintext renderer does not
prove Auth plaintext or actual inbox rendering.

## Visual and delivery checks

Open each standalone file directly to inspect its 600px table-based layout. Check
at 360px and desktop widths, including fallback links, long text and dark mode.
Browser rendering does not establish compatibility with every email client.

Placeholder previews are not send-ready messages. Do not send an email until its
placeholders are validated and real sender/destination values are configured.
Provider acceptance, inbox delivery and authenticated click-through are separate
acceptance steps. Current progress stays on the task board, not in this directory.
