# Symptom question releases

The questions Nora asks during a confirmed symptom intake are released as numbered
versions. There is one process, and every wording change goes through it.

| Release | Stored version | File | Review record | Status |
| --- | --- | --- | --- | --- |
| v2 | `v2` | [v2.json](v2.json) | [v2-review.md](v2-review.md) | Active |
| v1 | `candidate-1` | [v1.json](v1.json) | [v1-review.md](v1-review.md) | Retired for new intakes, kept for pinned drafts and reports |

v1 keeps the stored identifier `candidate-1` because applied intakes, confirmed reports and
the hosted eligibility row reference it, and its canonical hash covers that identifier. The
`label` in `manifest.json` is what people see, so clinicians read `v1`. New releases use the
same value for both.

## Release a change

1. Copy the latest release to `vN.json`, set its `version` to `vN` and edit the wording. Never
   edit a released file: a draft in progress is pinned to the version and hash it started with.
2. Write `vN-review.md` with the changed wording in both languages and an `## Approval` section
   that records who decided, their role, the date, and what kind of review took place. State
   plainly when there was no independent clinical review.
3. Add the release to `manifest.json` with its canonical SHA-256 and approval, and point
   `active_version` at it. The hash comes from `Bundle.checksum` in
   [library.py](../library.py); the service refuses to load a mismatch.
4. Merge, then publish the release to the database as soon as the backend deploys:

   ```bash
   cd backend
   PYTHONPATH=src .venv/bin/python scripts/publish_symptom_questions.py          # report only
   PYTHONPATH=src .venv/bin/python scripts/publish_symptom_questions.py --apply
   ```

   The script publishes only the active version, is safe to repeat, and confirms the result.
   Until it runs, new intakes fail closed with "unavailable"; drafts already in progress
   continue. No migration or Cloud Run change is needed.

## Roll back

Set `active_version` back to the earlier release and deploy. Its eligibility row already
exists, so no publish is needed. Drafts started on the withdrawn release keep their pinned
wording. To stop a release from being used at all, revoke its eligibility through an explicitly
authorized database change; revoked versions cannot progress or confirm.

## What this does not establish

An approval here covers the wording of a synthetic demonstration package. It is not
professional clinical validation. The package has no symptom-specific branch or structured
red-flag mapping, and it generates no medical rule. Test fixtures use test injection and do not
create an approval.
