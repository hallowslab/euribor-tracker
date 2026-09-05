# Euribor Tracker — local dev + server deployment orchestration.
#
# Works whether you run as root (typical in an LXC) or as a user with sudo.
# Server management:
#   make deploy        first-time install on the VM/LXC (systemd + dedicated user)
#   make update        refresh source + deps + data + restart
#   make update-data   refresh current-year data only
#   make backfill      (re)import full history on the server
#   make start|stop|restart|status|logs
#   make timer|timer-status
#   make nginx-install|nginx-remove
#   make uninstall
#
# Local development:
#   make test / make lint

SERVICE     := euribortracker.service
UPDATE_SVC  := euribortracker-update.service
UPDATE_TMR  := euribortracker-update.timer
APP_USER    := euribortracker
APP_DIR     := /opt/euribortracker
UV          := /usr/local/bin/uv

# Empty when running as root (no sudo needed); otherwise 'sudo'.
SUDO := $(shell if [ "$$(id -u)" = "0" ]; then echo; else echo sudo; fi)
# Run a command as the service user, regardless of sudo availability.
AS_APP := bash deploy/run-as-app.sh

.PHONY: help deploy start stop restart status logs update update-data backfill timer timer-status nginx-install nginx-remove test lint uninstall

help:
	@echo "Server: deploy | update | update-data | backfill | start | stop | restart | status | logs"
	@echo "        timer | timer-status | nginx-install | nginx-remove | uninstall"
	@echo "Dev:    test | lint"

deploy:
	$(SUDO) bash deploy/install.sh

start:
	$(SUDO) systemctl start $(SERVICE)

stop:
	$(SUDO) systemctl stop $(SERVICE)

restart:
	$(SUDO) systemctl restart $(SERVICE)

status:
	systemctl --no-pager --full status $(SERVICE)

logs:
	$(SUDO) journalctl -u $(SERVICE) -f

update:
	$(SUDO) bash deploy/update.sh

update-data:
	$(AS_APP) $(UV) run --project $(APP_DIR) euribortracker update
	$(SUDO) systemctl restart $(SERVICE)

backfill:
	$(AS_APP) $(UV) run --project $(APP_DIR) euribortracker backfill

timer:
	$(SUDO) systemctl enable --now $(UPDATE_TMR)

timer-status:
	$(SUDO) systemctl --no-pager list-timers $(UPDATE_TMR)

nginx-install:
	$(SUDO) apt-get update -qq
	$(SUDO) apt-get install -y -qq nginx
	$(SUDO) install -d /etc/nginx/sites-available /etc/nginx/sites-enabled
	$(SUDO) cp deploy/nginx/euribortracker.conf /etc/nginx/sites-available/euribortracker.conf
	$(SUDO) ln -sf /etc/nginx/sites-available/euribortracker.conf /etc/nginx/sites-enabled/euribortracker.conf
	$(SUDO) rm -f /etc/nginx/sites-enabled/default
	$(SUDO) nginx -t
	$(SUDO) systemctl enable --now nginx
	$(SUDO) systemctl reload nginx
	@echo "Nginx reverse proxy enabled. Browse to http://<vm-or-lxc-ip>"

nginx-remove:
	$(SUDO) rm -f /etc/nginx/sites-enabled/euribortracker.conf /etc/nginx/sites-available/euribortracker.conf
	$(SUDO) nginx -t && $(SUDO) systemctl reload nginx
	@echo "Nginx reverse proxy removed. App still on 127.0.0.1:8000."

test:
	uv run pytest -q

lint:
	uv run ruff check .

uninstall:
	$(SUDO) systemctl disable --now $(UPDATE_TMR) 2>/dev/null || true
	$(SUDO) rm -f /etc/systemd/system/$(UPDATE_SVC) /etc/systemd/system/$(UPDATE_TMR)
	$(SUDO) systemctl disable --now $(SERVICE) 2>/dev/null || true
	$(SUDO) rm -f /etc/systemd/system/$(SERVICE)
	$(SUDO) systemctl daemon-reload
	$(SUDO) userdel -r $(APP_USER) 2>/dev/null || true
	$(SUDO) rm -rf $(APP_DIR) /etc/euribortracker
	@echo "Removed. Data dir /var/lib/euribortracker left in place (back it up before deleting)."