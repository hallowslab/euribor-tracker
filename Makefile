# Euribor Tracker — local dev + server deployment orchestration.
#
# Server management (run in the repo, requires sudo):
#   make deploy        first-time install on the VM/LXC (systemd + dedicated user)
#   make update        refresh source + deps + data + restart
#   make update-data   refresh current-year data only
#   make backfill      (re)import full history on the server
#   make start|stop|restart|status|logs
#   make uninstall
#
# Local development:
#   make test / make lint

SERVICE  := euribortracker.service
UPDATE_SVC := euribortracker-update.service
UPDATE_TMR := euribortracker-update.timer
APP_USER := euribortracker
APP_DIR  := /opt/euribortracker
UV       := /usr/local/bin/uv

.PHONY: help deploy start stop restart status logs update update-data backfill timer timer-status nginx-install nginx-remove test lint uninstall

help:
	@echo "Server: deploy | update | update-data | backfill | start | stop | restart | status | logs"
	@echo "        timer | timer-status | nginx-install | nginx-remove | uninstall"
	@echo "Dev:    test | lint"

deploy:
	sudo ./deploy/install.sh

start:
	sudo systemctl start $(SERVICE)

stop:
	sudo systemctl stop $(SERVICE)

restart:
	sudo systemctl restart $(SERVICE)

status:
	systemctl --no-pager --full status $(SERVICE)

logs:
	sudo journalctl -u $(SERVICE) -f

update:
	sudo ./deploy/update.sh

update-data:
	sudo -u $(APP_USER) $(UV) run --project $(APP_DIR) euribortracker update
	sudo systemctl restart $(SERVICE)

backfill:
	sudo -u $(APP_USER) $(UV) run --project $(APP_DIR) euribortracker backfill

timer:
	sudo systemctl enable --now $(UPDATE_TMR)

timer-status:
	sudo systemctl --no-pager list-timers $(UPDATE_TMR)

nginx-install:
	sudo apt-get update -qq
	sudo apt-get install -y -qq nginx
	sudo install -d /etc/nginx/sites-available /etc/nginx/sites-enabled
	sudo cp deploy/nginx/euribortracker.conf /etc/nginx/sites-available/euribortracker.conf
	sudo ln -sf /etc/nginx/sites-available/euribortracker.conf /etc/nginx/sites-enabled/euribortracker.conf
	sudo rm -f /etc/nginx/sites-enabled/default
	sudo nginx -t
	sudo systemctl enable --now nginx
	sudo systemctl reload nginx
	@echo "Nginx reverse proxy enabled. Browse to http://<vm-or-lxc-ip>"

nginx-remove:
	sudo rm -f /etc/nginx/sites-enabled/euribortracker.conf /etc/nginx/sites-available/euribortracker.conf
	sudo nginx -t && sudo systemctl reload nginx
	@echo "Nginx reverse proxy removed. App still on 127.0.0.1:8000."

test:
	uv run pytest -q

lint:
	uv run ruff check .

uninstall:
	sudo systemctl disable --now $(UPDATE_TMR) 2>/dev/null || true
	sudo rm -f /etc/systemd/system/$(UPDATE_SVC) /etc/systemd/system/$(UPDATE_TMR)
	sudo systemctl disable --now $(SERVICE) 2>/dev/null || true
	sudo rm -f /etc/systemd/system/$(SERVICE)
	sudo systemctl daemon-reload
	sudo userdel -r $(APP_USER) 2>/dev/null || true
	sudo rm -rf $(APP_DIR) /etc/euribortracker
	@echo "Removed. Data dir /var/lib/euribortracker left in place (back it up before deleting)."