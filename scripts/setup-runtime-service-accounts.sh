#!/usr/bin/env bash
# Create the least-privilege runtime service accounts for the MediAgent Cloud Run
# services and grant each only what it needs (OPS-006 follow-up).
#
#   mediagent-api-runtime     the API service  (mediagent-backend)
#   mediagent-worker-runtime  the Nora turn worker (mediagent-chat-worker)
#
# Dry-run by default: prints every command and changes nothing. Pass --apply to run them.
# Safe to re-run: account creation is skipped when the account exists and IAM bindings are
# idempotent. This script never deploys, never touches Cloud Run, and never removes a
# binding from the existing github-actions-deployer account (see docs/chat-worker-setup.md,
# "Least-privilege runtime accounts", for the optional cleanup after verification).
#
# Usage: scripts/setup-runtime-service-accounts.sh [--apply] [--with-observability-writers]
set -euo pipefail

PROJECT="${PROJECT:-medi-agent-490106}"
REGION="${REGION:-us-central1}"
QUEUE="${QUEUE:-nora-turns}"
DEPLOYER_SA="${DEPLOYER_SA:-github-actions-deployer@${PROJECT}.iam.gserviceaccount.com}"
INVOKER_SA="${INVOKER_SA:-nora-turn-invoker@${PROJECT}.iam.gserviceaccount.com}"
API_NAME="mediagent-api-runtime"
WORKER_NAME="mediagent-worker-runtime"
API_SA="${API_NAME}@${PROJECT}.iam.gserviceaccount.com"
WORKER_SA="${WORKER_NAME}@${PROJECT}.iam.gserviceaccount.com"

# Secret Manager secrets each service reads (names only). Keep in step with the
# --update-secrets lists in .github/workflows/deploy-backend.yml.
API_SECRETS=(
  SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET
  GOOGLE_API_KEY DEEPGRAM_API_KEY BACKEND_SENTRY_DSN CRON_AUTH_TOKEN RESEND_API_KEY
  MEDIAGENT_SMART_STATE_KEY NOTIFICATION_TOKEN_SIGNING_SECRET
)
WORKER_SECRETS=(SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET)

APPLY=false
OBSERVABILITY=false
for arg in "$@"; do
  case "${arg}" in
    --apply) APPLY=true ;;
    --with-observability-writers) OBSERVABILITY=true ;;
    -h | --help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "Unknown argument: ${arg}" >&2; exit 2 ;;
  esac
done

if "${APPLY}"; then echo "MODE: APPLY (commands will run)"; else echo "MODE: DRY RUN (nothing changes; pass --apply to execute)"; fi

run() {
  echo "+ $*"
  if "${APPLY}"; then "$@"; fi
}

ensure_account() {
  local name="$1" email="$2" display="$3"
  if gcloud iam service-accounts describe "${email}" --project "${PROJECT}" >/dev/null 2>&1; then
    echo "= ${email} already exists; skipping create"
  else
    run gcloud iam service-accounts create "${name}" --project "${PROJECT}" --display-name "${display}"
  fi
}

project_role() {
  run gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member "serviceAccount:$1" --role "$2" --condition=None --quiet
}

secret_access() {
  local sa="$1" secret
  shift
  for secret in "$@"; do
    run gcloud secrets add-iam-policy-binding "${secret}" --project "${PROJECT}" \
      --member "serviceAccount:${sa}" --role roles/secretmanager.secretAccessor --quiet
  done
}

echo "--- accounts"
ensure_account "${API_NAME}" "${API_SA}" "MediAgent API runtime"
ensure_account "${WORKER_NAME}" "${WORKER_SA}" "MediAgent Nora worker runtime"

echo "--- API runtime: Vertex AI (Gemini), enqueue Nora turns, act as the invoker, read its secrets"
project_role "${API_SA}" roles/aiplatform.user
run gcloud tasks queues add-iam-policy-binding "${QUEUE}" --project "${PROJECT}" --location "${REGION}" \
  --member "serviceAccount:${API_SA}" --role roles/cloudtasks.enqueuer --quiet
run gcloud iam service-accounts add-iam-policy-binding "${INVOKER_SA}" --project "${PROJECT}" \
  --member "serviceAccount:${API_SA}" --role roles/iam.serviceAccountUser --quiet
secret_access "${API_SA}" "${API_SECRETS[@]}"

echo "--- worker runtime: Vertex AI (Gemini), read its secrets"
project_role "${WORKER_SA}" roles/aiplatform.user
secret_access "${WORKER_SA}" "${WORKER_SECRETS[@]}"

if "${OBSERVABILITY}"; then
  echo "--- optional: explicit log and metric writers (Cloud Run container logs do not need them)"
  for sa in "${API_SA}" "${WORKER_SA}"; do
    project_role "${sa}" roles/logging.logWriter
    project_role "${sa}" roles/monitoring.metricWriter
  done
fi

echo "--- deployer: may deploy services that run as the new accounts (actAs, on those accounts only)"
for sa in "${API_SA}" "${WORKER_SA}"; do
  run gcloud iam service-accounts add-iam-policy-binding "${sa}" --project "${PROJECT}" \
    --member "serviceAccount:${DEPLOYER_SA}" --role roles/iam.serviceAccountUser --quiet
done

cat <<NEXT

Next (not done by this script):
  gh variable set CLOUD_RUN_API_RUNTIME_SA --body ${API_SA}
  gh variable set CLOUD_RUN_WORKER_RUNTIME_SA --body ${WORKER_SA}
Then run the Deploy Backend workflow and confirm each new revision runs as its own account.
NEXT
