from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..models import MortgageConfig, parse_tenor

router = APIRouter(prefix="/api/mortgage", tags=["mortgage"])


class MortgageConfigIn(BaseModel):
    original_amount: float | None = None
    outstanding_principal: float | None = Field(default=None, ge=0)
    start_date: date | None = None
    end_date: date | None = None
    term_years: int | None = Field(default=None, ge=1)
    tenor: str = "6M"
    spread: float | None = Field(default=None, ge=0, le=20)
    revision_frequency_months: int = Field(default=6, ge=1, le=24)
    next_revision_date: date | None = None
    current_nominal_rate: float | None = Field(default=None, ge=-5, le=50)
    fixed_rate_period_end: date | None = None


@router.get("/config")
def get_config(request: Request):
    config = request.app.state.configs.get_mortgage()
    if config is None:
        return {"configured": False, "mortgage": None}
    return {"configured": True, "mortgage": _to_dict(config)}


@router.put("/config")
def put_config(request: Request, payload: MortgageConfigIn):
    config = MortgageConfig(
        original_amount=payload.original_amount,
        outstanding_principal=payload.outstanding_principal,
        start_date=payload.start_date,
        end_date=payload.end_date,
        term_years=payload.term_years,
        tenor=parse_tenor(payload.tenor),
        spread=payload.spread,
        revision_frequency_months=payload.revision_frequency_months,
        next_revision_date=payload.next_revision_date,
        current_nominal_rate=payload.current_nominal_rate,
        fixed_rate_period_end=payload.fixed_rate_period_end,
    )
    request.app.state.configs.save_mortgage(config)
    return {"configured": True, "mortgage": _to_dict(config)}


@router.get("/overview")
def overview(request: Request, as_of: date | None = Query(default=None)):
    config = request.app.state.configs.get_mortgage()
    if config is None:
        return {"configured": False, "overview": None}
    return {"configured": True, "overview": request.app.state.mortgage.overview(config, as_of)}


@router.get("/simulate")
def simulate(
    request: Request,
    euribor: str = Query(..., description="Comma-separated Euribor scenario rates, e.g. 1.5,2.0,3.0"),
):
    config = request.app.state.configs.get_mortgage()
    if config is None or not config.is_configured():
        raise HTTPException(status_code=400, detail="Mortgage not configured")
    scenarios = [float(x.strip().replace("%", "")) for x in euribor.split(",") if x.strip()]
    return {"rows": request.app.state.mortgage.simulate(config, scenarios)}


def _to_dict(config: MortgageConfig) -> dict:
    data = {
        "original_amount": config.original_amount,
        "outstanding_principal": config.outstanding_principal,
        "start_date": config.start_date.isoformat() if config.start_date else None,
        "end_date": config.end_date.isoformat() if config.end_date else None,
        "term_years": config.term_years,
        "tenor": config.tenor.value,
        "spread": config.spread,
        "revision_frequency_months": config.revision_frequency_months,
        "next_revision_date": config.next_revision_date.isoformat() if config.next_revision_date else None,
        "current_nominal_rate": config.current_nominal_rate,
        "fixed_rate_period_end": config.fixed_rate_period_end.isoformat()
        if config.fixed_rate_period_end
        else None,
    }
    return data
