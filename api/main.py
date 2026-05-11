#!/usr/bin/env python3
"""
FastAPI backend for the Polymarket bot web dashboard.
Exposes runtime state as JSON endpoints consumed by the Next.js frontend.

Run:
    uvicorn api.main:app --reload --port 8000
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

import common
from api.routers import stats, positions, whales, activity, actions

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
_last_monitor_output = {"stdout": "", "stderr": "", "returncode": None, "ran_at": None}
_last_pm_output = {"ran_at": None}


def _run_monitor():
    common.load_env()
    state = common.load_execution_state()
    if state.get("execution_mode") != "execute":
        return
    try:
        result = subprocess.run(
            [PYTHON, str(ROOT / "monitor.py"), "--execute"],
            cwd=str(ROOT), timeout=120, capture_output=True, text=True, env=os.environ.copy()
        )
        _last_monitor_output.update({
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-500:],
            "returncode": result.returncode,
            "ran_at": common.iso_now(),
        })
    except Exception as e:
        _last_monitor_output.update({"stderr": str(e), "returncode": -1, "ran_at": common.iso_now()})


def _run_position_manager():
    common.load_env()
    state = common.load_execution_state()
    if state.get("execution_mode") != "execute":
        return
    try:
        subprocess.run(
            [PYTHON, str(ROOT / "position_manager.py"), "--execute"],
            cwd=str(ROOT), timeout=55, capture_output=True, env=os.environ.copy()
        )
        _last_pm_output["ran_at"] = common.iso_now()
    except Exception as e:
        _last_pm_output["ran_at"] = f"error: {e}"


def _run_whale_refresh():
    common.load_env()
    try:
        subprocess.run([PYTHON, str(ROOT / "dune_fetch.py"), "--limit", "200"],
            cwd=str(ROOT), timeout=300, capture_output=True, env=os.environ.copy())
        subprocess.run([PYTHON, str(ROOT / "select_whales.py")],
            cwd=str(ROOT), timeout=60, capture_output=True, env=os.environ.copy())
    except Exception:
        pass


scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    common.load_env()
    scheduler.add_job(_run_monitor, "interval", seconds=60, id="monitor", max_instances=1)
    scheduler.add_job(_run_position_manager, "interval", seconds=300, id="position_manager", max_instances=1)
    scheduler.add_job(_run_whale_refresh, "interval", weeks=1, id="whale_refresh", max_instances=1)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


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


@app.get("/api/debug/monitor")
def debug_monitor():
    return _last_monitor_output


_last_qb_output: dict = {"stdout": "", "stderr": "", "returncode": None, "ran_at": None}

@app.post("/api/debug/run-quick-bets")
def run_quick_bets_debug():
    """Run quick_bets.py synchronously and return full output for debugging."""
    import os as _os
    result = subprocess.run(
        [PYTHON, str(ROOT / "quick_bets.py")],
        cwd=str(ROOT), timeout=120, capture_output=True, text=True,
        env=_os.environ.copy()
    )
    _last_qb_output.update({
        "stdout": result.stdout[-3000:],
        "stderr": result.stderr[-1000:],
        "returncode": result.returncode,
        "ran_at": common.iso_now(),
    })
    return _last_qb_output


@app.post("/api/mode/{mode}")
def set_mode(mode: str):
    """Switch between dry_run and execute mode. Persists across restarts."""
    if mode not in ("execute", "dry_run"):
        return {"error": "mode must be execute or dry_run"}
    state = common.load_execution_state()
    state["execution_mode"] = mode
    common.save_execution_state(state)
    return {"execution_mode": mode}
