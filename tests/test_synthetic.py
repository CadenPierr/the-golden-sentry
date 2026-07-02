"""Synthetic data source: shape, determinism, and forecast-miss events."""

from datetime import datetime, timezone

from goldensentry.config import REGIONS
from goldensentry.data.synthetic import generate_observations

NOW = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)


def test_generates_full_window_for_all_regions():
    obs = generate_observations(hours=72, now=NOW)
    assert len(obs) == len(REGIONS) * 73  # 72h back through the current hour
    regions = {o.region for o in obs}
    assert regions == {r.code for r in REGIONS}


def test_deterministic_across_calls():
    a = generate_observations(hours=24, now=NOW)
    b = generate_observations(hours=24, now=NOW)
    assert a == b


def test_values_are_plausible():
    for o in generate_observations(hours=24, now=NOW):
        assert o.demand_mw > 0
        assert o.forecast_mw is not None and o.forecast_mw > 0
        # Demand never strays more than ~20% from forecast, even in a spike.
        assert abs(o.demand_mw - o.forecast_mw) / o.forecast_mw < 0.20


def test_spikes_produce_forecast_misses():
    # Over a 72h window every region's spike cadence fires at least once,
    # so at least one observation should miss its forecast by >6%.
    obs = generate_observations(hours=72, now=NOW)
    misses = [o for o in obs
              if abs(o.demand_mw - o.forecast_mw) / o.forecast_mw > 0.06]
    assert misses, "expected at least one injected stress event in 72h"
