from __future__ import annotations

from datetime import date, datetime

from ..config import Settings
from ..models import SUPPORTED_TENORS, EuriborFixing, Tenor
from ..providers.base import EuriborProvider
from ..repositories import EuriborRepository, ImportReport


class EuriborImporter:
    """Imports fixings from a provider into the database.

    The importer is idempotent and safe to run repeatedly: it relies on the
    repository merge semantics (insert new, skip identical, flag conflicting).
    Missing business days are simply absent from the provider data and are
    never invented here.
    """

    def __init__(self, provider: EuriborProvider, repository: EuriborRepository, settings: Settings | None = None):
        self.provider = provider
        self.repository = repository
        self.settings = settings or Settings()

    def import_history(self, tenors: list[Tenor] | None = None) -> ImportReport:
        tenors = tenors or list(SUPPORTED_TENORS)
        report = ImportReport()
        start_year = self.settings.history_start_year
        end_year = date.today().year
        for year in range(start_year, end_year + 1):
            report.merge(self.import_year(year, tenors))
        self._record_import(report, "history")
        return report

    def import_year(self, year: int, tenors: list[Tenor] | None = None) -> ImportReport:
        tenors = tenors or list(SUPPORTED_TENORS)
        report = ImportReport()
        for tenor in tenors:
            fixings = self.provider.get_fixings(tenor, date(year, 1, 1), date(year, 12, 31))
            report.merge(self.repository.insert_fixings(self._to_entities(fixings)))
        return report

    def update(self, tenors: list[Tenor] | None = None) -> ImportReport:
        """Fast refresh: only the current year, typically run daily."""
        tenors = tenors or list(SUPPORTED_TENORS)
        today = date.today()
        report = self.import_year(today.year, tenors)
        self._record_import(report, "update")
        return report

    def _record_import(self, report: ImportReport, kind: str) -> None:
        db = self.repository._db  # noqa: SLF001 - importer and repo share the same Database
        db.meta_set(
            "last_import",
            f"{datetime.now().isoformat(timespec='seconds')}|{kind}|"
            f"inserted={report.inserted},duplicates={report.duplicates},conflicts={report.conflicts}",
        )

    def _to_entities(self, fixings: list) -> list[EuriborFixing]:
        now = datetime.now()
        return [
            EuriborFixing(
                tenor=f.tenor,
                date=f.date,
                rate=f.rate,
                source=f.source,
                source_url=f.source_url,
                retrieved_at=now,
            )
            for f in fixings
        ]
