#!/usr/bin/env bash
# Update Euribor Tracker on the server: refresh source, reinstall deps,
# refresh current-year data, and restart the service.
#
# Usage: sudo ./deploy/update.sh [SOURCE_DIR]
#
# NOTE: re-copies the app source from SOURCE_DIR (default: the repo containing
# deploy/). Local modifications made directly under /opt/euribortracker are
# overwritten; keep overrides in /etc/euribortracker/env instead.
set -euo pipefail

APP_USER="euribortracker"
APP_DIR="/opt/euribortracker"
SERVICE="euribortracker.service"
SRC_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
UV_BIN="$(command -v uv || echo /usr/local/bin/uv)"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run as root: sudo $0 ${1:-}" >&2
  exit 1
fi

# Run a command as the app user. Works without sudo on minimal LXC/containers.
as_user() {
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "$APP_USER" -- "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -u "$APP_USER" "$@"
  else
    echo "Cannot switch to user $APP_USER (no runuser/sudo)" >&2
    exit 1
  fi
}

echo ">> Refreshing source…"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
tar --exclude=.git --exclude=.venv --exclude=data -C "$SRC_DIR" -cf - . | \
  tar -C "$APP_DIR" -xf -
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo ">> Reinstalling dependencies…"
as_user "$UV_BIN" sync --project "$APP_DIR"

echo ">> Refreshing current-year Euribor data…"
as_user "$UV_BIN" run --project "$APP_DIR" euribortracker update

echo ">> Restarting service…"
systemctl restart "$SERVICE"
systemctl --no-pager --full status "$SERVICE" || true