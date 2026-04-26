#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

export DEPTHFLOW_API_WORKDIR="${DEPTHFLOW_API_WORKDIR:-$ROOT_DIR/.depthflow-api}"
export DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET="${DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET:-local}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
export UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

mkdir -p "$DEPTHFLOW_API_WORKDIR"
mkdir -p "$ROOT_DIR/output"

exec python -m uvicorn \
  depthflow_api.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$UVICORN_WORKERS" \
  --log-level "$UVICORN_LOG_LEVEL"
