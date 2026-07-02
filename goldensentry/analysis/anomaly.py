"""Point-in-time anomaly detection over an hourly demand series.

Three detectors, each producing a typed, timestamped finding:

    forecast_miss — actual demand deviates >6% from the day-ahead forecast.
    demand_spike  — demand's rolling z-score (vs the preceding 24h) exceeds 3.
    fast_ramp     — hour-over-hour swing exceeds 10%.

Severity is 'warning' at the threshold, 'critical' at ~1.5x the threshold.
"""

import statistics

from ..models import Observation

FORECAST_MISS_THRESHOLD = 0.06
SPIKE_Z_THRESHOLD = 3.0
RAMP_THRESHOLD = 0.10

_MIN_WINDOW = 12  # hours of context required before z-scores are trusted


def _severity(value: float, threshold: float) -> str:
    return "critical" if abs(value) >= 1.5 * threshold else "warning"


def detect_anomalies(series: list[Observation]) -> list[dict]:
    """Scan a series (oldest→newest) and return all findings."""
    findings: list[dict] = []

    for i, obs in enumerate(series):
        # Forecast miss
        if obs.forecast_mw:
            dev = (obs.demand_mw - obs.forecast_mw) / obs.forecast_mw
            if abs(dev) >= FORECAST_MISS_THRESHOLD:
                findings.append({
                    "region": obs.region, "ts": obs.ts.isoformat(),
                    "kind": "forecast_miss",
                    "severity": _severity(dev, FORECAST_MISS_THRESHOLD),
                    "detail": f"Demand {dev:+.1%} vs day-ahead forecast "
                              f"({obs.demand_mw:,.0f} vs {obs.forecast_mw:,.0f} MW)"})

        # Demand spike (rolling z-score against the preceding 24h)
        window = [o.demand_mw for o in series[max(0, i - 24):i]]
        if len(window) >= _MIN_WINDOW:
            mean = statistics.mean(window)
            std = statistics.pstdev(window)
            if std > 0:
                z = (obs.demand_mw - mean) / std
                if abs(z) >= SPIKE_Z_THRESHOLD:
                    findings.append({
                        "region": obs.region, "ts": obs.ts.isoformat(),
                        "kind": "demand_spike",
                        "severity": _severity(z, SPIKE_Z_THRESHOLD),
                        "detail": f"Demand z-score {z:+.1f} vs trailing 24h "
                                  f"(now {obs.demand_mw:,.0f} MW, mean {mean:,.0f} MW)"})

        # Fast ramp
        if i > 0 and series[i - 1].demand_mw > 0:
            ramp = (obs.demand_mw - series[i - 1].demand_mw) / series[i - 1].demand_mw
            if abs(ramp) >= RAMP_THRESHOLD:
                findings.append({
                    "region": obs.region, "ts": obs.ts.isoformat(),
                    "kind": "fast_ramp",
                    "severity": _severity(ramp, RAMP_THRESHOLD),
                    "detail": f"Demand ramped {ramp:+.1%} in one hour"})

    return findings
