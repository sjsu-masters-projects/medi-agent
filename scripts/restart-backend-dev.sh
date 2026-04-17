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
  pids="$(lsof -tiTCP:8000 -sTCP:LISTEN || true)"
  if [[ -n "$pids" ]]; then
    # Try graceful shutdown first.
    kill $pids >/dev/null 2>&1 || true

    # Wait briefly for the process to release the port.
    for _ in {1..10}; do
      if ! lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done

    # Force kill only if the process ignored SIGTERM.
    if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
      kill -9 $pids >/dev/null 2>&1 || true
    fi
  fi
fi

cd "$BACKEND_DIR"
source .venv/bin/activate
export PYTHONPATH=src

echo "Starting backend on http://127.0.0.1:8000"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
