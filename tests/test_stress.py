"""Stress index behavior: bounds, monotonicity, graceful degradation."""

from datetime import datetime, timedelta, timezone

from goldensentry.analysis.stress import compute_metrics, watch_level
from goldensentry.models import Observation


def make_series(demands, forecasts=None):
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    forecasts = forecasts or [None] * len(demands)
    return [Observation(region="TEX", ts=start + timedelta(hours=i),
                        demand_mw=d, forecast_mw=f)
            for i, (d, f) in enumerate(zip(demands, forecasts))]


def test_empty_series_is_normal():
    metrics = compute_metrics([])
    assert metrics["stress"] == 0.0
    assert metrics["level"] == "NORMAL"


def test_flat_series_scores_low():
    series = make_series([50_000] * 30, [50_000] * 30)
    metrics = compute_metrics(series)
    assert metrics["stress"] < 10
    assert metrics["level"] == "NORMAL"


def test_score_bounded_0_to_100():
    # Absurd spike: triple the forecast, huge ramp, huge z-score.
    demands = [50_000] * 29 + [150_000]
    forecasts = [50_000] * 30
    metrics = compute_metrics(make_series(demands, forecasts))
    assert 0 <= metrics["stress"] <= 100
    assert metrics["level"] == "CRITICAL"


def test_bigger_forecast_miss_scores_higher():
    base = [50_000] * 29
    small_miss = compute_metrics(make_series(base + [51_500], [50_000] * 30))
    big_miss = compute_metrics(make_series(base + [56_000], [50_000] * 30))
    assert big_miss["stress"] > small_miss["stress"]


def test_missing_forecast_degrades_gracefully():
    series = make_series([50_000] * 30)  # no forecasts at all
    metrics = compute_metrics(series)
    assert metrics["forecast_dev"] is None
    assert metrics["level"] == "NORMAL"


def test_watch_level_thresholds():
    assert watch_level(0) == "NORMAL"
    assert watch_level(24.9) == "NORMAL"
    assert watch_level(25) == "ELEVATED"
    assert watch_level(50) == "HIGH"
    assert watch_level(75) == "CRITICAL"
    assert watch_level(100) == "CRITICAL"
