from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Tenor(StrEnum):
    """Euribor maturities supported by the application."""

    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    M12 = "12M"

    @property
    def months(self) -> int:
        return int(self.value[:-1])

    @property
    def label(self) -> str:
        return f"Euribor {self.months} month" + ("s" if self.months > 1 else "")

    @property
    def short_label(self) -> str:
        return f"{self.value} Euribor"


SUPPORTED_TENORS: tuple[Tenor, ...] = (Tenor.M1, Tenor.M3, Tenor.M6, Tenor.M12)


def parse_tenor(value: str) -> Tenor:
    try:
        return Tenor(value.strip().upper())
    except ValueError as exc:
        raise ValueError(f"Unsupported Euribor tenor: {value!r}") from exc


@dataclass(frozen=True)
class EuriborFixing:
    """A single observed Euribor fixing.

    `date` is the fixing/publication date (the date the rate belongs to),
    NOT the date the value was retrieved by this application.
    """

    tenor: Tenor
    date: date
    rate: float  # percent per annum, e.g. 2.789 means 2.789%
    source: str
    source_url: str
    retrieved_at: datetime


@dataclass(frozen=True)
class MortgageConfig:
    """User mortgage configuration. All fields optional until entered."""

    original_amount: float | None = None
    outstanding_principal: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    term_years: int | None = None
    tenor: Tenor = Tenor.M6
    spread: float | None = None  # bank margin, percent points, e.g. 0.80
    revision_frequency_months: int = 6
    next_revision_date: date | None = None
    current_nominal_rate: float | None = None
    fixed_rate_period_end: date | None = None

    def is_configured(self) -> bool:
        return self.outstanding_principal is not None and self.spread is not None
