from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import parse_tenor
from ..services.alerts import AlertService

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertIn(BaseModel):
    type: str
    tenor: str = "6M"
    threshold: float | None = None
    threshold_pp: float | None = Field(default=None, ge=0)
    next_revision_date: str | None = None
    days_ahead: int | None = Field(default=30, ge=1)


@router.get("")
def list_alerts(request: Request):
    alerts = request.app.state.alert_repo.list_alerts()
    return {"alerts": alerts, "types": list(AlertService.ALERT_TYPES)}


@router.post("")
def create_alert(request: Request, payload: AlertIn):
    if payload.type not in AlertService.ALERT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown alert type: {payload.type}")
    parse_tenor(payload.tenor)
    params = {
        "threshold": payload.threshold,
        "threshold_pp": payload.threshold_pp,
        "next_revision_date": payload.next_revision_date,
        "days_ahead": payload.days_ahead,
    }
    alert_id = request.app.state.alert_repo.create_alert(payload.type, payload.tenor.upper(), params)
    return {"id": alert_id}


@router.delete("/{alert_id}")
def delete_alert(request: Request, alert_id: int):
    request.app.state.alert_repo.delete_alert(alert_id)
    return {"deleted": alert_id}


@router.post("/evaluate")
def evaluate(request: Request):
    triggered = request.app.state.alerts.evaluate()
    return {"triggered": triggered, "channels": list(request.app.state.alert_channels.keys())}
