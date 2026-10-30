# Email templates

This folder holds one template that can be installed and three design references. No
application code loads any file here: the backend renders its own emails in
`backend/src/app/services/email_templates.py`. The delivery and acceptance contract is
[EMAIL-001](../../.agent/specs/email-001-email-flows.md).

| File | Status | Use |
| --- | --- | --- |
| [`supabase-password-recovery.html`](supabase-password-recovery.html) | **Installable** | The Supabase Reset password template. See [Password recovery](#password-recovery) |
| [`reference/password-recovery.html`](reference/password-recovery.html) | Reference | The original supplied design that the installable template replaced |
| [`reference/signup-confirmation.html`](reference/signup-confirmation.html) | Reference | For future use. Signup confirmation is off; do not enable it until signup supports pending verification |
| [`reference/care-plan-updated.html`](reference/care-plan-updated.html) | Reference | For a possible future care-plan email. Nothing sends it today |

## Reference templates

Keep these for future work. They were extracted from the requester-provided
`MediAgent Emails (standalone).html` on October 11, 2026, without its JavaScript bundle or
preview wrapper, and are kept unchanged.

They are English examples with placeholders, not send-ready messages. Before using one:

- Add reviewed es-MX copy, plain text and safe links.
- Require verified mailbox ownership and optional-email consent. The example footer saying a
  clinic added the patient does not establish consent.
- Fill it only from authoritative data, and escape dynamic values. Never manufacture a
  clinician approval, clinic address or publication date to fill a placeholder.
- Keep the Supabase placeholders `{{ .ConfirmationURL }}` and `{{ .Email }}` in Auth templates.
  Installing a dashboard template is a separately authorized remote configuration change.

## Application emails

`backend/src/app/services/email_templates.py` uses the responsive table layout
with escaped HTML and plaintext and requires an explicit `audience`:

- `patient`: the reference palette (sand canvas, emerald `#147465` action,
  "MediAgent" wordmark) in en-US or es-MX from the saved preference.
- `clinician`: the clinician portal brand from `apps/clinician-portal`:
  primary blue `#2563EB` (`--color-primary`) for the button, links and the
  "Pro" in the "MediAgent Pro" wordmark, the navy M-check tile of
  `public/brand/mark-sidebar.svg` (`#1E293B`, white M, `#60A5FA` check), the
  light workspace canvas `#F4F6FA` and slate text. Always English. White on
  `#2563EB` is 5.2:1; footer text uses `#475569` (7.0:1 on the canvas).

Clinician invitations, clinician verification codes and notices addressed to
clinicians (shared review work, appointment responses, unread messages) use the
clinician brand; everything addressed to a patient uses the patient brand.
Application notices contain no clinical details, filenames, patient identifiers
or message bodies.

## Password recovery

`supabase-password-recovery.html` is the deployable Auth template.
Supabase allows one Reset password template per project, so this one file has
three variants, chosen with standard Go-template `eq` conditions on the exact
approved reset URL the backend sends as `redirect_to`:

| Variant | `.RedirectTo` | Brand and language |
| --- | --- | --- |
| Patient en-US | `https://app.mediagent.live/reset-password?lang=en-US` (and any other value) | Patient, English |
| Patient es-MX | `https://app.mediagent.live/reset-password?lang=es-MX` | Patient, Spanish |
| Clinician | `https://clinician.mediagent.live/reset-password?lang=en-US` | Clinician ("MediAgent Pro"), English |

The backend builds these from `PATIENT_PORTAL_URL` / `CLINICIAN_PORTAL_URL` plus
`/reset-password?lang=…`; if either portal URL changes, update the template's
comparison strings and the Supabase Redirect URLs allowlist together.

Every variant uses the same short structure: label, heading, one sentence with
the link lifetime ("Use the button within 1 hour to choose a new password. The
link works once." / "Usa el botón en menos de 1 hora para elegir una nueva
contraseña. El enlace funciona una sola vez."), the button, one note, and a small
footer with the fallback link, the no-reply/password notice and the prototype
line. One hour is Supabase's default email link lifetime; if Supabase →
Authentication → Email "OTP expiry" is changed, change this copy in all three
variants to match. Application emails share the same footer structure.

The button and fallback link are scanner-safe: they point to the portal reset
page itself, `{{ .RedirectTo }}&token_hash={{ .TokenHash }}&type=recovery`, not
to Supabase's single-use `{{ .ConfirmationURL }}` verify endpoint, which
institutional link scanners consume before the person clicks. Opening the page
redeems nothing; the page removes `token_hash`/`type` from history and calls
`verifyOtp` only when the person selects **Continue to choose a new password**.
Links sent with the older `#access_token` fragment still work. Because
`.RedirectTo` already contains `?lang=…`, the template appends with `&`; the
Supabase Redirect URLs allowlist must still contain exactly the three reset URLs
above (unchanged). A redirect missing from the allowlist falls back to the Site
URL, which has no query string, and would produce a broken link.

Install it in Supabase → Authentication → Emails → **Reset password** only, with
separate authorization, and **re-install it after every change to this file**.
Suggested shared subject: `MediAgent — Password reset / Restablecer contraseña`.
Do not activate signup confirmation.
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
