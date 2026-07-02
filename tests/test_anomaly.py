"""Anomaly detector: catches injected events, stays quiet on clean data."""

from datetime import datetime, timedelta, timezone

from goldensentry.analysis.anomaly import detect_anomalies
from goldensentry.models import Observation


def make_series(demands, forecasts=None):
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    forecasts = forecasts or [None] * len(demands)
    return [Observation(region="TEX", ts=start + timedelta(hours=i),
                        demand_mw=d, forecast_mw=f)
            for i, (d, f) in enumerate(zip(demands, forecasts))]


def test_clean_series_has_no_findings():
    # Gentle sinusoid-free flat demand tracking its forecast exactly.
    series = make_series([50_000] * 48, [50_000] * 48)
    assert detect_anomalies(series) == []


def test_forecast_miss_detected():
    demands = [50_000] * 47 + [54_000]      # +8% vs forecast
    forecasts = [50_000] * 48
    findings = detect_anomalies(make_series(demands, forecasts))
    kinds = {f["kind"] for f in findings}
    assert "forecast_miss" in kinds


def test_spike_detected_with_zscore_and_ramp():
    # Slight noise so std > 0, then a +16% spike in the final hour.
    demands = [50_000 + (i % 3) * 120 for i in range(47)] + [58_000]
    findings = detect_anomalies(make_series(demands))
    kinds = {f["kind"] for f in findings}
    assert "demand_spike" in kinds
    assert "fast_ramp" in kinds


def test_severity_escalates():
    demands = [50_000] * 47 + [56_000]      # +12% miss = 2x threshold
    forecasts = [50_000] * 48
    findings = detect_anomalies(make_series(demands, forecasts))
    miss = next(f for f in findings if f["kind"] == "forecast_miss")
    assert miss["severity"] == "critical"


def test_findings_carry_context():
    demands = [50_000] * 47 + [54_000]
    forecasts = [50_000] * 48
    findings = detect_anomalies(make_series(demands, forecasts))
    miss = next(f for f in findings if f["kind"] == "forecast_miss")
    assert miss["region"] == "TEX"
    assert "MW" in miss["detail"]
    assert miss["ts"].startswith("2026-06-02")  # final hour of the series
