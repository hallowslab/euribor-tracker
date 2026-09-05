from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ..models import Tenor


@dataclass(frozen=True)
class ProviderFixing:
    tenor: Tenor
    date: date  # fixing/publication date
    rate: float  # percent per annum
    source: str
    source_url: str


class EuriborProvider(Protocol):
    """Contract for any external Euribor data provider.

    The rest of the application must not know whether the provider talks to a
    REST API, parses JSON/HTML, or scrapes a website. Providers are the only
    component that knows how to obtain raw fixings from the outside world.
    """

    name: str
    source_label: str

    def get_available_tenors(self) -> list[Tenor]: ...

    def get_fixings(
        self, tenor: Tenor, start: date | None = None, end: date | None = None
    ) -> list[ProviderFixing]: ...

    def get_latest(self, tenor: Tenor) -> ProviderFixing | None: ...

    def get_last_available_date(self, tenor: Tenor) -> date | None: ...
