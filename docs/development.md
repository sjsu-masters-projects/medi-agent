# Local development

Use the [README quick start](../README.md#run-locally) for installation and
[CONTRIBUTING.md](../CONTRIBUTING.md) for required checks. This guide covers setup
decisions and common failures, not deployment instructions.

## Configuration boundaries

| Configuration | Location | Rule |
| --- | --- | --- |
| Backend configuration | Root `.env`, copied from [`.env.example`](../.env.example) | Server credentials stay on the server |
| Patient public configuration | Patient `.env.local`, copied from its [template](../apps/patient-portal/.env.example) | `NEXT_PUBLIC_*` values are bundled into browser code |
| Clinician public configuration | Clinician `.env.local`, copied from its [template](../apps/clinician-portal/.env.example) | Never include a service-role key |
| Hosted runtime configuration | Secret Manager, repository variables and the deploy workflow | Local files do not configure deployed services |

The backend loads the root `.env` through its settings module, with a working-directory
fallback for container layouts. Never copy local credentials into a worktree just to run
unit tests. Use the synthetic settings documented in the backend test setup.

Authentication needs an authorized development Supabase project. Generation, voice
and email need their own configured services. A page loading successfully does not
prove those integrations are active. See [database setup](supabase_setup_guide.md),
[email configuration](features/messaging-and-alerts.md) and
[worker setup](chat-worker-setup.md).

## Service checks

After starting the three services, check the patient and clinician sign-in pages,
`GET /health` and the backend API reference at `/docs`. Sign in yourself using
synthetic accounts authorized for development. Passwords and MFA codes stay on the site.

Use one hostname consistently in local URLs. `localhost` and `127.0.0.1` have separate
browser storage and sessions. A production login does not sign you into localhost.

## Common problems

| Symptom | Check |
| --- | --- |
| Dependencies fail to install | Use Python 3.12 and the committed lockfiles; confirm `.venv/bin/python --version` |
| Script cannot import `app` | Run from `backend` with `PYTHONPATH=src`; the source package is not installed by default |
| CLI fails before showing help | Some imports construct settings immediately; use the command's documented test settings |
| Port is occupied | Stop your own previous development server or choose a free port and update the matching public API URL |
| Turbopack rejects a dependency symlink | Install dependencies in that checkout with `npm ci`; do not link another worktree's `node_modules` |
| Sign-in works but reset/storage fails | Check the project's public key and configured URLs privately; do not print keys or inspect them in shared logs |
| Recovery link expires before use | Mail scanners can open links; follow the explicit-click recovery flow in the email contract |
| SQL behavior differs from mocks | Run the affected disposable PostgreSQL contracts, including authorization and transaction failures |
| A hosted service cannot be reached | Check the current environment's network policy; do not assume an old session's connectivity still applies |

## Changes that need separate permission

Local code and tests do not authorize hosted migrations, IAM grants, secret changes,
seeding, deployment or clinical publication. Stop at the documented apply gate and
name the exact target and action needed. A checksum mismatch requires investigation,
not editing the ledger or an applied file.

## Runtime implementation notes

- Use relative asynchronous timeouts where event-loop clock differences matter.
  A default-loop test does not establish uvloop deadline behavior.
- A model or provider success is not a saved clinical decision. Verify the source
  write, audit and authorized review path separately.
- CI reads PR policy metadata when a run starts and scans the committed range.
  Changing only the current file does not remove an exposed value from earlier commits.
- Deployment may start automatically after merge. Required migrations and runtime
  variables must be prepared in the order stated by the PR and operating guide.

## Historical questions to verify before relying on them

The retired session handoff recorded unresolved clinic-admin invite semantics and
three synthetic negative cases without a named owning endpoint:
`list_patient_documents`, `view_medication_timeline` and `view_document_metadata`.
Treat these as historical test gaps, not current authorization requirements. Check
the current [task requirements](../.agent/specs/project-backlog-acceptance.md) and
the [interoperability plan](features/patient-records.md)
before changing behavior or declaring the cases covered.
