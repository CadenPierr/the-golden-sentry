"""Orchestrator — runs the ingest → analyze → brief cycle and caches the result.

One GoldenSentry instance owns the store and the latest snapshot. The API
layer calls refresh() on a timer and serves the cached snapshot to clients,
so dashboard reads are always instant regardless of upstream latency.
"""

import logging
from datetime import datetime, timezone

from .analysis.anomaly import detect_anomalies
from .analysis.stress import compute_metrics
from .briefing.watch_officer import generate_brief
from .config import DB_PATH, HISTORY_HOURS, REGIONS, live_mode
from .data import eia_client, synthetic
from .data.store import Store

log = logging.getLogger("goldensentry")


class GoldenSentry:
    def __init__(self, db_path=DB_PATH):
        self.store = Store(db_path)
        self.snapshot: dict | None = None

    def refresh(self) -> dict:
        """Run one full cycle. Blocking — callers run it off the event loop."""
        mode = "live" if live_mode() else "demo"
        log.info("refresh started (mode=%s)", mode)

        if live_mode():
            observations = eia_client.fetch_observations()
        else:
            observations = synthetic.generate_observations()
        self.store.upsert_observations(observations)

        regions_payload = []
        for region in REGIONS:
            series = self.store.get_series(region.code, HISTORY_HOURS)
            metrics = compute_metrics(series)
            anomalies = detect_anomalies(series)
            self.store.record_anomalies(anomalies)
            regions_payload.append({
                "code": region.code, "name": region.name,
                "operator": region.operator, **metrics,
            })

        recent_anomalies = self.store.get_recent_anomalies(hours=24)

        brief_input = {
            "as_of_utc": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "regions": regions_payload,
            "anomalies_24h": recent_anomalies[:20],
            "anomaly_count_24h": len(recent_anomalies),
        }
        brief = generate_brief(brief_input)

        self.snapshot = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": mode,
            "brief": brief,
            "regions": regions_payload,
            "anomalies": recent_anomalies,
        }
        log.info("refresh complete: %s (%s)",
                 brief["watch_level"], brief["source"])
        return self.snapshot

    def get_series_payload(self, region_code: str) -> dict:
        """Chart-ready series for one region."""
        series = self.store.get_series(region_code, HISTORY_HOURS)
        return {
            "region": region_code,
            "timestamps": [o.ts.isoformat() for o in series],
            "demand_mw": [o.demand_mw for o in series],
            "forecast_mw": [o.forecast_mw for o in series],
        }
