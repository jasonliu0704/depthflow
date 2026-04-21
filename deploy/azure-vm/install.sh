#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv-depthflow-api}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[depthflow-api] installing OS packages"
sudo apt-get update
sudo apt-get install -y \
  ffmpeg \
  git \
  python3 \
  python3-dev \
  python3-pip \
  python3-venv \
  build-essential \
  pkg-config \
  libgl1 \
  libegl1 \
  libglib2.0-0

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[depthflow-api] creating virtualenv at $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "[depthflow-api] upgrading build tools"
python -m pip install --upgrade pip build wheel

echo "[depthflow-api] building wheel"
mkdir -p "$ROOT_DIR/dist"
rm -f "$ROOT_DIR"/dist/depthflow-*.whl
python -m build --wheel --outdir "$ROOT_DIR/dist" "$ROOT_DIR"

echo "[depthflow-api] installing wheel"
python -m pip install --force-reinstall "$ROOT_DIR"/dist/depthflow-*.whl

mkdir -p "$ROOT_DIR/.depthflow-api"
mkdir -p "$ROOT_DIR/output"

echo "[depthflow-api] install complete"
