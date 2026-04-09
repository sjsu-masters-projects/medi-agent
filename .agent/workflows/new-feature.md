---
description: How to start a new feature development workflow
---

# New Feature Development

// turbo-all

## Steps

1. **Pick a task from `.agent/TASKS.md`**
   - Choose an unstarted task (`[ ]`)
   - Mark it as in-progress (`[/]`)
   - Note the feature ID (e.g., F-P2, F-C7)

2. **Create a feature branch**
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/{feature-id}-{short-description}
   ```

3. **Read context before coding**
   - Read `.agent/PROJECT.md` for product context
   - Read `.agent/ARCHITECTURE.md` for system design
   - Read `.agent/CODING_STANDARDS.md` for code rules
   - Read `.agent/DESIGN_SYSTEM.md` for UI and styling (if frontend)
   - Read existing related code in the codebase

4. **Implement the feature**
   - Follow file organization from CODING_STANDARDS.md
   - Follow SOLID principles
   - Write tests alongside code
   - **Database**: add a migration in `backend/src/app/db/migrations/` (e.g. `009_*.sql`) — run manually in Supabase SQL Editor
   - **Backend new service**: place in `backend/src/app/services/`, add to `__init__.py`
   - **Backend new agent**: follow `agents/summarization/` pattern (agent.py, graph.py, prompts.py)
   - **Frontend API**: add typed functions in `apps/clinician-portal/src/services/`
   - **Frontend state**: add Redux slice in `apps/clinician-portal/src/store/slices/`, register in `store.ts`
   - **Supabase Realtime**: if feature requires live updates, enable table in Supabase Dashboard → Database → Replication

5. **Self-review checklist**
   ```markdown
   - [ ] Follows SOLID principles
   - [ ] No hallucinated imports
   - [ ] No dead code
   - [ ] Matches existing patterns
   - [ ] Types are correct (run `tsc --noEmit`)
   - [ ] Error handling is proper
   - [ ] Backend tests pass (pytest --noconftest for unit tests)
   - [ ] Frontend tests pass (vitest run)
   - [ ] DB migration tested in Supabase SQL Editor
   ```

6. **Run tests before committing**
   ```bash
   # Backend unit tests (no live DB needed)
   cd backend && PYTHONPATH=src SUPABASE_URL=http://localhost \
     SUPABASE_ANON_KEY=test SUPABASE_SERVICE_ROLE_KEY=test \
     SUPABASE_JWT_SECRET=test \
     python3 -m pytest tests/unit/ -v --no-cov --noconftest --override-ini="addopts="

   # Frontend tests
   cd apps/clinician-portal && ./node_modules/.bin/vitest run

   # TypeScript check
   cd apps/clinician-portal && ./node_modules/.bin/tsc --noEmit
   ```

7. **Create Pull Request**
   ```bash
   git add .
   git commit -m "feat({scope}): {description}"
   git push origin feature/{feature-id}-{short-description}
   ```
   - PR title: conventional commit format
   - PR description: what changed, why, how to test, screenshots
   - Include migration file path if DB changes were made

8. **Request review from a team member**

9. **After merge, mark task as done (`[x]`) in TASKS.md**
