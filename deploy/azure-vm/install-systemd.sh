#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-depthflow-api}"
SERVICE_USER="${SERVICE_USER:-$USER}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.depthflow-api}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$UNIT_PATH" >/dev/null <<EOF
[Unit]
Description=DepthFlow Batch API
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$ROOT_DIR
Environment=ENV_FILE=$ENV_FILE
ExecStart=/usr/bin/env bash $ROOT_DIR/deploy/azure-vm/start.sh
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "[depthflow-api] installed systemd unit at $UNIT_PATH"
echo "[depthflow-api] start with: sudo systemctl start $SERVICE_NAME"
