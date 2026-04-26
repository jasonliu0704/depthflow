#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${IMAGE_TAG:-depthflow-api:deploy}"
ARCHIVE_PATH="${ARCHIVE_PATH:-$ROOT_DIR/dist/depthflow-api-image.tar.gz}"
SAVE_ARCHIVE="${SAVE_ARCHIVE:-1}"

mkdir -p "$ROOT_DIR/dist"

echo "[depthflow-api] building image $IMAGE_TAG"
docker build \
  -f "$ROOT_DIR/Dockerfile.depthflow-api" \
  -t "$IMAGE_TAG" \
  "$ROOT_DIR"

if [[ "$SAVE_ARCHIVE" == "1" ]]; then
  echo "[depthflow-api] saving archive to $ARCHIVE_PATH"
  docker save "$IMAGE_TAG" | gzip > "$ARCHIVE_PATH"
fi

echo "[depthflow-api] package complete"
