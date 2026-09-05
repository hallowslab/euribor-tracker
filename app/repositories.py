from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from .db import Database
from .models import EuriborFixing, MortgageConfig, Tenor

RATE_EPSILON = 1e-9


@dataclass
class ImportReport:
    inserted: int = 0
    duplicates: int = 0
    conflicts: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.duplicates + self.conflicts

    def merge(self, other: ImportReport) -> ImportReport:
        self.inserted += other.inserted
        self.duplicates += other.duplicates
        self.conflicts += other.conflicts
        return self


class EuriborRepository:
    def __init__(self, db: Database):
        self._db = db

    def insert_fixings(self, fixings: list[EuriborFixing]) -> ImportReport:
        """Idempotent merge of observed fixings.

        - New (tenor, date) -> inserted.
        - Existing with identical rate -> counted as duplicate, ignored.
        - Existing with a different rate -> NOT overwritten; logged as anomaly.
        """
        report = ImportReport()
        with self._db.connect() as conn:
            for f in fixings:
                row = conn.execute(
                    "SELECT rate FROM euribor_fixings WHERE tenor = ? AND fixing_date = ?",
                    (f.tenor.value, f.date.isoformat()),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO euribor_fixings (tenor, fixing_date, rate, source, source_url, retrieved_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (f.tenor.value, f.date.isoformat(), f.rate, f.source, f.source_url, f.retrieved_at.isoformat()),
                    )
                    report.inserted += 1
                elif abs(row["rate"] - f.rate) > RATE_EPSILON:
                    conn.execute(
                        "INSERT INTO euribor_anomalies (tenor, fixing_date, old_rate, new_rate, detected_at, note) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            f.tenor.value,
                            f.date.isoformat(),
                            row["rate"],
                            f.rate,
                            datetime.now().isoformat(timespec="seconds"),
                            f"rate changed from {row['rate']} to {f.rate}; stored value kept",
                        ),
                    )
                    report.conflicts += 1
                else:
                    report.duplicates += 1
        return report

    def get_fixing(self, tenor: Tenor, day: date) -> EuriborFixing | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM euribor_fixings WHERE tenor = ? AND fixing_date = ?",
                (tenor.value, day.isoformat()),
            ).fetchone()
        return self._row_to_fixing(row) if row else None

    def get_latest(self, tenor: Tenor) -> EuriborFixing | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM euribor_fixings WHERE tenor = ? ORDER BY fixing_date DESC LIMIT 1",
                (tenor.value,),
            ).fetchone()
        return self._row_to_fixing(row) if row else None

    def get_latest_on_or_before(self, tenor: Tenor, day: date) -> EuriborFixing | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM euribor_fixings WHERE tenor = ? AND fixing_date <= ? "
                "ORDER BY fixing_date DESC LIMIT 1",
                (tenor.value, day.isoformat()),
            ).fetchone()
        return self._row_to_fixing(row) if row else None

    def get_previous(self, tenor: Tenor, before: date) -> EuriborFixing | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM euribor_fixings WHERE tenor = ? AND fixing_date < ? "
                "ORDER BY fixing_date DESC LIMIT 1",
                (tenor.value, before.isoformat()),
            ).fetchone()
        return self._row_to_fixing(row) if row else None

    def get_range(self, tenor: Tenor, start: date, end: date) -> list[EuriborFixing]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM euribor_fixings WHERE tenor = ? AND fixing_date >= ? AND fixing_date <= ? "
                "ORDER BY fixing_date ASC",
                (tenor.value, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [self._row_to_fixing(r) for r in rows]

    def get_first_date(self, tenor: Tenor) -> date | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT MIN(fixing_date) AS d FROM euribor_fixings WHERE tenor = ?", (tenor.value,)
            ).fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def get_last_date(self, tenor: Tenor) -> date | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT MAX(fixing_date) AS d FROM euribor_fixings WHERE tenor = ?", (tenor.value,)
            ).fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def count(self, tenor: Tenor) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM euribor_fixings WHERE tenor = ?", (tenor.value,)
            ).fetchone()
        return int(row["n"])

    def stored_tenors(self) -> list[Tenor]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT tenor FROM euribor_fixings ORDER BY tenor").fetchall()
        return [Tenor(r["tenor"]) for r in rows]

    def get_anomalies(self, limit: int = 100) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM euribor_anomalies ORDER BY detected_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def counts_by_tenor(self) -> dict[str, int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT tenor, COUNT(*) AS n FROM euribor_fixings GROUP BY tenor"
            ).fetchall()
        return {r["tenor"]: int(r["n"]) for r in rows}

    @staticmethod
    def _row_to_fixing(row) -> EuriborFixing:
        return EuriborFixing(
            tenor=Tenor(row["tenor"]),
            date=date.fromisoformat(row["fixing_date"]),
            rate=float(row["rate"]),
            source=row["source"],
            source_url=row["source_url"],
            retrieved_at=datetime.fromisoformat(row["retrieved_at"]),
        )


class ConfigRepository:
    def __init__(self, db: Database):
        self._db = db

    def get_mortgage(self) -> MortgageConfig | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT value FROM mortgage_config WHERE key = 'mortgage'").fetchone()
        if not row:
            return None
        data = json.loads(row["value"])
        data["tenor"] = Tenor(data["tenor"])
        for key in ("start_date", "end_date", "next_revision_date", "fixed_rate_period_end"):
            if data.get(key):
                data[key] = date.fromisoformat(data[key])
        return MortgageConfig(**data)

    def save_mortgage(self, config: MortgageConfig) -> None:
        data = config.__dict__.copy()
        data["tenor"] = config.tenor.value
        for key in ("start_date", "end_date", "next_revision_date", "fixed_rate_period_end"):
            value = getattr(config, key)
            data[key] = value.isoformat() if value else None
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO mortgage_config (key, value) VALUES ('mortgage', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(data),),
            )


class AlertRepository:
    def __init__(self, db: Database):
        self._db = db

    def list_alerts(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM alerts ORDER BY id").fetchall()
        alerts = [dict(r) for r in rows]
        for alert in alerts:
            alert["params"] = json.loads(alert["params"])
        return alerts

    def create_alert(self, alert_type: str, tenor: str, params: dict) -> int:
        with self._db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO alerts (type, tenor, params) VALUES (?, ?, ?)",
                (alert_type, tenor, json.dumps(params)),
            )
            return int(cur.lastrowid)

    def update_alert(self, alert_id: int, enabled: bool) -> None:
        with self._db.connect() as conn:
            conn.execute("UPDATE alerts SET enabled = ? WHERE id = ?", (int(enabled), alert_id))

    def delete_alert(self, alert_id: int) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))

    def mark_triggered(self, alert_id: int) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE alerts SET last_triggered_at = ?, triggered_count = triggered_count + 1 "
                "WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), alert_id),
            )
