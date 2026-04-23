#!/usr/bin/env bash
set -euo pipefail

# Generate a single HTML coverage report in backend/htmlcov and avoid duplicate root reports.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_DIR}/.." && pwd)"

rm -rf "${REPO_ROOT}/htmlcov" "${BACKEND_DIR}/htmlcov"

cd "${BACKEND_DIR}"
PYTHONPATH=src .venv/bin/pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html:htmlcov

echo "HTML coverage generated: ${BACKEND_DIR}/htmlcov/index.html"
