# Euribor Tracker

Monitor Euribor interest rates and estimate how they affect a variable-rate
mortgage (built for a Portuguese mortgage).

Lightweight stack: **FastAPI + Jinja2 + Chart.js + SQLite** (stdlib `sqlite3`), managed with **uv**.

## Data sources

- **EMMI** - the official publisher of Euribor (daily fixings, ~11:00 CET on TARGET business days).
- **euriborrates.com** - the current external data provider used by this application. It is an
  **aggregator** of the official daily fixings, *not* the official source. Full daily history
  since 1999 for 1M/3M/6M/12M, no API key required.
- **ECB (SDW)** - supplementary macroeconomic/reference data only. The ECB does **not** publish
  daily Euribor fixings (only monthly/quarterly/annual averages), so it is not used for daily data.

The provider layer is abstracted (`app/providers/base.py`). Adding an EMMI, FRED or other
provider later requires a new class only - no changes to the domain model, mortgage logic, API or UI.

Every stored fixing records: tenor, fixing date, rate, source, source URL and `retrieved_at`.
The **fixing date** is the publication date, never the retrieval date.

## Quick start

```bash
uv sync                                    # install dependencies
uv run euribortracker backfill             # import full history 1999->today (idempotent)
uv run euribortracker update               # refresh current year (run daily)
uv run euribortracker serve                # http://127.0.0.1:8000
```

Configure your mortgage under the **Mortgage** tab. Then the **Dashboard** shows the latest
Euribor, change vs previous publication, estimated mortgage rate, next revision and estimated
monthly payment for the selected maturity (default 6M).

## CLI

| Command | Purpose |
| --- | --- |
| `euribortracker backfill [--year YYYY] [--tenors 6M,12M]` | Full historical import (idempotent) |
| `euribortracker update [--tenors ...]` | Refresh current year only |
| `euribortracker coverage` | Per-tenor stored range + detected anomalies |
| `euribortracker evaluate-alerts` | Evaluate alerts and notify active channels |
| `euribortracker serve [--host --port --reload]` | Run the web app |

## API

- `GET /api/rates/{tenor}/latest` - latest fixing, previous fixing, change (pp and %), staleness flag
- `GET /api/rates/{tenor}/series?start=&end=` - time series
- `GET /api/rates/{tenor}/stats?period=1y` - min/max/avg, deltas vs 1w/1m/3m/6m/1y/2y/5y/10y
- `GET /api/rates/meta` - data coverage, source provenance, anomalies
- `GET|PUT /api/mortgage/config` - mortgage configuration
- `GET /api/mortgage/overview` - current estimate
- `GET /api/mortgage/simulate?euribor=1.5,2.0,2.5,3.0,4.0` - payment scenarios
- `GET|POST /api/alerts`, `DELETE /api/alerts/{id}`, `POST /api/alerts/evaluate`

## Data integrity

- Imports are **idempotent**: re-running never duplicates fixings.
- A previously stored fixing that changes unexpectedly is **logged as an anomaly and never
  silently overwritten** (stored value kept).
- Missing business days are simply absent - weekends/holidays have no fixing and nothing is
  invented or interpolated.
- The UI flags when the latest available fixing is not from today's expected publication day.

## Terminology

The UI distinguishes, and never conflates:

- **percentage (%)** - an actual interest rate, e.g. `2.789%`
- **percentage points (pp)** - the difference between two rates, e.g. `-0.42 pp`

Mortgage interest rate = **Euribor + bank spread**. All mortgage figures are **estimates**
unless the exact contractual calculation rules of the mortgage are configured. This tool is
for monitoring and estimation, not financial advice.

## Development

```bash
uv run pytest       # tests (mortgage math, pp/% conversions, stats, importer, provider parsing)
uv run ruff check . # lint
```

Configuration is via environment variables:

| Variable | Default |
| --- | --- |
| `EURIBORTRACKER_DB_PATH` | `data/euribor.db` |
| `EURIBORTRACKER_PROVIDER_URL` | `https://euriborrates.com` |

## Deployment (VM / LXC)

The app runs as a **systemd service under a dedicated system user** (`euribortracker`),
so it auto-starts on boot, restarts on crash, and logs to journald. The Makefile
orchestrates the common operations; systemd does the actual process supervision.

| Role | Path |
| --- | --- |
| Application code | `/opt/euribortracker` |
| Data (SQLite) | `/var/lib/euribortracker/euribor.db` |
| Config overrides | `/etc/euribortracker/env` (optional, see below) |
| System user | `euribortracker` (no login) |

### First install

```bash
# on the VM/LXC, from a checkout of this repo:
sudo apt-get update && sudo apt-get install -y make curl   # Debian/Ubuntu
make deploy
# or skip the initial data import: SKIP_BACKFILL=1 sudo ./deploy/install.sh
```

`install.sh` is idempotent. It: installs `uv`, creates the `euribortracker` user,
copies the source to `/opt/euribortracker`, runs `uv sync`, imports full history
(1999→today), and enables+starts `euribortracker.service`.

The service binds `127.0.0.1:8000`. To expose it on the LAN, use the provided
optional nginx reverse proxy (recommended) or edit the service to bind `0.0.0.0`.
The service file has basic hardening (`ProtectSystem=full`, `NoNewPrivileges`,
`ReadWritePaths` limited to the data dir).

### Expose to the LAN (optional nginx reverse proxy)

The app stays on `127.0.0.1:8000`; nginx fronts it on port 80.

```bash
make nginx-install     # installs nginx, config, disables the default site, reloads
# browse to http://<vm-or-lxc-ip>
make nginx-remove      # revert
```

`INSTALL_NGINX=1 sudo ./deploy/install.sh` does the same during first install.
The nginx config (`deploy/nginx/euribortracker.conf`) includes a commented TLS
block for certbot. For a bridged LXC/VM remember to allow inbound port 80
(ufw/iptables/proxmox firewall) and use a fixed IP or DHCP reservation.

### Day-to-day management

```bash
make status         # service state
make logs           # follow journald logs
make update-data    # refresh current-year Euribor data, restart (manual)
make update         # pull new code + deps + data + restart
make backfill       # re-import full history
make timer-status   # show the daily refresh schedule
make start|stop|restart
make uninstall      # remove service + user + /opt (keeps /var/lib data)
```

### Automatic daily refresh

`deploy/install.sh` also installs a **systemd timer** that runs
`euribortracker update` once a day (default `13:00` server-local time, with
`Persistent=true` so a missed run fires after boot). This replaces the need to
run `make update-data` by hand.

```bash
make timer-status        # next fire time / last run
sudo systemctl list-timers euribortracker-update.timer
journalctl -u euribortracker-update.service   # logs of the last run
```

To change the schedule, edit `OnCalendar=` in
`/etc/systemd/system/euribortracker-update.timer` (syntax per `man systemd.time`),
then `sudo systemctl daemon-reload && sudo systemctl restart euribortracker-update.timer`.

Euribor is fixed at ~11:00 CET; the timer runs after publication. If your LXC is
on UTC and you want it closer to the publication time, use
`OnCalendar=*-*-* 12:00:00 Europe/Lisbon` (timezones are allowed in `OnCalendar`).

Prefer cron? Equivalent one-liner (runs as root, drops to the app user):

```
0 13 * * * sudo -u euribortracker /usr/local/bin/uv run --no-sync --project /opt/euribortracker euribortracker update
```

Optional config overrides go in `/etc/euribortracker/env` (lines like
`EURIBORTRACKER_PROVIDER_URL=https://example.com`). The data directory is owned by
the service user and is never touched by re-installs.

> Note: `make update` re-copies the app source from the repo you run it in and
> overwrites manual edits made directly under `/opt/euribortracker`. Keep any
> tweaks in `/etc/euribortracker/env` instead.