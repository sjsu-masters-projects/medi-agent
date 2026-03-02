---
description: How to review AI-generated code before committing
---

# AI Code Review Workflow

## When to Use

Every time an AI coding assistant (Cursor, Copilot, Antigravity, etc.) generates code for you.

## Steps

1. **Before AI generates code, set context**
   - Point the AI to `.agent/PROJECT.md` and `.agent/CODING_STANDARDS.md`
   - Describe the specific task clearly
   - Reference existing code patterns the AI should follow

2. **After AI generates code, run this checklist**

   ### Correctness
   - [ ] Does the code actually solve the task?
   - [ ] Are all imports real packages or local files? (No hallucinated dependencies)
   - [ ] Do API endpoints match the patterns in ARCHITECTURE.md?
   - [ ] Do database queries use the correct table/column names?

   ### SOLID Compliance
   - [ ] **Single Responsibility:** Each file/class does one thing?
   - [ ] **Open/Closed:** New behavior via extension, not modification?
   - [ ] **Liskov:** Subclasses are interchangeable with parents?
   - [ ] **Interface Segregation:** No unused methods forced?
   - [ ] **Dependency Inversion:** Dependencies injected, not hardcoded?

   ### Code Quality
   - [ ] Naming matches conventions (see CODING_STANDARDS.md naming table)
   - [ ] Functions < 30 lines
   - [ ] Max 3 parameters per function
   - [ ] Comments explain WHY, not WHAT
   - [ ] Error handling: specific exceptions, meaningful messages
   - [ ] No hardcoded strings (URLs, API keys, config values)

   ### Patterns
   - [ ] Matches existing codebase patterns (compare with similar files)
   - [ ] No duplicate code (search for existing utilities first)
   - [ ] No over-abstraction (does this NEED an abstract class?)
   - [ ] Consistent with the project's file organization

   ### Security
   - [ ] No secrets in code
   - [ ] Auth checks on protected routes
   - [ ] Input validation on all user inputs
   - [ ] Proper RLS consideration for database queries

   ### Tests
   - [ ] Unit tests for business logic
   - [ ] Tests follow existing test patterns
   - [ ] Edge cases covered

3. **Fix any issues found**
   - Ask AI to fix specific problems (reference the checklist item)
   - Or fix manually if faster

4. **Run locally**
   ```bash
   # Backend
   cd backend && pytest
   
   # Frontend
   cd apps/patient-portal && npm run lint && npm test
   ```

5. **Commit only after all checks pass**
