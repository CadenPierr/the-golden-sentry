"""Grid stress index — one number an operator can glance at.

The index (0–100) blends three signals, each normalized against a threshold
that represents "clearly abnormal" for that signal:

    forecast deviation  (weight 0.5) — actual vs day-ahead forecast.
                        A 10% miss is a serious event; normalize against it.
    demand z-score      (weight 0.3) — latest demand vs trailing-24h
                        mean/std. |z| = 4 is far outside normal variation.
    ramp rate           (weight 0.2) — hour-over-hour change. Grids ramp
                        gradually; 15%/hour is an emergency-grade swing.

Watch levels:  <25 NORMAL · <50 ELEVATED · <75 HIGH · ≥75 CRITICAL
"""

import statistics

from ..models import Observation

FORECAST_DEV_NORM = 0.10   # 10% forecast miss ⇒ full contribution
ZSCORE_NORM = 4.0          # |z| of 4 ⇒ full contribution
RAMP_NORM = 0.15           # 15%/hour ramp ⇒ full contribution

WATCH_LEVELS = ["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]


def watch_level(score: float) -> str:
    if score < 25:
        return "NORMAL"
    if score < 50:
        return "ELEVATED"
    if score < 75:
        return "HIGH"
    return "CRITICAL"


def compute_metrics(series: list[Observation]) -> dict:
    """Compute current stress metrics from an hourly series (oldest→newest).

    Returns a dict with the raw signals, the composite score, and the level.
    Degrades gracefully on short series (missing signals contribute zero).
    """
    if not series:
        return {"demand_mw": None, "forecast_mw": None, "forecast_dev": None,
                "zscore": None, "ramp": None, "stress": 0.0,
                "level": "NORMAL"}

    latest = series[-1]

    forecast_dev = None
    if latest.forecast_mw:
        forecast_dev = (latest.demand_mw - latest.forecast_mw) / latest.forecast_mw

    zscore = None
    window = [o.demand_mw for o in series[-25:-1]]  # trailing 24 hours
    if len(window) >= 12:
        mean = statistics.mean(window)
        std = statistics.pstdev(window)
        # Variance floor: an ultra-flat history would make any deviation an
        # absurd (or undefined) z-score; treat 0.5% of mean as minimum noise.
        std = max(std, 0.005 * mean)
        if std > 0:
            zscore = (latest.demand_mw - mean) / std

    ramp = None
    if len(series) >= 2 and series[-2].demand_mw > 0:
        ramp = (latest.demand_mw - series[-2].demand_mw) / series[-2].demand_mw

    score = 100 * min(1.0, (
        0.5 * min(1.0, abs(forecast_dev or 0) / FORECAST_DEV_NORM)
        + 0.3 * min(1.0, abs(zscore or 0) / ZSCORE_NORM)
        + 0.2 * min(1.0, abs(ramp or 0) / RAMP_NORM)))

    return {
        "demand_mw": latest.demand_mw,
        "forecast_mw": latest.forecast_mw,
        "forecast_dev": forecast_dev,
        "zscore": zscore,
        "ramp": ramp,
        "stress": round(score, 1),
        "level": watch_level(score),
    }
