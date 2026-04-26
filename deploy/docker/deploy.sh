#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/compose.yml}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.depthflow-api}"
ENV_EXAMPLE="${ENV_EXAMPLE:-$APP_DIR/depthflow-api.env.example}"
IMAGE_ARCHIVE="${IMAGE_ARCHIVE:-$APP_DIR/depthflow-api-image.tar.gz}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on PATH" >&2
  exit 1
fi

docker compose version >/dev/null 2>&1 || {
  echo "docker compose plugin is required" >&2
  exit 1
}

mkdir -p "$APP_DIR/workdir" "$APP_DIR/output"

if [[ ! -f "$ENV_FILE" && -f "$ENV_EXAMPLE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file at $ENV_FILE" >&2
  exit 1
fi

if [[ -f "$IMAGE_ARCHIVE" ]]; then
  echo "[depthflow-api] loading image archive"
  gzip -dc "$IMAGE_ARCHIVE" | docker load
fi

echo "[depthflow-api] starting stack"
docker compose \
  --project-name depthflow-api \
  --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" \
  up -d --remove-orphans

echo "[depthflow-api] deployment complete"
