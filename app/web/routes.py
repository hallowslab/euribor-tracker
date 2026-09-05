from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..models import SUPPORTED_TENORS, MortgageConfig, Tenor, parse_tenor
from ..services.rates import PERIODS

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

PERIOD_LABELS = {
    "1m": "1 month",
    "3m": "3 months",
    "6m": "6 months",
    "1y": "1 year",
    "2y": "2 years",
    "5y": "5 years",
    "10y": "10 years",
    "all": "All history",
}


def _pick_tenor(request: Request, raw: str | None) -> Tenor:
    try:
        return parse_tenor(raw) if raw else Tenor(request.app.state.settings.default_tenor)
    except ValueError:
        return Tenor(request.app.state.settings.default_tenor)


@router.get("/")
def dashboard(request: Request, tenor: str | None = None):
    state = request.app.state
    t = _pick_tenor(request, tenor)
    config = state.configs.get_mortgage()
    latest = state.rates.latest(t)
    stats = state.rates.stats(t, "1y")
    chart_end = date.today()
    chart_start = chart_end - timedelta(days=PERIODS["2y"])
    chart = state.rates.series(t, chart_start, chart_end)
    mortgage = state.mortgage.overview(config) if config else None
    revision_days = None
    if config and config.next_revision_date:
        revision_days = (config.next_revision_date - date.today()).days
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "tenors": list(SUPPORTED_TENORS),
            "selected_tenor": t,
            "latest": latest,
            "stats": stats,
            "chart_data": chart,
            "mortgage": mortgage,
            "config": config,
            "revision_days": revision_days,
            "page": "dashboard",
        },
    )


@router.get("/history")
def history(request: Request, tenor: str | None = None, period: str = "all"):
    state = request.app.state
    t = _pick_tenor(request, tenor)
    if period not in PERIODS:
        period = "all"
    stats = state.rates.stats(t, period)
    end = date.today()
    start = date.fromisoformat(stats["start_date"]) if not stats.get("empty") else end
    chart = state.rates.series(t, start, end)
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "tenors": list(SUPPORTED_TENORS),
            "selected_tenor": t,
            "period": period,
            "period_labels": PERIOD_LABELS,
            "stats": stats,
            "chart_data": chart,
            "page": "history",
        },
    )


@router.get("/mortgage")
def mortgage_page(request: Request):
    config = request.app.state.configs.get_mortgage()
    return templates.TemplateResponse(
        request,
        "mortgage.html",
        {
            "tenors": list(SUPPORTED_TENORS),
            "config": config,
            "page": "mortgage",
        },
    )


@router.post("/mortgage")
def mortgage_save(
    request: Request,
    outstanding_principal: float = Form(default=None),
    original_amount: float = Form(default=None),
    start_date: str = Form(default=None),
    end_date: str = Form(default=None),
    term_years: int = Form(default=None),
    tenor: str = Form("6M"),
    spread: float = Form(default=None),
    revision_frequency_months: int = Form(6),
    next_revision_date: str = Form(default=None),
    current_nominal_rate: float = Form(default=None),
    fixed_rate_period_end: str = Form(default=None),
):
    def _date(value: str):
        return date.fromisoformat(value) if value else None

    config = MortgageConfig(
        original_amount=original_amount,
        outstanding_principal=outstanding_principal,
        start_date=_date(start_date),
        end_date=_date(end_date),
        term_years=term_years,
        tenor=parse_tenor(tenor),
        spread=spread,
        revision_frequency_months=revision_frequency_months,
        next_revision_date=_date(next_revision_date),
        current_nominal_rate=current_nominal_rate,
        fixed_rate_period_end=_date(fixed_rate_period_end),
    )
    request.app.state.configs.save_mortgage(config)
    return RedirectResponse("/?tenor=" + config.tenor.value, status_code=303)


@router.get("/alerts")
def alerts_page(request: Request):
    alerts = request.app.state.alert_repo.list_alerts()
    return templates.TemplateResponse(
        request,
        "alerts.html",
        {
            "tenors": list(SUPPORTED_TENORS),
            "alerts": alerts,
            "page": "alerts",
        },
    )
