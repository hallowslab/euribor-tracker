from __future__ import annotations

from datetime import date

import pytest

from app.models import MortgageConfig
from app.services.mortgage import MortgageCalculator, MortgageService


class TestMonthlyPayment:
    def test_zero_rate_degrades_to_principal_instalments(self):
        assert MortgageCalculator.monthly_payment(120000, 0.0, 120) == pytest.approx(1000.0)

    def test_negative_nominal_rate_same_instalments(self):
        assert MortgageCalculator.monthly_payment(120000, -1.0, 120) == pytest.approx(1000.0)

    def test_known_annuity_value(self):
        # 200k at 3.0% p.a. nominal over 240 months
        payment = MortgageCalculator.monthly_payment(200000, 3.0, 240)
        assert payment == pytest.approx(1109.20, abs=0.01)

    def test_known_annuity_value_second(self):
        # 150k at 2.9% over 300 months
        payment = MortgageCalculator.monthly_payment(150000, 2.9, 300)
        assert payment == pytest.approx(703.54, abs=0.01)

    def test_zero_months(self):
        assert MortgageCalculator.monthly_payment(100000, 3.0, 0) == 0.0


class TestNominalRate:
    def test_euribor_plus_spread(self):
        assert MortgageCalculator.nominal_rate(2.10, 0.80) == pytest.approx(2.90)

    def test_negative_euribor(self):
        assert MortgageCalculator.nominal_rate(-0.5, 0.9) == pytest.approx(0.4)


class TestMonthsRemaining:
    def test_term_from_dates(self):
        assert MortgageCalculator.months_between(date(2026, 1, 1), date(2036, 1, 1)) == 120

    def test_negative_term_clamped_to_zero(self):
        cfg = MortgageConfig(end_date=date(2020, 1, 1))
        assert MortgageService.__new__(MortgageService).months_remaining(cfg, as_of=date(2026, 1, 1)) == 0


class TestRevisionReferenceDate:
    def test_six_month_revision(self):
        service = MortgageService.__new__(MortgageService)
        cfg = MortgageConfig(next_revision_date=date(2026, 10, 1), revision_frequency_months=6)
        assert service._revision_reference_date(cfg) == date(2026, 4, 1)

    def test_six_month_revision_crossing_year(self):
        service = MortgageService.__new__(MortgageService)
        cfg = MortgageConfig(next_revision_date=date(2026, 3, 15), revision_frequency_months=6)
        assert service._revision_reference_date(cfg) == date(2025, 9, 15)

    def test_three_month_revision(self):
        service = MortgageService.__new__(MortgageService)
        cfg = MortgageConfig(next_revision_date=date(2026, 1, 10), revision_frequency_months=3)
        assert service._revision_reference_date(cfg) == date(2025, 10, 10)
