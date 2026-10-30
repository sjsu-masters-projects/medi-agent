# SEC-004 — Restore the blocking backend dependency audit

October 29, 2026, PR #230 follow-up on `fix/patient-records-clarity`.

## Scope and acceptance

The dependency audit fails before backend lint, type, migration and test jobs can
run. Its October 29 log reports 24 advisories across authlib, dnspython, filelock,
litellm, pypdf and setuptools. Raise the affected security floors and regenerate
both universal Python 3.12 lockfiles with the CI-pinned uv 0.9.24. Preserve other
locked versions where compatible. Do not disable audit enforcement or add a new
advisory exception. The separately documented SEC-003 OpenTelemetry exception and
its reachability guards remain unless its fixed release becomes compatible.

Acceptance: a second compile with the exact CI commands leaves both locks unchanged;
the pinned pip-audit 2.10.1 command passes with only the existing SEC-003 exception;
the installed lock remains compatible with full backend tests, Ruff and mypy; the
updated PR runs backend jobs instead of skipping them. Include the PR's 30 new
Records PostgreSQL contracts in the existing matrix with its zero-skip/minimum-count
gate; they were locally tested but absent from the explicit CI file list. Diagnose any further failing
PR job from its own log. No remote database, deployment or merge is authorized.
Preserve and exclude unrelated local script/configuration changes.

## Primary references

The failing CI audit is the version-specific acceptance source:
[job log](https://github.com/sjsu-masters-projects/medi-agent/actions/runs/40966039459/job/123770678164).
Maintainer advisories include
[Authlib](https://github.com/authlib/authlib/security/advisories/GHSA-8m4g-j4wp-wgcg),
[filelock](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8),
[pypdf](https://github.com/py-pdf/pypdf/security/advisories/GHSA-6c7f-9265-g8fw),
and [setuptools](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w).

## Resolved dependency set

Both locks change only these versions: authlib 1.9.1, dnspython 2.9.1,
filelock 4.2.4, litellm 1.101.3, pypdf 6.21.2 and setuptools 84.2.1. The provider
library stays on the existing 1.101 release line and other locked versions remain
unchanged. Security floors in `requirements.in` retain the patched minimums.
CI's compile commands reproduce both files byte-for-byte; pip-audit 2.10.1 reports
no known vulnerabilities after the sole existing SEC-003 ignore. That exception's
guards remain active. The new patient-records matrix shard requires all 24 removal
and six cache PostgreSQL cases to execute successfully, with no skips.

This is dependency maintenance, not production or clinical certification. Final
backend compatibility results and the updated PR run are recorded in the task board
and dated evidence once verification completes.

## October 30 follow-up — PR #232

The fresh audit reports CVE-2026-119284 in transitive `joserfc` 1.7.5 and requires
1.7.6. Add that floor, regenerate both locks with the pinned resolver, verify that
only this version changes, repeat the compile unchanged, and run the unchanged
blocking audit with only the existing SEC-003 exception. Validate the full backend
suite under the updated lock and verify remote CI; no audit bypass or remote
deployment is authorized. [Failing job](https://github.com/sjsu-masters-projects/medi-agent/actions/runs/41115572887/job/124268798884).
