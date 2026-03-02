# MediAgent — Team & Process

> How we work together. How we work with AI. How we ship quality.

---

## Team Structure

| Role | Who | Primary Domain | Backup Domain |
|------|-----|---------------|---------------|
| **Member 1** | TBD | Backend + Agents | Patient Portal |
| **Member 2** | TBD | Backend + Agents | Clinician Portal |
| **Member 3** | TBD | Patient Portal | Backend |
| **Member 4** | TBD | Clinician Portal | Backend |

> **No single point of failure.** Everyone must understand all domains. Backup domain ensures continuity.

---

## AI Coding Assistant Usage Guidelines

### Context Setup

**Before starting ANY coding session, every AI assistant should read these files:**

1. `.agent/PROJECT.md` — What we're building, key decisions
2. `.agent/CODING_STANDARDS.md` — How to write code
3. `.agent/ARCHITECTURE.md` — System structure
4. Relevant feature tasks in `.agent/TASKS.md`

### Workflow: AI-Assisted Code Generation

```
┌──────────────────────────────────────────────────────┐
│ 1. UNDERSTAND                                         │
│    Developer reads the task from TASKS.md              │
│    Developer reviews relevant existing code            │
│    Developer briefs the AI assistant with context      │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ 2. GENERATE                                           │
│    AI writes the code following CODING_STANDARDS.md   │
│    Developer reviews AI output in real-time            │
│    Developer corrects direction if AI drifts           │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ 3. REVIEW (Self)                                      │
│    Read every line the AI generated                    │
│    Check: Does it follow SOLID?                        │
│    Check: Are there unnecessary files/abstractions?    │
│    Check: Are imports and dependencies correct?        │
│    Check: Does it match existing patterns in codebase? │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ 4. TEST                                               │
│    Run locally — does it work?                         │
│    Run existing tests — nothing broken?                │
│    Write new tests for new functionality               │
└──────────────┬───────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────┐
│ 5. PR & PEER REVIEW                                   │
│    Create PR with conventional commit title            │
│    Another team member reviews                         │
│    Fix feedback → merge                                │
└──────────────────────────────────────────────────────┘
```

### AI Review Checklist (for every AI-generated PR)

```markdown
## AI Code Review Checklist

- [ ] **Context:** AI had correct project context (read .agent/ docs)
- [ ] **SOLID:** Single responsibility per file/class/function
- [ ] **No hallucinated imports:** All imports are real packages or local files
- [ ] **No dead code:** No unused functions, variables, or files
- [ ] **No over-abstraction:** AI didn't create unnecessary layers
- [ ] **Matches patterns:** Follows existing codebase conventions
- [ ] **Types:** Proper type hints (Python) / TypeScript types
- [ ] **Error handling:** Specific exceptions, meaningful messages
- [ ] **Tests included:** Unit tests for business logic
- [ ] **Security:** No hardcoded secrets, proper auth checks
- [ ] **Env vars:** No hardcoded URLs or config values
```

### Common AI Pitfalls to Watch For

| Pitfall | What Happens | How to Catch |
|---------|-------------|-------------|
| **Hallucinated packages** | AI imports a package that doesn't exist | `pip install` or `npm install` fails |
| **Over-engineering** | AI creates 5 abstraction layers for a simple function | Count the files — if > 3 for one feature, simplify |
| **Inconsistent patterns** | AI uses a different style than existing code | Compare with existing similar files |
| **Missing error handling** | AI writes happy path only | Ask: "What happens if X fails?" |
| **Stale context** | AI uses deprecated API or old project structure | Always point AI to latest code |
| **Duplicate code** | AI rewrites something that already exists | grep/search before accepting new utilities |

---

## Development Process

### Sprint Cadence

| Item | Cadence | Format |
|------|---------|--------|
| **Sprint** | 2 weeks | Aligned with roadmap phases |
| **Standup** | Async daily | Post in team chat: Yesterday / Today / Blockers |
| **Sprint Planning** | Every 2 weeks | Pick tasks from TASKS.md, assign owners |
| **Demo** | Every 2 weeks | Show working features to team |
| **Retro** | Every 4 weeks | What worked, what didn't, what to change |

### Task Lifecycle

```
BACKLOG → IN PROGRESS → IN REVIEW → DONE
  [ ]        [/]           [/]       [x]
```

### Definition of Done

A task is "done" when:
1. ✅ Code is written and follows CODING_STANDARDS.md
2. ✅ Tests pass (unit + integration where applicable)
3. ✅ PR is reviewed and approved by 1 team member
4. ✅ Merged to main branch
5. ✅ Deployed to staging (auto via CI/CD)
6. ✅ Manually verified on staging
7. ✅ Task marked `[x]` in TASKS.md

---

## Git Branching Strategy

```
main (production)
  │
  ├── develop (integration)
  │     │
  │     ├── feature/fp2-document-upload (feature branches)
  │     ├── feature/fc7-medwatch-queue
  │     └── bugfix/123-adherence-fix
  │
  └── release/v1.0 (cut from develop before expo)
```

- **main:** Always deployable. Protected branch.
- **develop:** Integration branch. All features merge here first.
- **feature/*:** One branch per task. Short-lived (< 1 week).
- **release/*:** Created before expo for final stabilization.

---

## Communication

| Channel | Purpose |
|---------|---------|
| **GitHub PRs** | All code discussion |
| **Team Chat** | Daily standups, quick questions |
| **TASKS.md** | Source of truth for task status |
| **PROJECT.md Decision Log** | All architectural decisions with rationale |

### Decision-Making

1. **Small decisions** (naming, minor refactors): Decide yourself, mention in PR.
2. **Medium decisions** (library choice, API design): Discuss in team chat, document in PR.
3. **Large decisions** (architecture change, new technology): Add to PROJECT.md Decision Log, get team consensus.
