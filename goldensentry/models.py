"""Shared data structures."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Observation:
    """One hourly reading for one region.

    demand_mw   — actual metered demand (EIA type 'D')
    forecast_mw — day-ahead demand forecast (EIA type 'DF'); may be None
                  when the operator hasn't reported one for that hour.
    """

    region: str
    ts: datetime            # timezone-aware UTC, truncated to the hour
    demand_mw: float
    forecast_mw: float | None = None
