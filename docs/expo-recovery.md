# Expo recovery notes

Use this during the [demonstration](expo-demo-script.md). Preserve the saved
record first; shortening the presentation is preferable to duplicating a clinical
action or bypassing an approval boundary.

## Quick decisions

| Symptom | Safe action | Avoid |
| --- | --- | --- |
| Login expired or MFA required | Let the presenter sign in on the site; keep password/code off the recording | Pasting credentials, removing MFA or changing Auth settings |
| Nora disconnects or is still replying | Allow reconnection, inspect the saved turn/history, use the existing Retry only when offered | Sending the same question as a fresh action repeatedly |
| Nora draft text resets | Wait for the saved/backup reply; a draft is not the durable answer | Treating a transient draft as the saved clinical record |
| Reply fails with an uncertain action | Inspect the relevant saved report/task and follow the existing recovery guidance | Repeating a possibly executed symptom handoff or clinical action |
| A read fails or appears stale | Use the screen's refresh/retry and confirm patient, team, filter and time zone | Treating unavailable data as an empty record or a zero count |
| A source cannot be opened | Show the unavailable status; dismiss invalid chat context before a new unrelated question | Inventing a source, changing its ownership or silently using the entire chart |
| An import hits a limit | Explain that the full request was refused; use an agreed smaller synthetic fixture later | Claiming a truncated record was complete or weakening limits live |
| Plan approval is blocked | Show the exact source/wording/conflict blocker and retain the active version | Removing guards, editing SQL or approving unverified wording |
| A download fails | Retry only after checking access/session. Open an existing approved PDF in a supported viewer if available | Saying export succeeded without a file; confusing preview with approval/export |
| Voice is unavailable or permission denied | Use typed input and text answers; stop microphone capture | Forcing OS permissions, changing device security or voice-only confirmation |
| Email has not arrived | Show only the provider/application state actually recorded; check spam privately | Claiming accepted means delivered/read, or resending invitations repeatedly |
| Appointment time differs | Inspect saved time zone and exact visit. A downloaded ICS is a one-time copy | Rebooking during troubleshooting or claiming automatic calendar sync |

## Presenter fallback

1. Say which live dependency failed and what remains saved. Do not speculate about
   root cause without logs or describe unrelated failures as the same incident.
2. Switch to the dated synthetic recording or prepared source-linked history.
   State that it is recorded, name its date/revision and do not imply it happened live.
3. Skip the failed optional segment. Continue with approved static state where useful.
4. Record the symptom, time, route, non-sensitive request identifier if available,
   expected/actual result and whether saved state persisted. Never record tokens,
   passwords, service-role keys, full provider errors or real patient data.
5. Diagnose after the presentation using the owning runbook. A new configuration,
   migration, deployment or reset requires specific authorization.

## Reset and rollback boundary

There is no one-click reset instruction in this run sheet. Keep shared QA histories,
clinical audit records and accounts intact. To rebuild a dedicated synthetic
scenario, agree on the exact target and account set first, then follow the guarded
[environment procedure](demo-environment.md). Do not rerun a seed against production,
edit applied migrations or recreate accounts merely because a display is wrong.

Runtime account rollback and queue configuration belong to the
[worker runbook](chat-worker-setup.md#least-privilege-runtime-accounts).
SQL application/verification belongs to the
[database guide](supabase_setup_guide.md#apply-migrations).
Reading these links does not authorize operating them during the demo.

## Rehearsal record

Capture application revision, fictional actor names, browser/device, route and
time zone, allowed live actions, interruption and recovery outcome. Keep actual
results in the [evidence directory](evidence/README.md) and reference them from
the task board. This document contains procedures, not a claimed completed rehearsal.
