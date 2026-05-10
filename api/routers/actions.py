"""
Action endpoints — trigger bot operations from the web UI.
These run the scripts as subprocesses to keep the API non-blocking.
"""
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

import common

router = APIRouter()
ROOT = Path(__file__).resolve().parent.parent.parent
PYTHON = str(ROOT / "venv" / "bin" / "python")


def _run(script: str, *args: str) -> dict:
    try:
        result = subprocess.run(
            [PYTHON, str(ROOT / script), *args],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROOT),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out after 300s"}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc)}


@router.post("/monitor")
def trigger_monitor(background_tasks: BackgroundTasks, execute: bool = False):
    """Trigger one monitor poll cycle."""
    args = ["--execute"] if execute else []
    background_tasks.add_task(_run, "monitor.py", *args)
    return {"status": "triggered", "execute": execute}


@router.post("/quick-bets")
def trigger_quick_bets(background_tasks: BackgroundTasks, execute: bool = False):
    args = ["--execute"] if execute else []
    background_tasks.add_task(_run, "quick_bets.py", *args)
    return {"status": "triggered", "execute": execute}


@router.post("/position-manager")
def trigger_position_manager(background_tasks: BackgroundTasks, execute: bool = False):
    args = ["--execute"] if execute else []
    background_tasks.add_task(_run, "position_manager.py", *args)
    return {"status": "triggered", "execute": execute}


@router.post("/refresh-whales")
def trigger_refresh_whales(background_tasks: BackgroundTasks):
    """Re-run wallet ranking and whale selection."""
    def _refresh():
        _run("rank_wallets.py")
        _run("select_whales.py")
    background_tasks.add_task(_refresh)
    return {"status": "triggered"}


@router.get("/status")
def get_status():
    execution_state = common.load_execution_state()
    whale_list = {}
    if common.WHALE_LIST_PATH.exists():
        whale_list = common.read_json(common.WHALE_LIST_PATH)
    monitor_state = common.load_monitor_state()

    return {
        "execution_mode": execution_state.get("execution_mode", "dry_run"),
        "whales_loaded": len(whale_list.get("whales", [])) > 0,
        "whale_count": len(whale_list.get("whales", [])),
        "last_poll": monitor_state.get("last_poll_at"),
        "open_positions": sum(
            1 for p in execution_state.get("active_positions", {}).values()
            if p.get("status") == "open"
        ),
        "data_ready": (common.DATA_DIR / "wallet_rankings.parquet").exists(),
    }
