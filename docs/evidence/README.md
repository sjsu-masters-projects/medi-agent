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
| [COM and SAFE gap audit](com-safe-gap-audit-2026-10.md) | Code-level audit of conversations and safety controls, October 22 | Static read of the code; nothing in it was run |
| [Interface wording review](loc-001-interface-review.md) | Spanish interface wording inventory and its project acceptance | Model-assisted review on the requester's authority, not human sign-off |
| [Operating-guide receipts](operating-guide-receipts-2026-10.md) | Migration application reports and rollout notes moved out of the operating guides | The hosted ledger and the task board stay authoritative |
| [OPS-005 root-cause analysis](ops-005-rca-2026-10.md) | Intermittent page failures: log evidence, cause, fix and what cannot be proven | Supported by backend logs, not browser logs from the original episodes |
| [SEC-004 CI correction](sec-004-pr230-ci-2026-10-29.md) | Python dependency audit advisories and the PR #230 CI correction | Local and CI evidence, not a deployed check |

## Confirmed symptom intake

| Report | Scope |
| --- | --- |
| [October 10 checkpoint](pat-002-b-acceptance-2026-10-10.md) | Initial source audit and safety behavior |
| [October 12 local acceptance](pat-002-b-acceptance-2026-10-12.md) | Implementation, paired-language candidate and local journey |
| [October 17 onward review closure](pat-002-b-acceptance-2026-10-17.md) | Review, integration tests and later merge receipts |

The [intake specification](../features/symptom-intake.md)
defines the behavior. The [rollout guide](../pat-002-b-rollout.md) defines activation.
Physical voice acceptance remains separate from mocked transport or permission tests.

## Approved care-plan feed

[PAT-005 acceptance](pat-005-final-acceptance-2026-10-10.md) records the earlier
approved-plan-to-Today journey. Read it with the current
[care-team plan contract](../features/care-plans-and-today.md),
which extends ownership and cross-plan behavior.

## Patient record clarity

| Report | Scope |
| --- | --- |
| [Clarity changes](rec-001-ux-2026-10-28.md) | Refresh, review labels, saved-language explanations and modal close |
| [Patient removal](rec-001-removal-2026-10-28.md) | Restricted upload removal and the private request handoff |
| [Icons](rec-001-icons-2026-10-29.md) | Neutral document and file-format icons in both portals |
| [Motion and state feedback](rec-001-motion-2026-10-29.md) | Processing, completion and error states on Records |
| [Commit review](rec-001-review-2026-10-29.md) | Review findings and fixes on the combined change |

The [record clarity contract](../features/patient-records.md)
defines the behavior.

## Interface wording

[October 22 interface wording review](spanish-interface-wording-2026-10-22.md)
records English/es-MX meaning-and-safety acceptance for the exact paired-source
snapshot, with later addenda. Its JSON receipt is machine-checkable; it is not clinical
validation, professional translation certification or a deployed/device acceptance run.

## Adding evidence

Record the date, commit or revision, environment, synthetic account role, action,
expected outcome, observed result and remaining gap. Reference identifiers only
when needed and safe. Do not include credentials, real health data or private reasoning.

Local tests, a successful deployment and live acceptance are different claims.
Preserve failures and interruptions; do not rewrite an old result into a new pass.
See [documentation maintenance](../maintaining-docs.md).
