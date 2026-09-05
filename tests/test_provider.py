from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.config import Settings
from app.models import Tenor
from app.providers.euriborrates import EuriborRatesComProvider

TENOR = Tenor.M6

DAILY_TABLE = """
<html><body>
<table class="w-full">
  <caption class="sr-only">Daily Euribor fixings in 2026</caption>
  <thead><tr><th>Date</th><th>6m</th></tr></thead>
  <tbody>
    <tr><th><time datetime="2026-01-02">January 2, 2026</time></th><td>2.105%</td></tr>
    <tr><th><time datetime="2026-01-05">January 5, 2026</time></th><td>2.112%</td></tr>
    <tr><th><time datetime="2026-01-06">January 6, 2026</time></th><td>-0.554%</td></tr>
    <tr><th><time datetime="2026-01-07">January 7, 2026</time></th><td>2.121%</td></tr>
  </tbody>
</table>
</body></html>
"""


def make_provider(handler) -> EuriborRatesComProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "test"},
        follow_redirects=True,
    )
    return EuriborRatesComProvider(Settings(provider_base_url="https://example.com"), client=client)


class TestParsing:
    def test_parses_daily_table(self):
        def handler(request):
            assert "?term=6m" in str(request.url)
            return httpx.Response(200, text=DAILY_TABLE)

        provider = make_provider(handler)
        fixings = provider._parse_daily_table(DAILY_TABLE, "https://example.com/x", TENOR, 2026)
        assert len(fixings) == 4
        assert fixings[0].date == date(2026, 1, 2)
        assert fixings[0].rate == 2.105
        assert fixings[1].date == date(2026, 1, 5)  # weekend absent: no 2026-01-03/04
        assert fixings[2].rate == -0.554  # negative rate
        assert fixings[0].source_url == "https://example.com/x"
        assert fixings[0].tenor == TENOR
        assert "aggregator" in fixings[0].source

    def test_missing_daily_table_raises(self):
        provider = make_provider(lambda r: httpx.Response(200, text="<html><body>no table</body></html>"))
        with pytest.raises(ValueError):
            provider._parse_daily_table("<html><body>no table</body></html>", "u", TENOR, 2026)

    def test_bad_rate_raises(self):
        bad = DAILY_TABLE.replace("2.105%", "oops")
        provider = make_provider(lambda r: httpx.Response(200, text=bad))
        with pytest.raises(ValueError):
            provider._parse_daily_table(bad, "u", TENOR, 2026)


class TestRange:
    def test_get_fixings_filters_dates_and_term(self):
        urls = {}

        def handler(request):
            urls[str(request.url)] = True
            return httpx.Response(200, text=DAILY_TABLE)

        provider = make_provider(handler)
        fixings = provider.get_fixings(TENOR, date(2026, 1, 5), date(2026, 1, 31))
        assert [f.date for f in fixings] == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
        assert any("?term=6m" in u for u in urls)

    def test_get_latest_returns_most_recent(self):
        def handler(request):
            return httpx.Response(200, text=DAILY_TABLE)

        provider = make_provider(handler)
        latest = provider.get_latest(TENOR)
        assert latest.date == date(2026, 1, 7)
        assert latest.rate == 2.121

    def test_available_tenors(self):
        provider = make_provider(lambda r: httpx.Response(200, text=DAILY_TABLE))
        assert {t.value for t in provider.get_available_tenors()} == {"1M", "3M", "6M", "12M"}
