#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv-depthflow-api}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.depthflow-api}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Missing virtualenv at $VENV_DIR. Run deploy/azure-vm/install.sh first." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing environment file at $ENV_FILE" >&2
  exit 1
fi

source "$VENV_DIR/bin/activate"
set -a
source "$ENV_FILE"
set +a

export DEPTHFLOW_API_WORKDIR="${DEPTHFLOW_API_WORKDIR:-$ROOT_DIR/.depthflow-api}"
export DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET="${DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET:-local}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
export UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

exec python -m uvicorn \
  depthflow_api.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$UVICORN_WORKERS" \
  --log-level "$UVICORN_LOG_LEVEL"
