#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo "Backend virtualenv not found at $BACKEND_DIR/.venv"
  exit 1
fi

# Kill anything already listening on 8000 to avoid stale process mixups.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  lsof -tiTCP:8000 -sTCP:LISTEN | xargs kill -9 >/dev/null 2>&1 || true
fi

cd "$BACKEND_DIR"
source .venv/bin/activate
export PYTHONPATH=src

echo "Starting backend on http://127.0.0.1:8000"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
