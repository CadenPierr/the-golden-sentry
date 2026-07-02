"""HTTP layer — FastAPI app serving the JSON API and the dashboard.

The refresh cycle runs as a background asyncio task; the actual work is
blocking (HTTP to EIA, SQLite, Anthropic call) so it's pushed to a thread
with asyncio.to_thread. Endpoints only ever read the cached snapshot.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import REFRESH_MINUTES, REGIONS_BY_CODE, STATIC_DIR
from .service import GoldenSentry

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

sentry = GoldenSentry()


async def _refresh_loop():
    while True:
        await asyncio.sleep(REFRESH_MINUTES * 60)
        try:
            await asyncio.to_thread(sentry.refresh)
        except Exception:
            logging.getLogger("goldensentry").exception("refresh failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(sentry.refresh)  # populate before serving
    task = asyncio.create_task(_refresh_loop())
    yield
    task.cancel()


app = FastAPI(title="The Golden Sentry",
              description="Grid situational awareness with an AI watch officer",
              lifespan=lifespan)


@app.get("/api/status")
async def status():
    """The full dashboard snapshot: brief, per-region metrics, anomalies."""
    if sentry.snapshot is None:
        raise HTTPException(503, "First refresh cycle still running")
    return sentry.snapshot


@app.get("/api/regions/{code}/series")
async def region_series(code: str):
    """72h demand-vs-forecast series for one region (chart data)."""
    code = code.upper()
    if code not in REGIONS_BY_CODE:
        raise HTTPException(404, f"Unknown region '{code}'")
    return await asyncio.to_thread(sentry.get_series_payload, code)


@app.post("/api/refresh")
async def force_refresh():
    """Run the ingest → analyze → brief cycle immediately."""
    return await asyncio.to_thread(sentry.refresh)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
