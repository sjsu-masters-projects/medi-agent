# MediAgent — Team and Delivery Process

## Team allocation

| Member | Primary lane | Required secondary review |
| --- | --- | --- |
| Rajeev Chaurasia | Platform, Supabase, security, FHIR, SMART, deployment | Clinician authorization |
| Ganesh Thampi | Worker runtime, provider adapters, evidence, safety, evaluation | Voice and ADR |
| Tushar Singh | Patient portal, bilingual companion, adherence, voice | Scheduling |
| Jeevan Kurian | Clinician portal, review queues, messaging, continuity | FHIR workflow UX |

The allocation is the execution starting point for the August–December plan. Update
the table and `.agent/TASKS.md` whenever responsibility changes.

## Operating cadence

- Maintain one integrated vertical increment each week.
- Use GitHub pull requests for all code review; one peer approval is required.
- Require the safety owner and clinical reviewer for safety-sensitive behavior.
- Keep a clinician/pharmacist review schedule for recommendation and escalation work.
- Record status, acceptance evidence, and owner in `.agent/TASKS.md`.

## Definition of done

A task is done only when its behavior and tests are complete, its documentation and
task tracker are current, a peer review is recorded, it is merged to `main`, CI is
green, and the required manual verification has been performed. Safety-sensitive work
also requires the assigned safety and clinical review.

## Branch and review workflow

`main` is the protected, deployable branch. Start a short-lived, product-focused
branch from current `main`; open one focused pull request; obtain review; merge; and
delete the merged branch. There is no `develop` integration branch.

Before requesting review:

1. Read the relevant product, architecture, task, and coding-standard documents.
2. Inspect adjacent code and state the acceptance criteria.
3. Run the required lint, type, test, build, and manual checks for the changed surface.
4. Confirm no secret, credential, undocumented placeholder, or unsupported clinical
   claim was introduced.
5. Include validation evidence and any follow-up work in the pull request.

## Decision-making

Small implementation choices can be documented in the pull request. Medium API or
library choices require team discussion and an architecture update. Product, safety,
or interoperability changes require team consensus and an entry in the project
decision history.
