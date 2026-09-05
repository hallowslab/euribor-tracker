from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import alerts as alerts_api
from .api import mortgage as mortgage_api
from .api import rates as rates_api
from .config import Settings, load_settings
from .db import Database
from .providers.euriborrates import EuriborRatesComProvider
from .repositories import AlertRepository, ConfigRepository, EuriborRepository
from .services.alerts import CHANNELS, AlertService
from .services.importer import EuriborImporter
from .services.mortgage import MortgageService
from .services.rates import RatesService
from .web import routes as web_routes

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.database_path)
    db.init_schema()

    repository = EuriborRepository(db)
    config_repo = ConfigRepository(db)
    alert_repo = AlertRepository(db)
    rates = RatesService(repository)
    mortgage = MortgageService(repository)
    alerts = AlertService(repository, alert_repo)
    provider = EuriborRatesComProvider(settings)
    importer = EuriborImporter(provider, repository, settings)

    app = FastAPI(title="Euribor Tracker", version="0.1.0")
    app.state.settings = settings
    app.state.db = db
    app.state.repo = repository
    app.state.configs = config_repo
    app.state.alert_repo = alert_repo
    app.state.rates = rates
    app.state.mortgage = mortgage
    app.state.alerts = alerts
    app.state.provider = provider
    app.state.importer = importer
    app.state.alert_channels = dict(CHANNELS)

    app.include_router(rates_api.router)
    app.include_router(mortgage_api.router)
    app.include_router(alerts_api.router)
    app.include_router(web_routes.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
