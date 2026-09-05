from __future__ import annotations

import click

from .config import load_settings
from .db import Database
from .main import create_app
from .models import SUPPORTED_TENORS, parse_tenor


@click.group()
def main() -> None:
    """Euribor Tracker CLI."""


@main.command()
def init_db() -> None:
    """Create the database schema if missing."""
    settings = load_settings()
    Database(settings.database_path).init_schema()
    click.echo(f"Database ready at {settings.database_path}")


def _tenors(tenors: str | None):
    if not tenors:
        return list(SUPPORTED_TENORS)
    return [parse_tenor(t) for t in tenors.split(",")]


@main.command()
@click.option("--year", type=int, default=None, help="Only import a single year.")
@click.option("--tenors", default=None, help="Comma-separated tenors (1M,3M,6M,12M). Default: all.")
def backfill(year: int | None, tenors: str | None) -> None:
    """Import full historical Euribor data (idempotent, safe to re-run)."""
    app = create_app(load_settings())
    if year is not None:
        report = app.state.importer.import_year(year, _tenors(tenors))
    else:
        report = app.state.importer.import_history(_tenors(tenors))
    click.echo(
        f"Done: inserted={report.inserted} duplicates={report.duplicates} conflicts={report.conflicts}"
    )


@main.command()
@click.option("--tenors", default=None, help="Comma-separated tenors (1M,3M,6M,12M). Default: all.")
def update(tenors: str | None) -> None:
    """Refresh the current year only (fast daily update)."""
    app = create_app(load_settings())
    report = app.state.importer.update(_tenors(tenors))
    click.echo(
        f"Done: inserted={report.inserted} duplicates={report.duplicates} conflicts={report.conflicts}"
    )


@main.command()
def coverage() -> None:
    """Show stored data coverage per tenor."""
    app = create_app(load_settings())
    coverage = app.state.rates.coverage()
    for t in coverage["tenors"]:
        click.echo(
            f"{t['tenor']}: {t['count']} fixings, "
            f"{t['first_date']} -> {t['last_date']}"
        )
    anomalies = coverage["anomalies"]
    if anomalies:
        click.echo(f"\n{len(anomalies)} anomaly/anomalies detected (see API /api/rates/meta).")


@main.command()
def evaluate_alerts() -> None:
    """Evaluate configured alerts and send notifications via active channels."""
    app = create_app(load_settings())
    triggered = app.state.alerts.evaluate()
    if triggered:
        for item in triggered:
            click.echo(f"Triggered [{item['tenor']} {item['type']}]: {item['body']}")
    else:
        click.echo("No alerts triggered.")


@main.command()
@click.option("--host", default="127.0.0.1", help="Bind host.")
@click.option("--port", default=8000, help="Bind port.")
@click.option("--reload/--no-reload", default=False, help="Auto-reload on code changes.")
def serve(host: str, port: int, reload: bool) -> None:
    """Run the web application."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
