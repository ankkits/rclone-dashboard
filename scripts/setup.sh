#!/usr/bin/env bash
set -euo pipefail

mkdir -p bin
echo "[setup] downloading rclone..."
curl -sL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip
unzip -o /tmp/rclone.zip -d /tmp >/dev/null
RCLONE_DIR=$(find /tmp -maxdepth 1 -type d -name "rclone-*-linux-amd64" | head -n1)
cp "$RCLONE_DIR/rclone" bin/rclone
chmod +x bin/rclone
echo "[setup] rclone ready: $(bin/rclone version | head -n1)"
