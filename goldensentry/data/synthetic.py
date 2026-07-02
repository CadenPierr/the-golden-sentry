"""Demo-mode data source — realistic synthetic grid demand.

Design goals:
  * Deterministic: the same (region, hour) always produces the same value,
    so refreshes extend the series smoothly instead of rewriting history.
  * Realistic shape: diurnal sine curve + weekday/weekend factor + noise.
  * Interesting: periodic "stress events" (unforecast demand spikes, the
    signature of a datacenter cluster or heat wave slamming the grid) are
    injected so the anomaly detector and watch officer have real work to do.

The day-ahead forecast is the smooth curve WITHOUT noise or spikes — so a
spike shows up as a forecast miss, exactly like the real-world failure mode.
"""

import math
import random
from datetime import datetime, timedelta, timezone

from ..config import HISTORY_HOURS, REGIONS
from ..models import Observation

# Rough baseline scale per region, in MW.
_BASE_MW = {"TEX": 52_000, "CAL": 28_000, "MIDA": 34_000, "NY": 17_500}

# Each region gets a different spike cadence so events don't align.
_SPIKE_PERIOD_HOURS = {"TEX": 31, "CAL": 47, "MIDA": 41, "NY": 59}

_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _hour_index(ts: datetime) -> int:
    return int((ts - _EPOCH).total_seconds() // 3600)


def _smooth_curve(region: str, ts: datetime) -> float:
    """The predictable component of demand — this is what gets 'forecast'."""
    base = _BASE_MW[region]
    # Diurnal cycle: trough ~04:00 UTC-ish, peak late afternoon local.
    # Offset the phase per region so the curves aren't identical.
    phase = {"TEX": 0.0, "CAL": 2.5, "MIDA": -1.0, "NY": -0.5}[region]
    hour = ts.hour + ts.minute / 60 + phase
    diurnal = 0.18 * math.sin((hour - 9) * math.pi / 12)
    # Weekends run ~7% lighter.
    weekend = -0.07 if ts.weekday() >= 5 else 0.0
    return base * (1 + diurnal + weekend)


def _spike_factor(region: str, ts: datetime) -> float:
    """Occasional 2-hour unforecast demand surge (up to ~+14%)."""
    period = _SPIKE_PERIOD_HOURS[region]
    position = _hour_index(ts) % period
    if position in (0, 1):
        return 1.14 if position == 0 else 1.09
    return 1.0


def _noise(region: str, ts: datetime) -> float:
    """Small deterministic per-hour noise, ±1.2%."""
    rng = random.Random(f"{region}:{ts.isoformat()}")
    return 1 + rng.uniform(-0.012, 0.012)


def generate_observations(hours: int = HISTORY_HOURS,
                          now: datetime | None = None) -> list[Observation]:
    """Generate the trailing `hours` of synthetic data for all regions."""
    now = (now or datetime.now(timezone.utc)).replace(
        minute=0, second=0, microsecond=0)
    observations: list[Observation] = []
    for region in REGIONS:
        for i in range(hours, -1, -1):
            ts = now - timedelta(hours=i)
            smooth = _smooth_curve(region.code, ts)
            demand = smooth * _spike_factor(region.code, ts) * _noise(region.code, ts)
            observations.append(Observation(
                region=region.code, ts=ts,
                demand_mw=round(demand, 1),
                forecast_mw=round(smooth, 1)))
    return observations
