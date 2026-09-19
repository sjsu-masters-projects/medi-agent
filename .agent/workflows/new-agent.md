---
description: How to add a bounded product worker to the ADK runtime
---

# Adding a product worker

## Before creating one

1. Read `.agent/PROJECT.md`, `.agent/ARCHITECTURE.md`, and `.agent/TASKS.md`.
2. Confirm the work cannot be a deterministic service. Authentication, authorization,
   approval enforcement, scheduling, notifications, retries, and persistence stay deterministic.
3. Define the worker's authority, evidence contract, deterministic outcome, and clinician-review
   boundary. A worker may propose or explain; it cannot approve clinical action.
4. Obtain a reviewed task entry and peer/safety review where the behaviour is safety-sensitive.

## Implementation shape

New model-backed work belongs in `backend/src/app/adk/`.

1. Add the agent under `adk/agents/<name>/` with a focused `agent.py` and prompts.
2. Register every model-backed workload in `adk/registry.py`. It must specify a primary
   transport, a different fallback where one is safe, a deterministic result, a kill switch,
   an output ceiling, and a latency budget where a person is waiting.
3. Keep safety and tool restrictions in shared plugins. The emergency floor runs before model
   execution; tools are deny-by-default.
4. Validate all model output at the boundary. Persist source/model metadata for candidate facts,
   never private reasoning or raw patient prompts.
5. Keep routers thin and place deterministic business rules in services.

## Verification

- Unit-test the route selection, disabled path, fallback, malformed output, and deterministic
  result.
- Add integration coverage for authorization, evidence/provenance, and review behaviour.
- Add browser coverage when the worker changes a critical user journey.
- Update `.agent/ARCHITECTURE.md`, the active task, and the applicable decision record.

Do not start new work in `backend/src/app/agents/`; it exists only for legacy compatibility.
