from __future__ import annotations

from datetime import date

import httpx
from bs4 import BeautifulSoup

from ..config import Settings
from ..models import SUPPORTED_TENORS, Tenor
from .base import ProviderFixing

TENOR_TERM_CODE: dict[Tenor, str] = {
    Tenor.M1: "1m",
    Tenor.M3: "3m",
    Tenor.M6: "6m",
    Tenor.M12: "12m",
}

DAILY_CAPTION_PREFIX = "Daily Euribor fixings"


class EuriborRatesComProvider:
    """Daily Euribor fixings from euriborrates.com.

    NOT the official publisher of Euribor. The official publisher is EMMI
    (European Money Markets Institute). euriborrates.com is an aggregator that
    publishes the official daily fixings as HTML tables on per-year pages.
    """

    name = "euriborrates.com"
    source_label = "euriborrates.com (aggregator of official EMMI daily Euribor fixings)"

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or Settings()
        self._http = client or httpx.Client(
            timeout=self.settings.provider_http_timeout,
            headers={"User-Agent": self.settings.user_agent},
            follow_redirects=True,
        )

    def get_available_tenors(self) -> list[Tenor]:
        return list(SUPPORTED_TENORS)

    def get_fixings(
        self, tenor: Tenor, start: date | None = None, end: date | None = None
    ) -> list[ProviderFixing]:
        if tenor not in TENOR_TERM_CODE:
            raise ValueError(f"Tenor not supported by {self.name}: {tenor.value}")
        end = end or date.today()
        start = start or date(self.settings.history_start_year, 1, 1)
        if end < start:
            return []
        fixings: list[ProviderFixing] = []
        for year in range(start.year, end.year + 1):
            year_fixings = self._fetch_year(tenor, year)
            for fixing in year_fixings:
                if start <= fixing.date <= end:
                    fixings.append(fixing)
        return fixings

    def get_latest(self, tenor: Tenor) -> ProviderFixing | None:
        today = date.today()
        for year in (today.year, today.year - 1):
            fixings = self._fetch_year(tenor, year)
            if fixings:
                return fixings[-1]
        return None

    def get_last_available_date(self, tenor: Tenor) -> date | None:
        latest = self.get_latest(tenor)
        return latest.date if latest else None

    def _fetch_year(self, tenor: Tenor, year: int) -> list[ProviderFixing]:
        term = TENOR_TERM_CODE[tenor]
        url = f"{self.settings.provider_base_url}/historical-euribor/{year}?term={term}"
        response = self._http.get(url)
        response.raise_for_status()
        return self._parse_daily_table(response.text, url, tenor, year)

    def _parse_daily_table(self, html: str, url: str, tenor: Tenor, year: int) -> list[ProviderFixing]:
        soup = BeautifulSoup(html, "html.parser")
        table = self._find_daily_table(soup, year)
        if table is None:
            raise ValueError(
                f"{self.name}: no daily fixings table found for {tenor.value} {year} at {url}"
            )
        fixings: list[ProviderFixing] = []
        for row in table.find_all("tr"):
            time_el = row.find("time")
            if time_el is None or "datetime" not in time_el.attrs:
                continue
            rate_cell = row.find("td")
            if rate_cell is None:
                continue
            fixing_date = date.fromisoformat(time_el["datetime"])
            rate = self._parse_rate(rate_cell.get_text(strip=True))
            fixings.append(
                ProviderFixing(
                    tenor=tenor,
                    date=fixing_date,
                    rate=rate,
                    source=self.source_label,
                    source_url=url,
                )
            )
        fixings.sort(key=lambda f: f.date)
        return fixings

    def _find_daily_table(self, soup: BeautifulSoup, year: int) -> object | None:
        for table in soup.find_all("table"):
            caption = table.find("caption")
            if caption and DAILY_CAPTION_PREFIX in caption.get_text():
                return table
        return None

    @staticmethod
    def _parse_rate(text: str) -> float:
        cleaned = text.strip().rstrip("%").replace("\u2212", "-").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError as exc:
            raise ValueError(f"Could not parse Euribor rate from {text!r}") from exc
