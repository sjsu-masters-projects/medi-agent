#!/usr/bin/env bash
# ============================================================
# Preflight check — run this when you first clone the repo
# or after pulling new changes. Catches common setup issues
# before you waste time debugging.
#
# Usage: ./scripts/preflight.sh
# ============================================================

set -euo pipefail

# Ensure we run from project root
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "🚀  MediAgent Preflight Check"
echo "=============================="
echo ""

ERRORS=0

# ── 1. Check tools ──────────────────────────────────

echo "1️⃣  Checking required tools..."

check_tool() {
  if command -v "$1" &>/dev/null; then
    echo "  ✅  $1 — $(command $1 --version 2>&1 | head -1)"
  else
    echo "  ❌  $1 — not installed"
    ERRORS=$((ERRORS + 1))
  fi
}

check_tool python3
check_tool node
check_tool npm
check_tool psql
echo ""

# ── 2. Check .env ───────────────────────────────────

echo "2️⃣  Checking environment variables..."
if [ -f ".env" ]; then
  # Delegate to the env checker
  bash scripts/check-env.sh || ERRORS=$((ERRORS + 1))
else
  echo "  ❌  .env not found — run:  cp .env.example .env"
  ERRORS=$((ERRORS + 1))
fi
echo ""

# ── 3. Check backend deps ──────────────────────────

echo "3️⃣  Checking backend virtual environment..."
if [ -d "backend/.venv" ]; then
  echo "  ✅  backend/.venv exists"
else
  echo "  ⚠️   No venv found. Run:"
  echo "      cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt"
fi
echo ""

# ── 4. Check frontend deps ─────────────────────────

echo "4️⃣  Checking frontend node_modules..."
for portal in apps/patient-portal apps/clinician-portal; do
  if [ -d "$portal/node_modules" ]; then
    echo "  ✅  $portal/node_modules"
  else
    echo "  ⚠️   $portal — run:  cd $portal && npm install"
  fi
done
echo ""

# ── 5. Check DB connection ─────────────────────────

echo "5️⃣  Checking Supabase connection..."
DB_URL=$(grep "^SUPABASE_URL=" .env 2>/dev/null | cut -d'=' -f2- || echo "")
if [ -n "$DB_URL" ]; then
  echo "  ✅  SUPABASE_URL is set"
  echo "  ℹ️   To verify DB schema, run migrations — see docs/supabase_setup_guide.md"
else
  echo "  ⚠️   SUPABASE_URL not set in .env"
fi
echo ""

# ── Result ──────────────────────────────────────────

if [ $ERRORS -gt 0 ]; then
  echo "💥  $ERRORS issue(s) found. Fix them and re-run this script."
  exit 1
else
  echo "✅  All checks passed! Start developing:"
  echo ""
  echo "   Backend:          cd backend && source .venv/bin/activate && PYTHONPATH=src uvicorn app.main:app --reload"
  echo "   Patient Portal:   cd apps/patient-portal && npm run dev"
  echo "   Clinician Portal: cd apps/clinician-portal && npm run dev -- --port 3001"
  echo "   All at once:      docker compose up"
fi
