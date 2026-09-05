from __future__ import annotations

import logging
from datetime import date
from typing import Protocol

from ..models import Tenor
from ..repositories import AlertRepository, EuriborRepository
from .rates import change_in_pp

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def send(self, title: str, body: str) -> None: ...


class LogChannel:
    """Default channel: writes notifications to the application log.

    Additional channels (email, telegram, ...) can be registered later without
    changing alert evaluation logic.
    """

    name = "log"

    def send(self, title: str, body: str) -> None:
        logger.warning("ALERT [%s]: %s", title, body)


CHANNELS: dict[str, NotificationChannel] = {"log": LogChannel()}


class AlertService:
    ALERT_TYPES = ("below", "above", "change_pp_gt", "yearly_high", "yearly_low", "revision_soon")

    def __init__(self, repo: EuriborRepository, alert_repo: AlertRepository):
        self.repo = repo
        self.alert_repo = alert_repo

    def evaluate(self, today: date | None = None) -> list[dict]:
        """Evaluate all enabled alerts against current data. Returns triggered alerts."""
        today = today or date.today()
        triggered: list[dict] = []
        for alert in self.alert_repo.list_alerts():
            if not alert["enabled"]:
                continue
            result = self._evaluate_one(alert, today)
            if result:
                self.alert_repo.mark_triggered(alert["id"])
                triggered.append(result)
        return triggered

    def _evaluate_one(self, alert: dict, today: date) -> dict | None:
        alert_type = alert["type"]
        tenor = Tenor(alert["tenor"])
        params = alert["params"]
        latest = self.repo.get_latest(tenor)
        title = f"{tenor.value} Euribor alert"
        body = ""

        if latest is None:
            return None

        if alert_type == "below" or alert_type == "above":
            threshold = float(params["threshold"])
            hit = latest.rate < threshold if alert_type == "below" else latest.rate > threshold
            body = (
                f"Latest {tenor.value} Euribor is {latest.rate:.3f}% (fixed {latest.date}), "
                f"{'below' if alert_type == 'below' else 'above'} {threshold:.3f}%."
            )
        elif alert_type == "change_pp_gt":
            previous = self.repo.get_previous(tenor, latest.date)
            if previous is None:
                return None
            threshold = float(params["threshold_pp"])
            delta = change_in_pp(latest.rate, previous.rate)
            hit = abs(delta) > threshold
            body = f"{tenor.value} Euribor changed by {delta:+.3f} pp since previous fixing ({previous.date})."
        elif alert_type == "yearly_high":
            year_rates = self.repo.get_range(tenor, date(latest.date.year, 1, 1), latest.date)
            hit = latest.rate >= max(r.rate for r in year_rates)
            body = f"{tenor.value} Euribor reached {latest.rate:.3f}% — new yearly high for {latest.date.year}."
        elif alert_type == "yearly_low":
            year_rates = self.repo.get_range(tenor, date(latest.date.year, 1, 1), latest.date)
            hit = latest.rate <= min(r.rate for r in year_rates)
            body = f"{tenor.value} Euribor reached {latest.rate:.3f}% — new yearly low for {latest.date.year}."
        elif alert_type == "revision_soon":
            next_revision = params.get("next_revision_date")
            days_ahead = int(params.get("days_ahead", 30))
            if not next_revision:
                return None
            revision_date = date.fromisoformat(next_revision)
            days_left = (revision_date - today).days
            hit = 0 <= days_left <= days_ahead
            body = f"Mortgage revision in {days_left} days ({revision_date})."
        else:
            return None

        if not hit:
            return None
        for channel in CHANNELS.values():
            channel.send(title, body)
        return {"alert_id": alert["id"], "type": alert_type, "tenor": tenor.value, "title": title, "body": body}
