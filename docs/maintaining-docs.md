# Maintaining documentation

The README explains the product and gets a contributor to a running checkout.
The documentation index routes deeper questions. Requirements, operating commands
and test evidence each have one maintained home.

## Where content belongs

| Reader's question | Document type | Location |
| --- | --- | --- |
| How do I start locally? | Setup guide | README and `docs/development.md` |
| How do I perform a specific operation? | Task guide | Existing operating guide under `docs/` |
| What are the fields, contracts and limits? | Reference | App/backend READMEs |
| What does a feature do, and what must it keep doing? | Feature doc | `docs/features/` |
| Why does the system work this way? | Explanation | `.agent/ARCHITECTURE.md` and the feature doc |
| What remains to be delivered? | Task board | `.agent/TASKS.md` |
| What was actually verified? | Evidence | `docs/evidence/` |

This structure follows [Diátaxis](https://diataxis.fr/start-here/). Do not create
empty folders just to mirror a framework. Keep established operating-guide paths
stable when scripts or contributor instructions depend on them.

## Writing rules

- Lead with the outcome and the intended reader. Use direct language and descriptive headings.
- Use ordinary punctuation, not em dashes. Avoid promotional claims, authoring credits
  and descriptions of the tools used to write the document.
- Describe implemented behavior accurately. Product safety disclosures and factual
  service dependencies must not be removed to make the description sound stronger.
- Keep commands copyable. State their working directory, prerequisites, side effects
  and permission boundary. Do not include credentials or production data.
- Link to configuration templates instead of duplicating variable defaults.
- Link to status and evidence rather than copying volatile task lists into guides.
- Keep guides as procedures. Test counts, "applied on" notes, PR progress and session
  checkpoints go in `docs/evidence/`; the guide links to them.

## Diagrams

Use a diagram only when it clarifies a relationship or sequence. Keep labels short,
use supported Mermaid flowchart syntax and provide a prose explanation beside it.
Include `accTitle` and `accDescr`. Use dark text on light fills with visible borders;
colour is an aid, never the only way to distinguish a review or failure path.

The README uses emerald for patient care, blue for services and source inputs,
amber for human review, and violet for storage. Node labels still identify each role.
Follow [GitHub's diagram guidance](https://docs.github.com/en/contributing/writing-for-github-docs/creating-diagrams-for-github-docs)
and [Mermaid accessibility guidance](https://mermaid.js.org/config/accessibility.html).

## Retire or move a document

Keep repeatable operating procedures, unresolved decisions and evidence needed to judge
acceptance.

A specification is temporary. Write one under `.agent/specs/` only for work being built. When
the feature ships, move what code cannot explain into its doc under `docs/features/`: the rules
it must keep, why they exist, the options rejected and what was ruled out. Anything unbuilt goes
under that doc's "Still open". Then delete the specification. The same applies to a decision
record once its choice is settled.

A feature doc describes current behavior only, with no status, PR numbers, test counts or dated
progress. Update it in the same change that alters the behavior. If a doc and the code disagree
on a safety rule, treat that as a bug to raise, not a wording fix.

Before removal, move unique, still-useful information into its maintained source.
Then remove the redundant document and repair inbound links. Git preserves the old
version. Do not introduce an unindexed archive or a parallel task tracker.

Historical reports belong under `docs/evidence/`, labelled by date and scope. Preserve
their outcomes and limitations. An old local result must not become a current live pass.

## Review checklist

From the repository root:

```bash
node --test scripts/tests/check-docs.test.mjs
node scripts/check-docs.mjs --all
```

The link checker validates tracked Markdown links, heading anchors, image paths and
code-fence balance. It does not fetch external URLs, run setup commands or prove
Mermaid rendering. Parse and inspect changed diagrams separately.

1. Confirm every local file link and heading anchor resolves, including inbound links
   from feature docs and app READMEs.
2. Parse and render changed Mermaid blocks. Inspect wrapping, contrast and arrows.
3. Verify setup commands against scripts, manifests and configuration loading code.
4. Search edited guides for em dashes, credentials, unsupported claims and stale status.
5. Update the documentation index and task board. Record exact checks in the PR.
6. Run the existing checks for any deployment or application files included in the PR.
