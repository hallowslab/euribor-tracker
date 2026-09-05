#!/usr/bin/env bash
# Install Euribor Tracker on a Linux VM/LXC as a systemd service.
#
# Usage:
#   sudo ./deploy/install.sh [SOURCE_DIR]     # SOURCE_DIR defaults to the repo containing deploy/
#   SKIP_BACKFILL=1 sudo ./deploy/install.sh  # skip the initial data import
#   INSTALL_NGINX=1 sudo ./deploy/install.sh  # also install the nginx LAN reverse proxy
#
# Idempotent: safe to re-run. Installs uv, creates the dedicated system user,
# copies the source, installs dependencies, imports history, and enables the
# systemd unit.
set -euo pipefail

APP_USER="euribortracker"
APP_GROUP="euribortracker"
APP_DIR="/opt/euribortracker"
DATA_DIR="/var/lib/euribortracker"
CONF_DIR="/etc/euribortracker"
SERVICE="euribortracker.service"
UNIT_DIR="/etc/systemd/system"
SRC_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
UV_BIN=""

need_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "Run as root: sudo $0 ${1:-}" >&2
    exit 1
  fi
}

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

install_uv() {
  # uv must be reachable by the service user. The Astral installer defaults to
  # $HOME/.local/bin (i.e. /root/.local/bin), which the app user cannot traverse
  # (0700). So install uv directly into /usr/local/bin via UV_INSTALL_DIR.
  # A real binary there is fine; a symlink into /root (or any user home) is NOT
  # usable by other users and is replaced on re-run.
  if [[ -x /usr/local/bin/uv && ! -L /usr/local/bin/uv ]]; then
    UV_BIN="/usr/local/bin/uv"
    echo "   uv: $UV_BIN"
    return
  fi
  echo ">> Installing uv (Astral) to /usr/local/bin…"
  export HOME=/root
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
  if [[ ! -x /usr/local/bin/uv || -L /usr/local/bin/uv ]]; then
    echo "uv installation failed" >&2
    exit 1
  fi
  UV_BIN="/usr/local/bin/uv"
  echo "   uv: $UV_BIN"
}

ensure_user() {
  if ! id "$APP_USER" >/dev/null 2>&1; then
    echo ">> Creating system user '$APP_USER'…"
    useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin --create-home "$APP_USER"
  fi
  install -d -o "$APP_USER" -g "$APP_GROUP" "$DATA_DIR"
  install -d -o root -g root -m 0750 "$CONF_DIR"
  if [[ ! -f "$CONF_DIR/env" ]]; then
    install -o root -g root -m 0640 /dev/null "$CONF_DIR/env"
  fi
}

copy_source() {
  echo ">> Copying source to $APP_DIR…"
  install -d -o "$APP_USER" -g "$APP_GROUP" "$APP_DIR"
  tar --exclude=.git --exclude=.venv --exclude=data -C "$SRC_DIR" -cf - . | \
    tar -C "$APP_DIR" -xf -
  chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
}

sync_deps() {
  echo ">> Installing dependencies (uv sync)…"
  as_user "$UV_BIN" sync --project "$APP_DIR"
}

backfill() {
  if [[ "${SKIP_BACKFILL:-0}" == "1" ]]; then
    echo ">> Skipping backfill (SKIP_BACKFILL=1)."
    return
  fi
  echo ">> Importing historical Euribor data (1999→today)…"
  as_user "$UV_BIN" run --project "$APP_DIR" euribortracker backfill
}

install_unit() {
  echo ">> Installing systemd unit…"
  cp "$SRC_DIR/deploy/$SERVICE" "$UNIT_DIR/$SERVICE"
  chmod 0644 "$UNIT_DIR/$SERVICE"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE"
}

install_timer() {
  echo ">> Installing daily update timer…"
  for f in euribortracker-update.service euribortracker-update.timer; do
    cp "$SRC_DIR/deploy/$f" "$UNIT_DIR/$f"
    chmod 0644 "$UNIT_DIR/$f"
  done
  systemctl daemon-reload
  systemctl enable --now euribortracker-update.timer
}

install_nginx() {
  if [[ "${INSTALL_NGINX:-0}" != "1" ]]; then
    return
  fi
  echo ">> Installing nginx reverse proxy…"
  apt-get install -y -qq nginx
  install -d /etc/nginx/sites-available /etc/nginx/sites-enabled
  cp "$SRC_DIR/deploy/nginx/euribortracker.conf" /etc/nginx/sites-available/euribortracker.conf
  ln -sf /etc/nginx/sites-available/euribortracker.conf /etc/nginx/sites-enabled/euribortracker.conf
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx
}

main() {
  need_root
  if ! command -v curl >/dev/null 2>&1; then
    echo ">> Installing curl…"
    apt-get update -qq
    apt-get install -y -qq curl ca-certificates
  fi
  install_uv
  ensure_user
  copy_source
  sync_deps
  backfill
  install_unit
  install_timer
  install_nginx
  echo
  echo "=== Installed. ==="
  systemctl --no-pager --full status "$SERVICE" || true
  echo
  echo "Point your browser at: http://<vm-or-lxc-ip>:8000"
  echo "Data lives in:         $DATA_DIR/euribor.db"
  echo "Config overrides:      $CONF_DIR/env (optional)"
  echo "Management:            make start|stop|restart|status|logs|update"
  echo "Daily refresh:         make timer-status (runs at 13:00 server time)"
  if [[ "${INSTALL_NGINX:-0}" == "1" ]]; then
    echo "LAN access (nginx):    http://<vm-or-lxc-ip>  (port 80)"
  fi
}

main "$@"