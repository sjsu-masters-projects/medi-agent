---
description: How to implement a feature and automatically create a pull request
---

# Create Pull Request Workflow

## When to Use
Use this workflow whenever the user asks you to implement a task and appends `/create-pr`.
This signals that you should NOT push directly to the main branch, as branch protection rules forbid it.

## Steps

1. **Create and switch to a feature branch**
   Read the user's task description and generate a short, descriptive branch name (e.g., `feat/add-patient-dashboard` or `fix/auth-token-refresh`).
   ```bash
   git checkout main
   git pull origin main
   git checkout -b <branch-name>
   ```

2. **Implement the feature**
   Follow standard development protocols (read `PROJECT.md`, `ARCHITECTURE.md`, `CODING_STANDARDS.md`).
   Write logic, tests, and make sure to run local verification:
   ```bash
   # Backend
   cd backend && ruff check src/ && pytest tests/
   # Frontend
   cd apps/patient-portal && npm run lint && npm run build
   ```

3. **Commit the changes**
   Use Conventional Commits format (`feat: ...`, `fix: ...`, `docs: ...`).
   ```bash
   git add <files>
   git commit -m "feat(scope): descriptive message"
   ```

4. **Push the feature branch to GitHub**
   ```bash
   git push origin <branch-name>
   ```

5. **Create the Pull Request using the `gh` CLI**
   Use the `run_command` tool to execute `gh pr create` with the populated template fields.
   ```bash
   gh pr create \
     --title "feat(scope): descriptive title matching your commit" \
     --body "- Context: implemented the requested feature
   - What changed: added X, modified Y
   - Resolves: [task reference]
   
   - [x] I have read the CODING_STANDARDS
   - [x] My code matches existing architecture
   - [x] I have verified tests pass
   - [x] I have run local linting
   - [x] I have added/updated tests
   - [x] There are no new warnings or secrets"
   ```

6. **Notify the User**
   Inform the user that the PR has been created via `notify_user` and provide the URL returned by the `gh` command.
