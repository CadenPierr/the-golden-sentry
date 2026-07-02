"""SQLite persistence for observations and detected anomalies.

Uses the stdlib sqlite3 module — no ORM, no external database. Observations
are keyed on (region, ts) so re-ingesting the same window is idempotent;
live-mode values that get revised by the operator simply overwrite.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import Observation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    region      TEXT NOT NULL,
    ts          TEXT NOT NULL,      -- ISO 8601 UTC
    demand_mw   REAL NOT NULL,
    forecast_mw REAL,
    PRIMARY KEY (region, ts)
);
CREATE TABLE IF NOT EXISTS anomalies (
    region   TEXT NOT NULL,
    ts       TEXT NOT NULL,
    kind     TEXT NOT NULL,
    severity TEXT NOT NULL,
    detail   TEXT NOT NULL,
    PRIMARY KEY (region, ts, kind)
);
"""


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def upsert_observations(self, observations: list[Observation]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO observations VALUES (?, ?, ?, ?)",
                [(o.region, o.ts.isoformat(), o.demand_mw, o.forecast_mw)
                 for o in observations])

    def trim_stale_future(self, region: str, latest_ts_iso: str) -> None:
        """Delete rows newer than the source's own latest hour.

        Guards against a source switch (e.g. demo -> live) leaving behind
        rows from the other source that are timestamped later than
        anything the current source has reported — those would otherwise
        masquerade as the "latest" reading.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM observations WHERE region = ? AND ts > ?",
                (region, latest_ts_iso))

    def get_series(self, region: str, hours: int) -> list[Observation]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT region, ts, demand_mw, forecast_mw FROM observations "
                "WHERE region = ? AND ts >= ? ORDER BY ts",
                (region, cutoff)).fetchall()
        return [Observation(region=r, ts=datetime.fromisoformat(t),
                            demand_mw=d, forecast_mw=f)
                for r, t, d, f in rows]

    def record_anomalies(self, anomalies: list[dict]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO anomalies VALUES (?, ?, ?, ?, ?)",
                [(a["region"], a["ts"], a["kind"], a["severity"], a["detail"])
                 for a in anomalies])

    def get_recent_anomalies(self, hours: int) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT region, ts, kind, severity, detail FROM anomalies "
                "WHERE ts >= ? ORDER BY ts DESC",
                (cutoff,)).fetchall()
        return [{"region": r, "ts": t, "kind": k, "severity": s, "detail": d}
                for r, t, k, s, d in rows]
