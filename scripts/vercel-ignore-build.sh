#!/usr/bin/env bash
# Vercel "Ignored Build Step" for the portals: exit 0 skips the build, exit 1 builds.
#
# The free Vercel plan rate-limits deployments, and every pushed branch used to build both
# portals, including backend-only commits. Only main deploys now, and only when this
# portal or the shared package changed since the last deployment that went out.
#
# Usage (from a portal's vercel.json): bash ../../scripts/vercel-ignore-build.sh <app-dir-name>
set -uo pipefail

app="${1:?usage: vercel-ignore-build.sh <app-dir-name>}"
branch="${VERCEL_GIT_COMMIT_REF:-}"

if [ "$branch" != "main" ]; then
  echo "Skipping build: preview deployments are off (branch '${branch:-unknown}'). CI builds every portal on each PR."
  exit 0
fi

top="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Building: not a git checkout, so changes cannot be compared."
  exit 1
}
base="${VERCEL_GIT_PREVIOUS_SHA:-}"

# No earlier deployment, or a shallow clone that lacks it: build rather than risk skipping.
if [ -z "$base" ] || ! git cat-file -e "${base}^{commit}" 2>/dev/null; then
  echo "Building: no previous deployment commit to compare against."
  exit 1
fi

if git diff --quiet "$base" HEAD -- "$top/apps/$app" "$top/packages/shared" "$top/scripts/vercel-ignore-build.sh"; then
  echo "Skipping build: nothing in apps/$app or packages/shared changed since ${base:0:8}."
  exit 0
fi

echo "Building: apps/$app or packages/shared changed since ${base:0:8}."
exit 1
