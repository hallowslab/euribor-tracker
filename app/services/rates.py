from __future__ import annotations

from datetime import date, timedelta

from ..models import Tenor
from ..repositories import EuriborRepository

# Display periods in days. None = full available history.
PERIODS: dict[str, int | None] = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "all": None,
}


def change_in_pp(new_rate: float, old_rate: float) -> float:
    """Difference between two rates expressed in percentage points."""
    return new_rate - old_rate


def relative_change_pct(new_rate: float, old_rate: float) -> float | None:
    """Relative change between two rates expressed as a percentage.

    Returns None when the baseline rate is zero (division undefined).
    Example: 2.50 -> 2.10 is a relative decrease of 16% (i.e. -16.0).
    """
    if old_rate == 0:
        return None
    return (new_rate - old_rate) / old_rate * 100


def most_recent_weekday(day: date) -> date:
    """Most recent Monday-Friday on or before `day`.

    Euribor is fixed on TARGET business days. Weekends never have a fixing;
    this helper is used to detect when the latest stored fixing is stale.
    (European holidays are not hardcoded here: their absence is visible as a
    gap in the observed fixing data itself.)
    """
    current = day
    while current.weekday() >= 5:  # Saturday=5, Sunday=6
        current -= timedelta(days=1)
    return current


class RatesService:
    def __init__(self, repository: EuriborRepository):
        self.repo = repository

    def latest(self, tenor: Tenor) -> dict | None:
        latest = self.repo.get_latest(tenor)
        if latest is None:
            return None
        previous = self.repo.get_previous(tenor, latest.date)
        today = date.today()
        expected = most_recent_weekday(today)
        return {
            "tenor": tenor.value,
            "rate": latest.rate,
            "fixing_date": latest.date.isoformat(),
            "source": latest.source,
            "source_url": latest.source_url,
            "previous_rate": previous.rate if previous else None,
            "previous_date": previous.date.isoformat() if previous else None,
            "change_pp": (
                change_in_pp(latest.rate, previous.rate) if previous else None
            ),
            "change_pct": (
                relative_change_pct(latest.rate, previous.rate) if previous else None
            ),
            "days_since_fixing": (today - latest.date).days,
            "is_stale": latest.date < expected,
            "expected_publication_date": expected.isoformat(),
            "retrieved_at": latest.retrieved_at.isoformat(timespec="seconds"),
        }

    def series(self, tenor: Tenor, start: date, end: date) -> list[dict]:
        fixings = self.repo.get_range(tenor, start, end)
        return [
            {"date": f.date.isoformat(), "rate": f.rate, "source": f.source}
            for f in fixings
        ]

    def stats(self, tenor: Tenor, period: str = "all") -> dict:
        days = PERIODS.get(period)
        if days is None:
            start = self.repo.get_first_date(tenor)
        else:
            start = date.today() - timedelta(days=days)
        if start is None:
            return {"tenor": tenor.value, "period": period, "empty": True}
        end = date.today()
        fixings = self.repo.get_range(tenor, start, end)
        if not fixings:
            return {"tenor": tenor.value, "period": period, "empty": True}
        rates = [f.rate for f in fixings]
        latest = fixings[-1]
        previous_publication = fixings[-2] if len(fixings) > 1 else None
        period_start = fixings[0]

        deltas = {}
        for label, span in PERIODS.items():
            if span is None:
                continue
            anchor_date = end - timedelta(days=span)
            anchor = self._fixing_on_or_before(tenor, anchor_date)
            if anchor:
                deltas[label] = {
                    "anchor_date": anchor.date.isoformat(),
                    "anchor_rate": anchor.rate,
                    "change_pp": change_in_pp(latest.rate, anchor.rate),
                    "change_pct": relative_change_pct(latest.rate, anchor.rate),
                }

        return {
            "tenor": tenor.value,
            "period": period,
            "empty": False,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "count": len(fixings),
            "latest_rate": latest.rate,
            "latest_date": latest.date.isoformat(),
            "previous_rate": previous_publication.rate if previous_publication else None,
            "previous_date": previous_publication.date.isoformat() if previous_publication else None,
            "change_from_previous_pp": (
                change_in_pp(latest.rate, previous_publication.rate)
                if previous_publication
                else None
            ),
            "period_start_rate": period_start.rate,
            "period_start_date": period_start.date.isoformat(),
            "change_over_period_pp": change_in_pp(latest.rate, period_start.rate),
            "change_over_period_pct": relative_change_pct(latest.rate, period_start.rate),
            "min_rate": min(rates),
            "max_rate": max(rates),
            "avg_rate": sum(rates) / len(rates),
            "deltas": deltas,
        }

    def _fixing_on_or_before(self, tenor: Tenor, day: date):
        return self.repo.get_latest_on_or_before(tenor, day)

    def coverage(self) -> dict:
        tenors = []
        for tenor in sorted(self.repo.stored_tenors(), key=lambda t: t.value):
            first = self.repo.get_first_date(tenor)
            last = self.repo.get_last_date(tenor)
            tenors.append(
                {
                    "tenor": tenor.value,
                    "count": self.repo.count(tenor),
                    "first_date": first.isoformat() if first else None,
                    "last_date": last.isoformat() if last else None,
                }
            )
        return {"tenors": tenors, "anomalies": self.repo.get_anomalies()}
