"""EIA API v2 client — pulls real hourly grid demand + day-ahead forecast.

Endpoint: https://api.eia.gov/v2/electricity/rto/region-data/data/
Series types used:
    D  — actual demand (megawatthours, hourly)
    DF — day-ahead demand forecast

EIA reports periods as UTC hours in the form "2026-06-30T14".
"""

from datetime import datetime, timedelta, timezone

import httpx

from ..config import EIA_API_KEY, HISTORY_HOURS, REGIONS
from ..models import Observation

BASE_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"


def _parse_period(period: str) -> datetime:
    return datetime.strptime(period, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)


def fetch_observations(hours: int = HISTORY_HOURS) -> list[Observation]:
    """Fetch the trailing `hours` of demand + forecast for all regions."""
    start = datetime.now(timezone.utc) - timedelta(hours=hours + 2)
    params: list[tuple[str, str]] = [
        ("api_key", EIA_API_KEY),
        ("frequency", "hourly"),
        ("data[0]", "value"),
        ("facets[type][]", "D"),
        ("facets[type][]", "DF"),
        ("start", start.strftime("%Y-%m-%dT%H")),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("length", "5000"),
    ]
    for region in REGIONS:
        params.append(("facets[respondent][]", region.code))

    with httpx.Client(timeout=30) as client:
        resp = client.get(BASE_URL, params=params)
        resp.raise_for_status()
        rows = resp.json()["response"]["data"]

    # Merge D and DF rows into one Observation per (region, hour).
    merged: dict[tuple[str, datetime], dict] = {}
    for row in rows:
        value = row.get("value")
        if value is None:
            continue
        key = (row["respondent"], _parse_period(row["period"]))
        entry = merged.setdefault(key, {})
        if row["type"] == "D":
            entry["demand"] = float(value)
        elif row["type"] == "DF":
            entry["forecast"] = float(value)

    observations = [
        Observation(region=region, ts=ts,
                    demand_mw=entry["demand"],
                    forecast_mw=entry.get("forecast"))
        for (region, ts), entry in merged.items()
        if "demand" in entry
    ]
    observations.sort(key=lambda o: (o.region, o.ts))
    return observations
