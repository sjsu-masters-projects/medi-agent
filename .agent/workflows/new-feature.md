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

5. **Self-review checklist**
   ```markdown
   - [ ] Follows SOLID principles
   - [ ] No hallucinated imports
   - [ ] No dead code
   - [ ] Matches existing patterns
   - [ ] Types are correct
   - [ ] Error handling is proper
   - [ ] Tests pass
   ```

6. **Create Pull Request**
   ```bash
   git add .
   git commit -m "feat({scope}): {description}"
   git push origin feature/{feature-id}-{short-description}
   ```
   - PR title: conventional commit format
   - PR description: what changed, why, how to test, screenshots

7. **Request review from a team member**

8. **After merge, mark task as done (`[x]`) in TASKS.md**
