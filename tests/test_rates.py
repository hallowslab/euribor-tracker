from __future__ import annotations

from datetime import date, datetime

from app.models import EuriborFixing, Tenor
from app.services.rates import (
    RatesService,
    change_in_pp,
    most_recent_weekday,
    relative_change_pct,
)


def fixing(day: date, rate: float, tenor: Tenor = Tenor.M6) -> EuriborFixing:
    return EuriborFixing(
        tenor=tenor,
        date=day,
        rate=rate,
        source="test",
        source_url="http://test",
        retrieved_at=datetime(2026, 1, 1),
    )


class TestChangeUnits:
    def test_percentage_points(self):
        assert change_in_pp(2.10, 2.50) == pytest_approx(-0.40)

    def test_relative_change_pct(self):
        assert relative_change_pct(2.10, 2.50) == pytest_approx(-16.0)

    def test_relative_change_zero_baseline_is_none(self):
        assert relative_change_pct(0.5, 0.0) is None


class TestWeekdayHelper:
    def test_saturday_rolls_back(self):
        assert most_recent_weekday(date(2026, 9, 5)) == date(2026, 9, 4)  # Sat -> Fri

    def test_sunday_rolls_back(self):
        assert most_recent_weekday(date(2026, 9, 6)) == date(2026, 9, 4)  # Sun -> Fri

    def test_weekday_unchanged(self):
        assert most_recent_weekday(date(2026, 9, 3)) == date(2026, 9, 3)


class TestStats:
    def test_stats_over_weekend_gaps(self, db):
        from app.repositories import EuriborRepository

        repo = EuriborRepository(db)
        repo.insert_fixings(
            [
                fixing(date(2026, 8, 27), 2.746),
                fixing(date(2026, 8, 28), 2.762),
                fixing(date(2026, 8, 31), 2.770),
                fixing(date(2026, 9, 1), 2.779),
                fixing(date(2026, 9, 2), 2.770),
                fixing(date(2026, 9, 3), 2.789),
            ]
        )
        service = RatesService(repo)
        stats = service.stats(Tenor.M6, "1m")
        assert stats["empty"] is False
        assert stats["latest_rate"] == 2.789
        assert stats["previous_rate"] == 2.770
        assert stats["change_from_previous_pp"] == pytest_approx(0.019)
        assert stats["min_rate"] == 2.746
        assert stats["max_rate"] == 2.789
        assert stats["avg_rate"] == pytest_approx((2.746 + 2.762 + 2.770 + 2.779 + 2.770 + 2.789) / 6)
        assert stats["change_over_period_pp"] == pytest_approx(2.789 - 2.746)

    def test_latest_stale_flag(self, db):
        from app.repositories import EuriborRepository

        repo = EuriborRepository(db)
        repo.insert_fixings([fixing(date(2026, 8, 28), 2.762)])
        service = RatesService(repo)
        latest = service.latest(Tenor.M6)
        # 2026-09-04 is a Friday; a fixing from Aug 28 is stale
        assert latest["is_stale"] is True
        assert latest["days_since_fixing"] >= 7


def pytest_approx(value):
    return pytest.approx(value, abs=1e-6)


import pytest  # noqa: E402
