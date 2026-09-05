from __future__ import annotations

from datetime import date, datetime

from app.models import EuriborFixing, MortgageConfig, Tenor
from app.repositories import EuriborRepository
from app.services.mortgage import MortgageService


def fixing(day: date, rate: float, tenor: Tenor = Tenor.M6) -> EuriborFixing:
    return EuriborFixing(
        tenor=tenor,
        date=day,
        rate=rate,
        source="test",
        source_url="http://test",
        retrieved_at=datetime(2026, 1, 1),
    )


class TestOverview:
    def test_unconfigured_mortgage(self, db):
        repo = EuriborRepository(db)
        service = MortgageService(repo)
        cfg = MortgageConfig()
        overview = service.overview(cfg, as_of=date(2026, 9, 4))
        assert overview["configured"] is False
        assert overview["estimate"] is True

    def test_configured_mortgage_full_picture(self, db):
        repo = EuriborRepository(db)
        repo.insert_fixings(
            [
                fixing(date(2026, 3, 2), 2.131),  # reference date for Apr-1 revision
                fixing(date(2026, 9, 2), 2.770),
                fixing(date(2026, 9, 3), 2.789),  # latest
            ]
        )
        service = MortgageService(repo)
        cfg = MortgageConfig(
            outstanding_principal=150000.0,
            end_date=date(2046, 1, 1),
            tenor=Tenor.M6,
            spread=0.80,
            revision_frequency_months=6,
            next_revision_date=date(2026, 10, 1),
            current_nominal_rate=2.90,
        )
        overview = service.overview(cfg, as_of=date(2026, 9, 4))
        assert overview["current_euribor"] == 2.789
        assert overview["estimated_nominal_rate"] == pytest.approx(3.589, abs=0.001)
        # reference date = 6 months before 2026-10-01 -> 2026-04-01, rate from 2026-03-02
        assert overview["current_period_euribor"] == 2.131
        assert overview["current_period_applied_rate"] == pytest.approx(2.931, abs=0.001)
        assert overview["estimated_next_nominal_rate"] == pytest.approx(3.589, abs=0.001)
        assert overview["estimated_next_change_pp"] == pytest.approx(0.689, abs=0.001)
        assert overview["months_remaining"] == 232
        payment = overview["estimated_monthly_payment"]
        assert payment == pytest.approx(897.5, abs=5.0)

    def test_simulate_scenarios(self, db):
        repo = EuriborRepository(db)
        service = MortgageService(repo)
        cfg = MortgageConfig(
            outstanding_principal=200000.0,
            end_date=date(2046, 1, 1),
            spread=0.80,
        )
        rows = service.simulate(cfg, [1.5, 2.0, 2.5, 3.0, 4.0])
        assert len(rows) == 5
        assert [r["spread"] for r in rows] == [0.8] * 5
        assert [r["nominal_rate"] for r in rows] == [2.3, 2.8, 3.3, 3.8, 4.8]
        # higher rate -> higher payment, monotonic
        payments = [r["monthly_payment"] for r in rows]
        assert all(b > a for a, b in zip(payments, payments[1:], strict=False))


import pytest  # noqa: E402
