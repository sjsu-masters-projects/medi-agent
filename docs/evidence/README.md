# Verification evidence

These reports record observations, commands, test results and limitations.
They are not operating instructions or a second task board. Use
[TASKS.md](../../.agent/TASKS.md) for the current verdict and next acceptance step.

## Cross-workflow verification

| Report | Scope | How to read it |
| --- | --- | --- |
| [Deployed portal rechecks](deployed-recheck-2026-10-11.md) | Grouped patient/clinician journeys, defects, fixes and rollout receipts through October 22 | Start with the latest relevant dated section and the task verdict; earlier failures remain historical evidence |
| [Portal UI and language review](portal-ui-ux-review-2026-10-10.md) | Layout, content, localization and screen-level observations | A dated review, not an assertion about the current deployment |
| [Reference redesign verification](ux-002-overhaul-verification.md) | Redesign implementation and local checks | Distinguishes local verification from live acceptance |
| [Earlier task-board checkpoints](task-board-acceptance-history-2026-10-13.md) | Older LOC/ADR/care-plan local test and acceptance records removed from the board | Historical unchecked items are not the current task verdict |

## Confirmed symptom intake

| Report | Scope |
| --- | --- |
| [October 10 checkpoint](pat-002-b-acceptance-2026-10-10.md) | Initial source audit and safety behavior |
| [October 12 local acceptance](pat-002-b-acceptance-2026-10-12.md) | Implementation, paired-language candidate and local journey |
| [October 17 onward review closure](pat-002-b-acceptance-2026-10-17.md) | Review, integration tests and later merge receipts |

The [intake specification](../../.agent/specs/pat-002-b-confirmed-symptom-intake-plan.md)
defines the behavior. The [rollout guide](../pat-002-b-rollout.md) defines activation.
Physical voice acceptance remains separate from mocked transport or permission tests.

## Approved care-plan feed

[PAT-005 acceptance](pat-005-final-acceptance-2026-10-10.md) records the earlier
approved-plan-to-Today journey. Read it with the current
[care-team plan contract](../../.agent/specs/plan-002-care-plans-per-care-team.md),
which extends ownership and cross-plan behavior.

## Adding evidence

Record the date, commit or revision, environment, synthetic account role, action,
expected outcome, observed result and remaining gap. Reference identifiers only
when needed and safe. Do not include credentials, real health data or private reasoning.

Local tests, a successful deployment and live acceptance are different claims.
Preserve failures and interruptions; do not rewrite an old result into a new pass.
See [documentation maintenance](../maintaining-docs.md).
