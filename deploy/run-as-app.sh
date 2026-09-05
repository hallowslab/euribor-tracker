#!/usr/bin/env bash
# Run a command as the euribortracker service user.
# Works as root (runuser) or as a sudo-enabled user (sudo).
set -euo pipefail

APP_USER="euribortracker"
DATA_DIR="/var/lib/euribortracker"

# Make CLI commands write to the same DB the systemd service reads.
export EURIBORTRACKER_DB_PATH="$DATA_DIR/euribor.db"

if [[ "$EUID" -eq 0 ]]; then
  exec runuser -u "$APP_USER" -- "$@"
elif command -v sudo >/dev/null 2>&1; then
  exec sudo -u "$APP_USER" "$@"
else
  echo "Need root (runuser) or sudo to switch to user $APP_USER" >&2
  exit 1
fi