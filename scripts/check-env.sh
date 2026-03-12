#!/usr/bin/env bash
# ============================================================
# Checks that your .env file has all the required variables
# defined in .env.example. Run this before starting dev servers.
#
# Usage: ./scripts/check-env.sh
# ============================================================

set -euo pipefail

# Find project root so script works regardless of where it's called from
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ENV_FILE="$ROOT_DIR/.env"
EXAMPLE_FILE="$ROOT_DIR/.env.example"
ERRORS=0

if [ ! -f "$ENV_FILE" ]; then
  echo "❌  .env file not found!"
  echo ""
  echo "   Run:  cp .env.example .env"
  echo "   Then fill in your values (see .env.example for details)."
  exit 1
fi

echo "🔍  Checking .env against .env.example..."
echo ""

# Required vars (must have a non-empty value)
REQUIRED_VARS=(
  "SUPABASE_URL"
  "SUPABASE_ANON_KEY"
  "SUPABASE_SERVICE_ROLE_KEY"
  "SUPABASE_JWT_SECRET"
  "GOOGLE_API_KEY"
)

# Optional vars (should exist in .env but can be empty)
OPTIONAL_VARS=(
  "GOOGLE_PROJECT_ID"
  "DEEPGRAM_API_KEY"
  "RESEND_API_KEY"
  "SYNCFUSION_LICENSE_KEY"
  "MEDGEMMA_MODEL_ID"
  "BACKEND_URL"
  "PATIENT_PORTAL_URL"
  "CLINICIAN_PORTAL_URL"
  "ENVIRONMENT"
  "LOG_LEVEL"
)

# Check required vars
for var in "${REQUIRED_VARS[@]}"; do
  value=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | xargs 2>/dev/null || echo "")
  if [ -z "$value" ]; then
    echo "  ❌  $var  — required but missing or empty"
    ERRORS=$((ERRORS + 1))
  else
    echo "  ✅  $var"
  fi
done

echo ""

# Check optional vars (warn if missing)
for var in "${OPTIONAL_VARS[@]}"; do
  if grep -q "^${var}=" "$ENV_FILE" 2>/dev/null; then
    echo "  ✅  $var"
  else
    echo "  ⚠️   $var  — not in .env (optional)"
  fi
done

echo ""

# Check for vars in .env.example that we haven't covered
EXAMPLE_VARS=$(grep -E "^[A-Z_]+=.*" "$EXAMPLE_FILE" | cut -d'=' -f1 | sort)
ENV_VARS=$(grep -E "^[A-Z_]+=.*" "$ENV_FILE" | cut -d'=' -f1 | sort)

NEW_IN_EXAMPLE=$(comm -23 <(echo "$EXAMPLE_VARS") <(echo "$ENV_VARS") 2>/dev/null || true)
if [ -n "$NEW_IN_EXAMPLE" ]; then
  echo "🆕  New vars in .env.example that you're missing:"
  echo "$NEW_IN_EXAMPLE" | while read -r var; do
    echo "    → $var"
  done
  echo ""
fi

if [ $ERRORS -gt 0 ]; then
  echo "💥  $ERRORS required variable(s) missing. Fix your .env file."
  exit 1
else
  echo "✅  All required variables set. You're good to go!"
fi
