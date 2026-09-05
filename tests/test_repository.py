from __future__ import annotations

from datetime import date, datetime

from app.models import EuriborFixing, Tenor
from app.repositories import EuriborRepository


def fixing(day: date, rate: float, tenor: Tenor = Tenor.M6) -> EuriborFixing:
    return EuriborFixing(
        tenor=tenor,
        date=day,
        rate=rate,
        source="test-source",
        source_url="http://test/url",
        retrieved_at=datetime(2026, 1, 1, 12, 0, 0),
    )


class TestInsertIdempotency:
    def test_inserts_and_dedupes(self, db):
        repo = EuriborRepository(db)
        first = repo.insert_fixings(
            [fixing(date(2026, 1, 2), 2.0), fixing(date(2026, 1, 5), 2.1)]
        )
        assert first.inserted == 2 and first.duplicates == 0 and first.conflicts == 0

        second = repo.insert_fixings(
            [fixing(date(2026, 1, 2), 2.0), fixing(date(2026, 1, 6), 2.2)]
        )
        assert second.inserted == 1 and second.duplicates == 1 and second.conflicts == 0
        assert repo.count(Tenor.M6) == 3

    def test_conflict_is_flagged_not_overwritten(self, db):
        repo = EuriborRepository(db)
        repo.insert_fixings([fixing(date(2026, 1, 2), 2.000)])
        report = repo.insert_fixings([fixing(date(2026, 1, 2), 2.150)])
        assert report.conflicts == 1
        assert report.inserted == 0
        # stored value kept
        stored = repo.get_fixing(Tenor.M6, date(2026, 1, 2))
        assert stored.rate == 2.000
        anomalies = repo.get_anomalies()
        assert len(anomalies) == 1
        assert anomalies[0]["old_rate"] == 2.000
        assert anomalies[0]["new_rate"] == 2.150


class TestQueries:
    def test_latest_and_previous(self, db):
        repo = EuriborRepository(db)
        repo.insert_fixings(
            [
                fixing(date(2026, 1, 2), 2.0),
                fixing(date(2026, 1, 5), 2.1),
                fixing(date(2026, 1, 6), 2.2),
            ]
        )
        latest = repo.get_latest(Tenor.M6)
        assert latest.date == date(2026, 1, 6) and latest.rate == 2.2
        previous = repo.get_previous(Tenor.M6, date(2026, 1, 6))
        assert previous.date == date(2026, 1, 5)
        on_or_before = repo.get_latest_on_or_before(Tenor.M6, date(2026, 1, 3))
        assert on_or_before.date == date(2026, 1, 2)

    def test_range_is_ordered_and_filtered(self, db):
        repo = EuriborRepository(db)
        repo.insert_fixings(
            [fixing(date(2026, 1, i), float(i)) for i in range(2, 30)]
        )
        rows = repo.get_range(Tenor.M6, date(2026, 1, 5), date(2026, 1, 10))
        assert [r.date.day for r in rows] == [5, 6, 7, 8, 9, 10]
        assert rows[0].rate == 5.0

    def test_tenor_isolation(self, db):
        repo = EuriborRepository(db)
        repo.insert_fixings([fixing(date(2026, 1, 2), 2.0, Tenor.M6)])
        repo.insert_fixings([fixing(date(2026, 1, 2), 3.0, Tenor.M12)])
        assert repo.count(Tenor.M6) == 1
        assert repo.count(Tenor.M12) == 1
        assert repo.get_latest(Tenor.M12).rate == 3.0

    def test_metadata_roundtrip(self, db):
        db.meta_set("last_import", "2026-09-04T12:00:00|update|inserted=10")
        assert db.meta_get("last_import").startswith("2026-09-04")
