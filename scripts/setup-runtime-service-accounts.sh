#!/usr/bin/env bash
# Create the least-privilege runtime service accounts for the MediAgent Cloud Run
# services and grant each only what it needs (OPS-006 follow-up).
#
#   mediagent-api-runtime     the API service  (mediagent-backend)
#   mediagent-worker-runtime  the Nora turn worker (mediagent-chat-worker)
#   mediagent-jobs-runtime    the Cloud Run Jobs (document ingestion, health-knowledge refresh)
#
# Dry-run by default: prints every command and changes nothing. Pass --apply to run them.
# Safe to re-run: account creation is skipped when the account exists and IAM bindings are
# idempotent. This script never deploys, never touches Cloud Run, and never removes a
# binding from the existing github-actions-deployer account (see docs/chat-worker-setup.md,
# "Least-privilege runtime accounts", for the optional cleanup after verification).
#
# The Cloud Scheduler callers (mediagent-doc-ingest-sched, mediagent-knowledge-sched) are
# already dedicated invoker-only accounts (run.invoker on one job each), so no scheduler
# account is created here.
#
# --trim-deployer is a separate, later step: it removes the github-actions-deployer roles
# that deploying no longer needs, after the services and jobs run as their own accounts. It
# creates nothing and is also dry-run unless --apply is given.
#
# Usage: scripts/setup-runtime-service-accounts.sh [--apply] [--with-observability-writers]
#        scripts/setup-runtime-service-accounts.sh --trim-deployer [--apply]
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
JOBS_NAME="mediagent-jobs-runtime"
JOBS_SA="${JOBS_NAME}@${PROJECT}.iam.gserviceaccount.com"
SERVICES=(mediagent-backend mediagent-chat-worker)
JOBS=(mediagent-document-ingestion mediagent-health-knowledge-refresh)
PROPAGATION_WAIT_SECONDS="${PROPAGATION_WAIT_SECONDS:-20}"

# Secret Manager secrets each service reads (names only). Keep in step with the
# --update-secrets lists in .github/workflows/deploy-backend.yml.
API_SECRETS=(
  SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET
  GOOGLE_API_KEY DEEPGRAM_API_KEY BACKEND_SENTRY_DSN CRON_AUTH_TOKEN RESEND_API_KEY
  MEDIAGENT_SMART_STATE_KEY NOTIFICATION_TOKEN_SIGNING_SECRET
)
WORKER_SECRETS=(SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET)
# Both jobs inject exactly these four (--set-secrets in deploy-backend.yml).
JOBS_SECRETS=(SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY SUPABASE_JWT_SECRET)

APPLY=false
OBSERVABILITY=false
TRIM=false
for arg in "$@"; do
  case "${arg}" in
    --apply) APPLY=true ;;
    --with-observability-writers) OBSERVABILITY=true ;;
    --trim-deployer) TRIM=true ;;
    -h | --help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "Unknown argument: ${arg}" >&2; exit 2 ;;
  esac
done

if "${APPLY}"; then echo "MODE: APPLY (commands will run)"; else echo "MODE: DRY RUN (nothing changes; pass --apply to execute)"; fi

run() {
  echo "+ $*"
  if "${APPLY}"; then "$@"; fi
}

# Roles on the deployer that deploying does not need once nothing runs as it (role|reason).
# Kept on purpose: run.admin (deploy services and jobs), artifactregistry.admin/repoAdmin (the
# workflow creates the repository, sets cleanup policies and deletes images),
# iam.serviceAccountUser (actAs on the runtime accounts, also needed for rollback),
# serviceusage.serviceUsageConsumer (API quota project) and iam.serviceAccountTokenCreator
# (purpose not established; review separately).
TRIM_ROLES=(
  "roles/secretmanager.secretAccessor|runtime accounts read their own secrets; deploying only references them"
  "roles/aiplatform.user|Vertex calls run as the api, worker and jobs accounts"
  "roles/ml.admin|nothing in the workflow or code administers AI Platform"
  "roles/run.developer|subset of run.admin, which stays"
  "roles/artifactregistry.writer|subset of artifactregistry.admin, which stays"
)

# Read-only: print who each service and job runs as; return 1 if any still uses the deployer
# or could not be read.
runtime_identities_ready() {
  local ok=0 name sa
  for name in "${SERVICES[@]}"; do
    sa="$(gcloud run services describe "${name}" --project "${PROJECT}" --region "${REGION}" \
      --format 'value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
    echo "  service ${name}: ${sa:-unreadable}"
    if [ -z "${sa}" ] || [ "${sa}" = "${DEPLOYER_SA}" ]; then ok=1; fi
  done
  for name in "${JOBS[@]}"; do
    sa="$(gcloud run jobs describe "${name}" --project "${PROJECT}" --region "${REGION}" \
      --format 'value(spec.template.spec.template.spec.serviceAccountName)' 2>/dev/null || true)"
    echo "  job ${name}: ${sa:-unreadable}"
    if [ -z "${sa}" ] || [ "${sa}" = "${DEPLOYER_SA}" ]; then ok=1; fi
  done
  return "${ok}"
}

trim_deployer() {
  local entry role why
  echo "--- PRECONDITIONS (all must hold before --trim-deployer --apply)"
  echo "  [ ] CLOUD_RUN_API_RUNTIME_SA, CLOUD_RUN_WORKER_RUNTIME_SA and CLOUD_RUN_JOBS_RUNTIME_SA are set"
  echo "  [ ] a Deploy Backend run succeeded afterwards; both services and both jobs run as their own account (checked below)"
  echo "  [ ] a real Nora turn, a document ingestion run and a knowledge refresh succeeded (Cloud Logging)"
  echo "  [ ] a week of clean traffic, and the requester explicitly authorizes this removal"
  echo "--- read-only check: nothing may still run as ${DEPLOYER_SA}"
  if ! runtime_identities_ready; then
    echo "NOT READY: something still runs as the deployer, or could not be read."
    if "${APPLY}"; then echo "Refusing to --apply." >&2; exit 1; fi
  fi
  echo "--- removals (rollback is the printed command for each)"
  for entry in "${TRIM_ROLES[@]}"; do
    role="${entry%%|*}"; why="${entry#*|}"
    echo "# ${role}: ${why}"
    echo "#   rollback: gcloud projects add-iam-policy-binding ${PROJECT} --member serviceAccount:${DEPLOYER_SA} --role ${role} --condition=None"
    run gcloud projects remove-iam-policy-binding "${PROJECT}" \
      --member "serviceAccount:${DEPLOYER_SA}" --role "${role}" --condition=None --quiet
  done
  echo "Then re-run Deploy Backend once to prove deploying still works."
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

if "${TRIM}"; then trim_deployer; exit 0; fi

echo "--- accounts"
ensure_account "${API_NAME}" "${API_SA}" "MediAgent API runtime"
ensure_account "${WORKER_NAME}" "${WORKER_SA}" "MediAgent Nora worker runtime"
ensure_account "${JOBS_NAME}" "${JOBS_SA}" "MediAgent Cloud Run Jobs runtime"
# A new account can take a few seconds to become visible to IAM bindings.
if "${APPLY}"; then
  echo "Waiting ${PROPAGATION_WAIT_SECONDS}s for the new accounts to propagate"
  sleep "${PROPAGATION_WAIT_SECONDS}"
else
  echo "(apply mode waits ${PROPAGATION_WAIT_SECONDS}s here for account propagation)"
fi

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

echo "--- jobs runtime: Vertex AI (document ingestion calls Gemini), read the 4 Supabase secrets"
project_role "${JOBS_SA}" roles/aiplatform.user
secret_access "${JOBS_SA}" "${JOBS_SECRETS[@]}"

if "${OBSERVABILITY}"; then
  echo "--- optional: explicit log and metric writers (Cloud Run container logs do not need them)"
  for sa in "${API_SA}" "${WORKER_SA}" "${JOBS_SA}"; do
    project_role "${sa}" roles/logging.logWriter
    project_role "${sa}" roles/monitoring.metricWriter
  done
fi

echo "--- deployer: may deploy services that run as the new accounts (actAs, on those accounts only)"
for sa in "${API_SA}" "${WORKER_SA}" "${JOBS_SA}"; do
  run gcloud iam service-accounts add-iam-policy-binding "${sa}" --project "${PROJECT}" \
    --member "serviceAccount:${DEPLOYER_SA}" --role roles/iam.serviceAccountUser --quiet
done

cat <<NEXT

Next (not done by this script):
  gh variable set CLOUD_RUN_API_RUNTIME_SA --body ${API_SA}
  gh variable set CLOUD_RUN_WORKER_RUNTIME_SA --body ${WORKER_SA}
  gh variable set CLOUD_RUN_JOBS_RUNTIME_SA --body ${JOBS_SA}
Then run the Deploy Backend workflow and confirm each new revision runs as its own account.
NEXT
