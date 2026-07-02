"""The AI watch officer — turns raw metrics into an operational judgment.

Every refresh cycle, the current cross-region snapshot (stress metrics,
anomalies, 24h trend) is handed to Claude with a watch-officer persona and a
strict JSON schema. The model returns a structured brief: overall watch
level, a headline, a 3–4 sentence assessment, and regions of concern.

If no ANTHROPIC_API_KEY is configured (or the API call fails), a
deterministic rule-based brief is generated instead, so the dashboard is
never blank. The `source` field tells the UI which path produced the brief.
"""

import json

import anthropic

from ..config import ANTHROPIC_API_KEY

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are the watch officer for The Golden Sentry, a grid \
operations monitoring desk covering four US balancing authorities (ERCOT, \
CAISO, PJM, NYISO). You receive a JSON snapshot of current grid state: per-\
region demand, day-ahead forecast deviation, statistical stress signals, and \
detected anomalies over the last 24 hours.

Write an operational brief the way an experienced control-room officer \
would: factual, calm, specific. Reference concrete numbers (MW, percentages) \
from the data. Never invent data that is not in the snapshot. Weigh forecast \
misses most heavily — unforecast demand is what forces emergency dispatch. \
If everything is quiet, say so plainly; do not manufacture drama."""

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "watch_level": {
            "type": "string",
            "enum": ["NORMAL", "ELEVATED", "HIGH", "CRITICAL"],
            "description": "Overall level across all monitored regions",
        },
        "headline": {
            "type": "string",
            "description": "One-line summary, <=100 chars, control-room style",
        },
        "brief": {
            "type": "string",
            "description": "3-4 sentence assessment: current state, notable "
                           "anomalies, recommended posture",
        },
        "regions_of_concern": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Region codes needing attention; empty if none",
        },
    },
    "required": ["watch_level", "headline", "brief", "regions_of_concern"],
    "additionalProperties": False,
}


def generate_brief(snapshot: dict) -> dict:
    """Produce the watch brief for a snapshot; never raises."""
    if not ANTHROPIC_API_KEY:
        return _fallback_brief(snapshot)
    try:
        return _claude_brief(snapshot)
    except Exception as exc:  # any API failure degrades to the fallback
        brief = _fallback_brief(snapshot)
        brief["note"] = f"AI brief unavailable ({type(exc).__name__}); rule-based fallback used"
        return brief


def _claude_brief(snapshot: dict) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": BRIEF_SCHEMA}},
        messages=[{
            "role": "user",
            "content": "Current grid snapshot:\n" + json.dumps(snapshot, indent=2),
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    brief = json.loads(text)
    brief["source"] = "claude"
    return brief


def _fallback_brief(snapshot: dict) -> dict:
    """Deterministic brief from the same signals the model would use."""
    regions = snapshot.get("regions", [])
    order = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3}
    worst = max(regions, key=lambda r: order.get(r["level"], 0), default=None)
    level = worst["level"] if worst else "NORMAL"
    concerns = [r["code"] for r in regions if r["level"] != "NORMAL"]
    anomaly_count = snapshot.get("anomaly_count_24h", 0)

    if level == "NORMAL":
        headline = "All monitored regions operating within normal parameters"
        brief = (f"Demand across all {len(regions)} regions is tracking day-ahead "
                 f"forecasts. {anomaly_count} anomalies logged in the trailing 24 "
                 f"hours, none currently active. Routine monitoring posture.")
    else:
        dev = worst.get("forecast_dev")
        dev_txt = f"{dev:+.1%} vs forecast" if dev is not None else "n/a vs forecast"
        headline = (f"{worst['operator']} at {level}: "
                    f"{worst['demand_mw']:,.0f} MW, {dev_txt}")
        brief = (f"{worst['operator']} ({worst['name']}) demand is "
                 f"{worst['demand_mw']:,.0f} MW, {dev_txt}, stress index "
                 f"{worst['stress']:.0f}/100. {anomaly_count} anomalies logged in "
                 f"the trailing 24 hours. Recommend elevated monitoring of "
                 f"{', '.join(concerns)} until demand reconverges with forecast.")

    return {"watch_level": level, "headline": headline, "brief": brief,
            "regions_of_concern": concerns, "source": "rule-based"}
