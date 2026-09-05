from __future__ import annotations

from datetime import date

from ..models import MortgageConfig
from ..repositories import EuriborRepository


class MortgageCalculator:
    """Pure mortgage math. No I/O; all inputs passed explicitly."""

    @staticmethod
    def nominal_rate(euribor_rate: float, spread: float) -> float:
        """Total mortgage interest rate = Euribor + bank spread (percentage points)."""
        return euribor_rate + spread

    @staticmethod
    def monthly_payment(
        principal: float, annual_nominal_rate_pct: float, months_remaining: int
    ) -> float:
        """Equal-instalment (French amortisation) monthly payment.

        When the annual nominal rate is zero or negative, the payment degrades
        to principal / months (no interest). This can occur when Euribor is
        negative and only partially offset by the spread.
        """
        if months_remaining <= 0:
            return 0.0
        monthly_rate = annual_nominal_rate_pct / 100.0 / 12.0
        if monthly_rate <= 0:
            return principal / months_remaining
        factor = (1 + monthly_rate) ** months_remaining
        return principal * monthly_rate * factor / (factor - 1)

    @staticmethod
    def months_between(start: date, end: date) -> int:
        """Whole calendar months between two dates (used for remaining term)."""
        return (end.year - start.year) * 12 + (end.month - start.month)


class MortgageService:
    """Mortgage estimation built on top of observed Euribor data.

    All revision/payment figures are ESTIMATES unless the user has entered the
    exact contractual calculation rules of their specific mortgage.
    """

    def __init__(self, repository: EuriborRepository):
        self.repo = repository

    def overview(self, config: MortgageConfig, as_of: date | None = None) -> dict:
        as_of = as_of or date.today()
        latest = self.repo.get_latest(config.tenor)
        result: dict = {
            "configured": config.is_configured(),
            "tenor": config.tenor.value,
            "spread": config.spread,
            "revision_frequency_months": config.revision_frequency_months,
            "estimate": True,
            "note": (
                "Estimated figure. The rate actually applied by the bank may "
                "depend on the exact contractual rules of the mortgage."
            ),
        }

        if latest:
            result["current_euribor"] = latest.rate
            result["current_euribor_date"] = latest.date.isoformat()
            result["current_euribor_source"] = latest.source
            if config.spread is not None:
                result["estimated_nominal_rate"] = MortgageCalculator.nominal_rate(
                    latest.rate, config.spread
                )

        if config.current_nominal_rate is not None:
            result["current_nominal_rate"] = config.current_nominal_rate

        if config.next_revision_date:
            result["next_revision_date"] = config.next_revision_date.isoformat()
            result["days_until_revision"] = (config.next_revision_date - as_of).days

        if config.spread is not None and config.next_revision_date:
            reference_date = self._revision_reference_date(config)
            result["current_period_reference_date"] = reference_date.isoformat()
            reference_fixing = self.repo.get_latest_on_or_before(config.tenor, reference_date)
            if reference_fixing:
                result["current_period_euribor"] = reference_fixing.rate
                result["current_period_euribor_date"] = reference_fixing.date.isoformat()
                result["current_period_applied_rate"] = MortgageCalculator.nominal_rate(
                    reference_fixing.rate, config.spread
                )
                if config.current_nominal_rate is not None:
                    result["current_period_applied_rate_match"] = (
                        abs(
                            result["current_period_applied_rate"]
                            - config.current_nominal_rate
                        )
                        < 0.005
                    )
            if latest and config.current_nominal_rate is not None:
                result["estimated_next_nominal_rate"] = MortgageCalculator.nominal_rate(
                    latest.rate, config.spread
                )
                result["estimated_next_change_pp"] = (
                    result["estimated_next_nominal_rate"] - config.current_nominal_rate
                )

        months = self.months_remaining(config, as_of)
        if months is not None:
            result["months_remaining"] = months
        if config.is_configured() and months and latest and config.spread is not None:
            rate = MortgageCalculator.nominal_rate(latest.rate, config.spread)
            result["estimated_monthly_payment"] = MortgageCalculator.monthly_payment(
                config.outstanding_principal, rate, months
            )
            result["estimated_payment_rate"] = rate
            if config.current_nominal_rate is not None:
                result["current_monthly_payment"] = MortgageCalculator.monthly_payment(
                    config.outstanding_principal, config.current_nominal_rate, months
                )
                result["estimated_payment_change_eur"] = (
                    result["estimated_monthly_payment"]
                    - result["current_monthly_payment"]
                )
        return result

    def simulate(self, config: MortgageConfig, euribor_scenarios: list[float]) -> list[dict]:
        months = self.months_remaining(config)
        if months is None or config.outstanding_principal is None:
            return []
        rows = []
        for euribor in euribor_scenarios:
            nominal = MortgageCalculator.nominal_rate(euribor, config.spread or 0.0)
            payment = MortgageCalculator.monthly_payment(
                config.outstanding_principal, nominal, months
            )
            rows.append(
                {
                    "euribor": euribor,
                    "spread": config.spread,
                    "nominal_rate": nominal,
                    "monthly_payment": payment,
                }
            )
        return rows

    def months_remaining(self, config: MortgageConfig, as_of: date | None = None) -> int | None:
        as_of = as_of or date.today()
        if config.end_date:
            return max(MortgageCalculator.months_between(as_of, config.end_date), 0)
        if config.term_years and config.start_date:
            end = date(
                config.start_date.year + config.term_years,
                config.start_date.month,
                config.start_date.day,
            )
            return max(MortgageCalculator.months_between(as_of, end), 0)
        return None

    def _revision_reference_date(self, config: MortgageConfig) -> date:
        """Date the current period's Euribor was (likely) fixed.

        Assumes the reference date is `revision_frequency_months` before the
        next revision date. This is an ESTIMATE of the common contractual
        convention, not a guaranteed rule.
        """
        if config.next_revision_date is None:
            raise ValueError("next_revision_date is required")
        year = config.next_revision_date.year
        month = config.next_revision_date.month - config.revision_frequency_months
        if month <= 0:
            year -= 1
            month += 12
        return date(year, month, config.next_revision_date.day)
