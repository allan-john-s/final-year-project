#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Development bootstrap — installs backend and frontend dependencies.
#
# Usage:  ./scripts/bootstrap.sh [--python python3.12]
# -----------------------------------------------------------------------------
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.12}"

echo "==> Backend ($PYTHON_BIN)"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "!! '$PYTHON_BIN' not found. Install Python 3.12+ (e.g. 'brew install python@3.12')." >&2
  exit 1
fi

if [ ! -d "backend/.venv" ]; then
  "$PYTHON_BIN" -m venv backend/.venv
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt
deactivate

echo "==> Frontend"
if [ ! -d "frontend/node_modules" ]; then
  (cd frontend && npm install)
else
  (cd frontend && npm ci)
fi

echo "==> Done. See README.md for run instructions."
