"""Central configuration.

Everything is driven by environment variables (see .env.example).
The app is designed to run with ZERO keys: no EIA_API_KEY means synthetic
demo data, no ANTHROPIC_API_KEY means a rule-based fallback brief.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "goldensentry.db"
STATIC_DIR = BASE_DIR / "static"

EIA_API_KEY = os.getenv("EIA_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "5"))

# Hours of hourly history kept per region and used for analysis/charts.
HISTORY_HOURS = 72


@dataclass(frozen=True)
class Region:
    """A monitored balancing-authority region (EIA 'respondent')."""

    code: str      # EIA respondent code
    name: str      # human-readable label
    operator: str  # grid operator name


# The four regions on the watch floor. TEX and MIDA are the two biggest
# AI-datacenter load-growth stories in the US grid; CAL and NY add coastal
# demand profiles with very different diurnal shapes.
REGIONS: list[Region] = [
    Region("TEX", "Texas", "ERCOT"),
    Region("CAL", "California", "CAISO"),
    Region("MIDA", "Mid-Atlantic", "PJM"),
    Region("NY", "New York", "NYISO"),
]

REGIONS_BY_CODE = {r.code: r for r in REGIONS}


def live_mode() -> bool:
    """True when we have an EIA key and should pull real grid data."""
    return bool(EIA_API_KEY)
