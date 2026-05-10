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
PYTHON = sys.executable  # works both locally (venv) and on Railway (system python)


def _run(script: str, *args: str, timeout: int = 300) -> dict:
    try:
        result = subprocess.run(
            [PYTHON, str(ROOT / script), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Timed out after {timeout}s"}
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


_setup_running = False
_setup_stage = ""
_setup_rows_fetched = 0


@router.post("/setup")
def trigger_setup(background_tasks: BackgroundTasks):
    """
    Run the full data pipeline on Railway:
      1. fetch_historical.py  (downloads all trades from subgraph — takes hours)
      2. rank_wallets.py      (compute win rates)
      3. select_whales.py     (pick top 20)
    Runs in background — check /api/actions/status for data_ready flag.
    """
    global _setup_running
    if _setup_running:
        return {"status": "already_running", "message": "Setup is already in progress"}

    def _full_setup():
        global _setup_running, _setup_stage, _setup_rows_fetched
        _setup_running = True
        try:
            common.load_env()
            _setup_stage = "fetching"
            _run("fetch_historical.py", timeout=43200)
            # Count rows fetched
            parquet = common.DATA_DIR / "trades_raw.parquet"
            if parquet.exists():
                import pandas as pd
                _setup_rows_fetched = len(pd.read_parquet(parquet))
            _setup_stage = "ranking"
            _run("rank_wallets.py", timeout=3600)
            _setup_stage = "selecting"
            _run("select_whales.py", timeout=60)
            _setup_stage = "done"
        except Exception:
            _setup_stage = "failed"
        finally:
            _setup_running = False

    background_tasks.add_task(_full_setup)
    return {
        "status": "triggered",
        "message": "Full setup started. fetch_historical.py will run for several hours. Check /api/actions/status for data_ready.",
    }


@router.get("/setup-status")
def get_setup_status():
    trades_file = common.DATA_DIR / "trades_raw.parquet"
    rankings_file = common.DATA_DIR / "wallet_rankings.parquet"

    rows = 0
    wallets = 0
    if trades_file.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(trades_file, columns=["maker_address"])
            rows = len(df)
            wallets = df["maker_address"].nunique()
        except Exception:
            pass

    whale_count = 0
    if common.WHALE_LIST_PATH.exists():
        try:
            whale_count = len(common.read_json(common.WHALE_LIST_PATH).get("whales", []))
        except Exception:
            pass

    return {
        "setup_running": _setup_running,
        "stage": _setup_stage or ("done" if rankings_file.exists() else "not_started"),
        "data_ready": rankings_file.exists(),
        "trades_fetched": trades_file.exists(),
        "whales_selected": common.WHALE_LIST_PATH.exists(),
        "rows_downloaded": _setup_rows_fetched or rows,
        "wallets_scanned": wallets,
        "whale_count": whale_count,
    }


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
