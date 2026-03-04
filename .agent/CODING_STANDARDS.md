# MediAgent — Coding Standards

> Every team member and AI coding assistant MUST follow these standards. No exceptions.

---

## SOLID Principles

We follow SOLID strictly. Here's what it means in our codebase:

### S — Single Responsibility

**Every file, class, and function does ONE thing.**

```python
# ✅ Good — each service has one job
class DocumentService:
    """Handles document CRUD operations only."""

class DocumentParser:
    """Handles AI parsing of documents only."""

# ❌ Bad — mixed responsibilities
class DocumentManager:
    def upload(self): ...
    def parse_with_ai(self): ...
    def send_notification(self): ...
    def update_dashboard(self): ...
```

### O — Open/Closed

**Open for extension, closed for modification.** Use base classes and interfaces.

```python
# ✅ Good — new agents extend base, don't modify it
class BaseAgent(ABC):
    @abstractmethod
    async def process(self, input: AgentInput) -> AgentOutput: ...

class IngestionAgent(BaseAgent):
    async def process(self, input: AgentInput) -> AgentOutput: ...

class TriageAgent(BaseAgent):
    async def process(self, input: AgentInput) -> AgentOutput: ...
```

### L — Liskov Substitution

**Subclasses must be usable wherever their parent is expected.**

```python
# Any agent must work when passed to the orchestrator
async def run_agent(agent: BaseAgent, input: AgentInput):
    return await agent.process(input)  # Works with ANY agent
```

### I — Interface Segregation

**Don't force classes to implement methods they don't use.**

```python
# ✅ Good — separate interfaces
class Parseable(Protocol):
    async def parse(self, content: bytes) -> dict: ...

class Explainable(Protocol):
    async def explain(self, data: dict, language: str) -> str: ...

# ❌ Bad — fat interface
class DocumentHandler(ABC):
    @abstractmethod
    async def parse(self): ...
    @abstractmethod
    async def explain(self): ...
    @abstractmethod
    async def redact(self): ...  # Not all handlers redact!
```

### D — Dependency Inversion

**Depend on abstractions, not concretions. Use dependency injection.**

```python
# ✅ Good — depends on abstract LLMClient
class IngestionAgent:
    def __init__(self, llm: LLMClient, db: DatabaseClient):
        self.llm = llm
        self.db = db

# ❌ Bad — hardcoded dependency
class IngestionAgent:
    def __init__(self):
        self.llm = GeminiClient()  # Can't swap out for testing
```

---

## Clean Code Rules

### Naming

| What | Convention | Example |
|------|-----------|---------|
| Python files | `snake_case.py` | `document_service.py` |
| Python classes | `PascalCase` | `DocumentService` |
| Python functions | `snake_case` | `parse_document()` |
| Python constants | `UPPER_SNAKE` | `MAX_FILE_SIZE_MB` |
| TypeScript files | `kebab-case.tsx` | `risk-radar.tsx` |
| React components | `PascalCase` | `RiskRadar` |
| TS functions | `camelCase` | `fetchPatientData()` |
| API routes | `kebab-case` | `/api/v1/care-teams` |
| DB tables | `snake_case` (plural) | `symptom_reports` |
| DB columns | `snake_case` | `created_at` |
| Env vars | `UPPER_SNAKE` | `SUPABASE_URL` |

### Functions

1. **Max 30 lines.** If longer, extract helper functions.
2. **Max 3 parameters.** Use a config/options object for more.
3. **One level of abstraction.** Don't mix high-level logic with low-level details.
4. **Verbs for functions:** `parse_document()`, `calculate_naranjo_score()`, `send_notification()`
5. **Nouns for classes:** `DocumentParser`, `NaranjoCalculator`, `NotificationService`

### Comments

```python
# ✅ Good — explains WHY, not WHAT
# Naranjo score ≥5 is "Probable" per the standard algorithm.
# We flag as HIGH priority to ensure clinician review.
if naranjo_score >= 5:
    priority = "HIGH"

# ❌ Bad — explains WHAT (the code already says this)
# Set priority to HIGH if score is 5 or more
if naranjo_score >= 5:
    priority = "HIGH"
```

### Error Handling

```python
# ✅ Good — specific exceptions, meaningful messages
class DocumentParseError(MediAgentError):
    """Raised when AI fails to extract structured data from a document."""

try:
    parsed = await parser.parse(document)
except DocumentParseError as e:
    logger.error(f"Failed to parse document {doc_id}: {e}")
    return ParseResult(status="error", message="Could not read this document")

# ❌ Bad — generic catch-all
try:
    parsed = await parser.parse(document)
except Exception:
    return None
```

---

## File Organization

### Backend (Python)

```
backend/app/
├── main.py              # App entry, middleware, startup
├── config.py            # Settings from env vars (pydantic-settings)
├── models/              # Pydantic models (request/response schemas)
│   ├── patient.py
│   ├── document.py
│   └── ...
├── routers/             # API route handlers (thin — delegates to services)
│   ├── patients.py
│   ├── documents.py
│   └── ...
├── services/            # Business logic (testable, no framework deps)
│   ├── document_service.py
│   ├── adherence_service.py
│   └── ...
├── agents/              # LangGraph agent definitions
│   ├── base.py          # BaseAgent abstract class
│   ├── ingestion.py
│   └── ...
├── tools/               # Tools agents call (DailyMed, RxNorm, etc.)
├── clients/             # External API clients (Gemini, Deepgram, etc.)
├── db/                  # Supabase queries, migrations, seeds
│   ├── queries/         # Raw SQL or Supabase client calls
│   ├── migrations/
│   └── seed/
└── utils/               # Pure utility functions
```

### Frontend (TypeScript/React)

```
apps/{portal}/src/
├── app/                 # Next.js App Router pages
│   ├── (auth)/          # Auth-gated routes
│   ├── layout.tsx
│   └── page.tsx
├── components/          # Reusable UI components
│   ├── ui/              # Primitives (Button, Card, Input)
│   ├── features/        # Feature-specific (MedCard, RiskBadge)
│   └── layouts/         # Page layouts
├── store/               # Redux slices
│   ├── slices/
│   └── store.ts
├── services/            # API client functions
│   ├── api.ts           # Base fetch wrapper
│   ├── patients.ts
│   └── ...
├── hooks/               # Custom React hooks
├── types/               # TypeScript interfaces
├── utils/               # Pure utility functions
└── constants/           # App-wide constants
```

---

## Design System & UI

All frontend UI code must strictly adhere to our centralized design tokens and components based on the approved Figma screens.
**Before writing or reviewing any UI code (Tailwind, React components, CSS), you must read:**
👉 [`.agent/DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md)

Do not invent new colors, spacing, or abstractions that conflict with the Design System.

---

## Git Conventions

### Branch Naming

```
feature/{feature-id}-{short-description}
bugfix/{issue}-{short-description}
hotfix/{description}

Examples:
feature/fp2-document-upload
feature/fc7-medwatch-queue
bugfix/123-adherence-score-calculation
```

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(agents): add Naranjo scoring to pharmacovigilance agent
fix(patient-portal): correct medication time display in Today Feed
docs(architecture): update API endpoint documentation
refactor(services): extract document parsing into separate service
test(agents): add golden-set tests for ingestion agent
chore(ci): add Playwright E2E workflow
```

### Pull Request Rules

1. **Every PR requires at least 1 review** from another team member
2. **All CI checks must pass** (lint, test, build)
3. **PR title follows conventional commits** format
4. **PR description must include:**
   - What changed and why
   - How to test manually
   - Screenshots for UI changes
   - Link to task in TASKS.md

---

## Testing Standards

### Backend

| Type | Tool | Coverage Target | When |
|------|------|----------------|------|
| Unit | pytest | Services, agents, tools | Every PR |
| Integration | pytest + httpx | API endpoints with DB | Every PR |
| Agent Eval | Custom golden-set runner | Agent input/output accuracy | Weekly |

### Frontend

| Type | Tool | Coverage Target | When |
|------|------|----------------|------|
| Component | Vitest + Testing Library | UI components | Every PR |
| E2E | Playwright | Critical user flows | Pre-merge to main |

### Test File Naming

```
# Python
tests/test_document_service.py
tests/agents/test_ingestion_agent.py

# TypeScript
__tests__/risk-radar.test.tsx
e2e/patient-onboarding.spec.ts
```

---

## Linting & Formatting

| Tool | Scope | Config |
|------|-------|--------|
| **Ruff** | Python lint + format | `ruff.toml` |
| **mypy** | Python type checking | `mypy.ini` |
| **ESLint** | TypeScript lint | `.eslintrc.json` |
| **Prettier** | TS/CSS/JSON format | `.prettierrc` |
| **Husky** | Pre-commit hooks | Runs lint + format on staged files |

**Rule: If the linter complains, fix it. No `# noqa` or `eslint-disable` without a comment explaining why.**
