#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv-depthflow-api}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required on PATH" >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install --upgrade build

mkdir -p "$ROOT_DIR/dist"
rm -f "$ROOT_DIR"/dist/depthflow-*.whl
python -m build --wheel --outdir "$ROOT_DIR/dist" "$ROOT_DIR"
python -m pip install --force-reinstall "$ROOT_DIR"/dist/depthflow-*.whl

export DEPTHFLOW_API_WORKDIR="${DEPTHFLOW_API_WORKDIR:-$ROOT_DIR/.depthflow-api}"
export DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET="${DEPTHFLOW_API_DEFAULT_OUTPUT_TARGET:-local}"

exec python -m uvicorn \
  depthflow_api.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers "$UVICORN_WORKERS" \
  --log-level "$UVICORN_LOG_LEVEL"
