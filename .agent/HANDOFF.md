# Session handoff

**What this file is:** the things a new contributor session needs that the tracker cannot
carry — environment limits, traps that have already cost someone hours, and decisions
waiting on a human.

**What this file is not:** a status report. `.agent/TASKS.md` is the execution source of
truth and `.agent/TEAM.md` owns the allocation. Nothing here restates them, because a
second copy of the status is how the previous handoff ended up asserting things that were
no longer true.

---

## Read the tracker, then verify the rows you are about to rely on

`.agent/TASKS.md` is authoritative for status, but individual rows go stale between
updates. Two examples found on 2026-09-09, both of which had been repeated as fact:

- The MCP/A2A row said "A2A implementation files are empty". The task service and retry
  worker were 545 lines and the worker started with the application. What is genuinely
  missing is `/.well-known/agent-card.json` and the delegation flow.
- A finding circulated that the committed env templates pointed at a deleted Supabase
  project. The reference had already been removed; the templates carry empty placeholders,
  which is the normal convention.

The `AI-001` adapter row had the same shape: it read as though MedGemma had no adapter,
when the client was complete and only the comparison was missing.

**Practical rule:** before quoting a row as a reason to do or skip work, re-run the thing
it describes. Test counts, coverage, migration counts, and dependency audits are all
cheap to re-measure and all have been wrong at least once.

## Start-of-session checks

- `git fetch && git log --oneline origin/main -1`. `main` has moved mid-session before.
- `npm audit` in both portals. Advisories are published continuously; a "zero
  vulnerabilities" record has a shelf life of days. Two critical advisories appeared
  against a pinned version hours after an audit recorded it clean.
- `backend/.venv/bin/python --version` must report 3.12 or newer.

## Environment limits in a hosted session

Egress is policy-controlled and varies between environments. Verify rather than assume —
the previous handoff recorded Supabase over HTTPS as working, and in a later session the
proxy refused it.

| Operation | Observed 2026-09-09 |
|---|---|
| `git clone` / `fetch` / `pull` / `push` | works once the repository is authorized for the session |
| npm, PyPI, crates, Go proxy | works |
| Supabase, on any port | refused by egress policy |
| Postgres `:5432` and the pooler `:6543` | refused; raw TCP is not supported |
| Deployed `*.mediagent.live` | refused |

Consequences worth planning around:

- **Migrations cannot be applied from a hosted session, with any credential.** They need a
  machine with direct network access. `scripts/apply-supabase-migrations.sh` is
  ledger-backed and checksum-verified; stop and escalate on `Checksum mismatch`.
- Anything that must talk to staging — seeding, the denial verifier, provider comparison —
  runs locally, not here.

## Deploy ordering, and why it constrains schema changes

`deploy-backend.yml` deploys to Cloud Run on any push to `main` touching `backend/**`.
Migrations are applied by hand. **The code therefore reaches production before the schema
does.**

A change that writes to a new column will fail in that window. Two ways this has been
handled deliberately:

- Migration `033` added a table the application tolerates the absence of: denial auditing
  logs an ERROR and the 403 still returns correctly until the table exists.
- Tiered action authority records the applied tier in an existing `jsonb` audit payload
  specifically to avoid a new column and the window that comes with it.

Prefer one of those shapes over adding a column that the write path immediately requires.

## Traps found the hard way

- **`python3` on macOS is not 3.12.** `scripts/bootstrap-and-validate.sh` prefers
  `python3.12` when present and silently falls back, producing a venv that cannot install
  the locked dependencies. The failure surfaces much later as a missing executable. Build
  the venv with an explicit interpreter path and check `.venv/bin/python --version`.
- **`app` is not installed into the virtualenv.** Only pytest puts `src` on the path, so a
  script under `backend/scripts/` must resolve the source root itself.
- **Importing `app` constructs `Settings`**, which requires the full service environment.
  A CLI that imports it at module scope cannot even print `--help` without credentials.
- **Reading the CodeQL alert:** the code-scanning API returns 403 for this repository, but
  the check-run annotations endpoint is readable and names the exact file and line.

## Never put patient or clinician identifiers in logs

A CodeQL finding on 2026-09-09 flagged clear-text logging of sensitive information where a
care-team classifier logged both identifiers on a failure path. A log store has weaker
access control than the audited table those identifiers belong in.

Log the reason code, the rule id, and the target *type*. The database row carries who and
what. This applies to the paths that fail — those are the moments it is most tempting to
stash an id somewhere, and they are the ones a scanner catches.

## Open decisions that need a person

| Question | Why it is blocked | Whose call |
|---|---|---|
| A clinic admin can obtain a patient invite code, and a patient redeeming it makes the admin an active care-team member recorded as `provider`. `SYN-NEG-004` expects admins denied on role grounds first. | Changes authorization semantics on a live product | Clinician authorization |
| Three fixture actions have no endpoint that owns them: `list_patient_documents`, `view_medication_timeline`, `view_document_metadata`. Their negative-access cases are reported as unverified rather than pointed at an unrelated route. | Needs a product decision on which route owns each action | Product + clinician portal |
| Triage safety rules need clinical sign-off on wording and coverage in both locales. | Not an engineering step | Safety owner + clinical reviewer |
| Pharmacovigilance (`PV-001`, `PV-002`) has no owner in `TEAM.md`. | The whole R4 milestone is unassigned | Team allocation |

## Long-lead items that cannot be compressed

`EVA-001` needs clinician or pharmacist adjudication of 40 high-risk cases, and `PAT-003`
needs clinical review of high-risk bilingual content. The review schedule is still
unassigned. Neither can start in the final weeks before the 2026-12-04 freeze.

## Credentials

Never in this repository, and never pasted into a tool that keeps a transcript. Obtain
them from the team out-of-band. `docs/qa-auth-accounts.md` covers the fixture accounts;
`DEMO_ACCOUNT_PASSWORD` gates them.

Secret scanning runs in CI and cannot see a chat window.

---

*Keep this file short. When something here becomes permanent guidance, move it to
`AGENTS.md` or the relevant doc under `docs/` and delete it from here.*
