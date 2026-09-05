from __future__ import annotations

from datetime import date

import pytest

from app.config import Settings
from app.models import Tenor
from app.providers.base import ProviderFixing
from app.repositories import EuriborRepository
from app.services.importer import EuriborImporter

DAILY = """
<html><body>
<table><caption class="sr-only">Daily Euribor fixings in 2026</caption>
<tbody>
<tr><th><time datetime="2026-01-02">..</time></th><td>2.000%</td></tr>
<tr><th><time datetime="2026-01-05">..</time></th><td>2.100%</td></tr>
</tbody></table>
</body></html>
"""


class FakeProvider:
    name = "fake"
    source_label = "fake provider"

    def __init__(self, data: dict[int, list[ProviderFixing]]):
        self.data = data

    def get_available_tenors(self):
        return [Tenor.M6]

    def get_fixings(self, tenor, start=None, end=None):
        out = []
        for _year, fixings in self.data.items():
            for f in fixings:
                if f.tenor == tenor and (start is None or f.date >= start) and (end is None or f.date <= end):
                    out.append(f)
        return sorted(out, key=lambda f: f.date)

    def get_latest(self, tenor):
        fixings = self.get_fixings(tenor)
        return fixings[-1] if fixings else None

    def get_last_available_date(self, tenor):
        latest = self.get_latest(tenor)
        return latest.date if latest else None


def pf(day, rate, tenor=Tenor.M6):
    return ProviderFixing(
        tenor=tenor,
        date=day,
        rate=rate,
        source="fake",
        source_url="http://fake",
    )


@pytest.fixture()
def importer(db):
    repo = EuriborRepository(db)
    provider = FakeProvider({2026: [pf(date(2026, 1, 2), 2.0), pf(date(2026, 1, 5), 2.1)]})
    return EuriborImporter(provider, repo, Settings(history_start_year=2026))


class TestImporter:
    def test_import_is_idempotent(self, importer):
        r1 = importer.import_year(2026)
        assert r1.inserted == 2 and r1.duplicates == 0
        r2 = importer.import_year(2026)
        assert r2.inserted == 0 and r2.duplicates == 2 and r2.conflicts == 0

    def test_missing_days_not_invented(self, importer):
        importer.import_year(2026)
        # weekends 2026-01-03/04 and beyond absent
        stored = importer.repository.get_range(Tenor.M6, date(2026, 1, 1), date(2026, 1, 31))
        assert [f.date for f in stored] == [date(2026, 1, 2), date(2026, 1, 5)]

    def test_unexpected_change_flagged(self, importer):
        importer.import_year(2026)
        importer.provider.data[2026] = [pf(date(2026, 1, 2), 9.999), pf(date(2026, 1, 5), 2.1)]
        report = importer.import_year(2026)
        assert report.conflicts == 1
        anomalies = importer.repository.get_anomalies()
        assert anomalies[0]["old_rate"] == 2.0
        assert anomalies[0]["new_rate"] == 9.999

    def test_history_spans_years(self, db):
        repo = EuriborRepository(db)
        provider = FakeProvider(
            {
                2025: [pf(date(2025, 12, 30), 1.0)],
                2026: [pf(date(2026, 1, 2), 2.0), pf(date(2026, 1, 5), 2.1)],
            }
        )
        imp = EuriborImporter(provider, repo, Settings(history_start_year=2025))
        report = imp.import_history()
        assert report.inserted == 3
        assert repo.count(Tenor.M6) == 3
