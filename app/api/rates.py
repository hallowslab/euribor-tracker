from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import SUPPORTED_TENORS, parse_tenor

router = APIRouter(prefix="/api/rates", tags=["rates"])


@router.get("/{tenor}/latest")
def latest(request: Request, tenor: str):
    t = parse_tenor(tenor)
    data = request.app.state.rates.latest(t)
    if data is None:
        raise HTTPException(status_code=404, detail="No Euribor data stored for this tenor")
    return data


@router.get("/{tenor}/series")
def series(
    request: Request,
    tenor: str,
    start: date = Query(default=None),
    end: date = Query(default=None),
):
    t = parse_tenor(tenor)
    end = end or date.today()
    start = start or (request.app.state.rates.repo.get_first_date(t) or end)
    return {
        "tenor": t.value,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "points": request.app.state.rates.series(t, start, end),
    }


@router.get("/{tenor}/stats")
def stats(request: Request, tenor: str, period: str = Query("all")):
    t = parse_tenor(tenor)
    if period not in ("all", "1m", "3m", "6m", "1y", "2y", "5y", "10y"):
        raise HTTPException(status_code=400, detail=f"Invalid period: {period}")
    return request.app.state.rates.stats(t, period)


@router.get("/meta")
def meta(request: Request):
    return {
        "tenors": [t.value for t in SUPPORTED_TENORS],
        "default_tenor": request.app.state.settings.default_tenor,
        "coverage": request.app.state.rates.coverage(),
        "last_import": request.app.state.db.meta_get("last_import"),
    }
