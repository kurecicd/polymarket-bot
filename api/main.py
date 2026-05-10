#!/usr/bin/env python3
"""
FastAPI backend for the Polymarket bot web dashboard.
Exposes runtime state as JSON endpoints consumed by the Next.js frontend.

Run:
    uvicorn api.main:app --reload --port 8000
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import common
from api.routers import stats, positions, whales, activity, actions

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
POLL_INTERVAL = 60      # seconds between monitor runs
PM_INTERVAL = 300       # seconds between position manager runs

_stop_event = threading.Event()


def _bot_loop():
    """Background thread: runs monitor.py + position_manager.py on a schedule."""
    last_pm = 0
    while not _stop_event.is_set():
        try:
            state = common.load_execution_state()
            if state.get("execution_mode") == "execute":
                subprocess.run(
                    [PYTHON, str(ROOT / "monitor.py"), "--execute"],
                    cwd=str(ROOT), timeout=50, capture_output=True
                )
                if time.time() - last_pm >= PM_INTERVAL:
                    subprocess.run(
                        [PYTHON, str(ROOT / "position_manager.py"), "--execute"],
                        cwd=str(ROOT), timeout=50, capture_output=True
                    )
                    last_pm = time.time()
        except Exception:
            pass
        _stop_event.wait(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    common.load_env()
    t = threading.Thread(target=_bot_loop, daemon=True)
    t.start()
    yield
    _stop_event.set()


app = FastAPI(title="Polymarket Bot API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
app.include_router(whales.router, prefix="/api/whales", tags=["whales"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(actions.router, prefix="/api/actions", tags=["actions"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/mode/{mode}")
def set_mode(mode: str):
    """Switch between dry_run and execute mode. Persists across restarts."""
    if mode not in ("execute", "dry_run"):
        return {"error": "mode must be execute or dry_run"}
    state = common.load_execution_state()
    state["execution_mode"] = mode
    common.save_execution_state(state)
    return {"execution_mode": mode}
