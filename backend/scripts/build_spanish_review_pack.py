"""Build a source-linked review inventory without executing portal or backend copy.

Writes Markdown to stdout. Redirects are unnecessary: maintainers can use --check
for a freshness assertion; repository edits are made through normal patch review.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "docs/spanish-draft-review-pack.md"
TS_FILES = (
    "apps/patient-portal/src/content/chat-copy.ts",
    "apps/patient-portal/src/content/care-team-copy.ts",
    "apps/patient-portal/src/content/symptom-history-copy.ts",
    "apps/patient-portal/src/content/visits-copy.ts",
    "apps/patient-portal/src/app/(app)/profile/profile-copy.ts",
    "apps/patient-portal/src/components/features/nora-conversations.tsx",
    "packages/shared/src/utils/care-conversations.ts",
)
PY_FILES = (
    "backend/src/app/services/notification_centre_presentation.py",
    "backend/src/app/services/symptom_report_presenter.py",
    "backend/src/app/services/appointment_calendar.py",
    "backend/src/app/services/email_service.py",
)


def python_rows(file: str) -> list[dict[str, str | int]]:
    tree = ast.parse((ROOT / file).read_text())
    rows: list[dict[str, str | int]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        name = ast.unparse(node.targets[0] if isinstance(node, ast.Assign) else node.target)
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("en-US"), dict) and isinstance(value.get("es-MX"), dict):
            for key, spanish in value["es-MX"].items():
                rows.append(
                    dict(
                        file=file,
                        line=node.lineno,
                        key=f"{name}.{key}",
                        en=str(value["en-US"][key]),
                        es=str(spanish),
                    )
                )
        elif isinstance(value.get("en-US"), tuple) and isinstance(value.get("es-MX"), tuple):
            for index, spanish in enumerate(value["es-MX"]):
                rows.append(
                    dict(
                        file=file,
                        line=node.lineno,
                        key=f"{name}.{index}",
                        en=str(value["en-US"][index]),
                        es=str(spanish),
                    )
                )
        else:
            for key, entry in value.items():
                if (
                    isinstance(entry, tuple)
                    and len(entry) in {2, 4}
                    and all(isinstance(item, str) for item in entry)
                ):
                    for index in range(len(entry) // 2):
                        rows.append(
                            dict(
                                file=file,
                                line=node.lineno,
                                key=f"{name}.{key}.{index}",
                                en=entry[index],
                                es=entry[index + len(entry) // 2],
                            )
                        )
    return rows


def cell(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
    )


def build() -> str:
    result = subprocess.run(
        ["node", "scripts/extract-spanish-review.mjs", *TS_FILES],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    rows = json.loads(result.stdout)
    for file in PY_FILES:
        rows.extend(python_rows(file))
    header = [
        "# English / Mexican Spanish draft review pack",
        "",
        "Status: pending meaning-and-safety review. This inventory is not approval.",
        "",
        "This pack collects the source files named by LOC-001 draft markers and linked",
        "requirements, including recovery, voice, care-team ownership/privacy, symptoms,",
        "visits/cancellation, translation caveats, Profile and calendar labels. Entire",
        "bilingual dictionaries are included conservatively where a marker covers only",
        "part of a file. Inclusion does not revoke earlier accepted wording.",
        "",
        "Dynamic rows show the exact source expression, including singular/plural and",
        "conditional branches. Review both branches and preserve placeholders, names,",
        "numbers, units, dates and safety/approval boundaries. They are not executable",
        "instructions in this document. No patient-authored text or clinical record is included.",
        "",
        "## Review method",
        "",
        "1. Compare meaning, not word order: uncertainty, negation, timing and who may act.",
        "2. Check no diagnosis, approval, delivery or continuous-monitoring claim is added.",
        "3. Retain text fallback, confirmation before sharing, and emergency wording.",
        "4. Record each decision by file/key with accepted text or a proposed correction.",
        "5. Edit source copy and regenerate the pack after corrections; do not approve by",
        "   deleting a draft comment alone. Clinical plan text still uses in-app bilingual approval.",
        "",
        "A documented demo meaning-and-safety review is sufficient for this project;",
        "a separate fluent reviewer is not required. This pack itself makes no completed",
        "review or professional translation/clinical-validation claim.",
        "",
        "## Source snapshot",
        "",
        "Regenerate with `python backend/scripts/build_spanish_review_pack.py`;",
        "check freshness with `python backend/scripts/build_spanish_review_pack.py --check`.",
        "Install the clinician portal's locked dependencies first for the TypeScript parser.",
        "",
        "| Source | SHA-256 |",
        "| --- | --- |",
    ]
    for file in (*TS_FILES, *PY_FILES):
        digest = hashlib.sha256((ROOT / file).read_bytes()).hexdigest()
        header.append(
            f"| [{file}](../{file.replace('(', '%28').replace(')', '%29')}) | `{digest}` |"
        )
    header.extend(
        [
            "",
            f"## Review list ({len(rows)} paired rows)",
            "",
            "Every row is pending review in this pack. Use the source key to identify duplicates",
            "across screens; do not infer that similar strings have the same clinical context.",
            "",
            "| Source/key | English (US) | Español (México), draft |",
            "| --- | --- | --- |",
        ]
    )
    for row in rows:
        file = str(row["file"])
        header.append(
            f"| {cell(file)}:{row['line']} / `{row['key']}` | {cell(row['en'])} | {cell(row['es'])} |"
        )
    header.extend(
        [
            "",
            "## Scope outside static interface copy",
            "",
            "Stored care-plan wording, historical human messages, question-library content and",
            "generated clinical translations require their own source-linked review. They are",
            "not replaced by this interface pack. Existing clinical safety copy is unchanged.",
            "The linked [LOC-001 contract](../.agent/specs/loc-001-bilingual-approved-wording.md)",
            "owns approval semantics; [the task board](../.agent/TASKS.md) owns current status.",
            "",
        ]
    )
    return "\n".join(header)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = build()
    if args.check:
        if not DESTINATION.exists() or DESTINATION.read_text() != text:
            print("Spanish review pack is stale; regenerate and review its diff.")
            return 1
        print("Spanish review pack matches its source snapshot.")
        return 0
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
