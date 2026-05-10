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


SETUP_PROGRESS_PATH = common.RUNTIME_DIR / "setup_progress.json"


def _write_progress(stage: str, running: bool, rows: int = 0, wallets: int = 0) -> None:
    common.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    common.write_json(SETUP_PROGRESS_PATH, {
        "running": running,
        "stage": stage,
        "rows_downloaded": rows,
        "wallets_scanned": wallets,
        "updated_at": common.iso_now(),
    })


def _read_progress() -> dict:
    if SETUP_PROGRESS_PATH.exists():
        try:
            return common.read_json(SETUP_PROGRESS_PATH)
        except Exception:
            pass
    return {"running": False, "stage": "not_started", "rows_downloaded": 0, "wallets_scanned": 0}


@router.post("/setup")
def trigger_setup(background_tasks: BackgroundTasks):
    progress = _read_progress()
    if progress.get("running"):
        return {"status": "already_running", "message": "Setup is already in progress"}

    def _full_setup():
        try:
            common.load_env()
            _write_progress("fetching", running=True)
            _run("fetch_historical.py", "--wallets", "2000", timeout=43200)

            rows, wallets = 0, 0
            parquet = common.DATA_DIR / "trades_raw.parquet"
            if parquet.exists():
                try:
                    import pandas as pd
                    df = pd.read_parquet(parquet, columns=["maker_address"])
                    rows = len(df)
                    wallets = df["maker_address"].nunique()
                except Exception:
                    pass

            if not parquet.exists():
                _write_progress("failed_no_trades", running=False)
                return

            # If 0 trades (seed fallback used), skip ranking — whale_list.json already exists
            if rows == 0:
                whale_count = 0
                if common.WHALE_LIST_PATH.exists():
                    try:
                        whale_count = len(common.read_json(common.WHALE_LIST_PATH).get("whales", []))
                    except Exception:
                        pass
                if whale_count > 0:
                    _write_progress("done", running=False, rows=0, wallets=whale_count)
                    return
                _write_progress("failed_no_trades", running=False)
                return

            _write_progress("ranking", running=True, rows=rows, wallets=wallets)
            result = _run("rank_wallets.py", timeout=3600)
            if not result["success"]:
                _write_progress("failed_ranking", running=False)
                return

            _write_progress("selecting", running=True, rows=rows, wallets=wallets)
            _run("select_whales.py", timeout=60)

            _write_progress("done", running=False, rows=rows, wallets=wallets)
        except Exception as exc:
            _write_progress(f"failed: {str(exc)[:80]}", running=False)

    background_tasks.add_task(_full_setup)
    _write_progress("fetching", running=True)
    return {"status": "triggered"}


@router.get("/setup-status")
def get_setup_status():
    progress = _read_progress()
    rankings_file = common.DATA_DIR / "wallet_rankings.parquet"
    trades_file = common.DATA_DIR / "trades_raw.parquet"

    whale_count = 0
    if common.WHALE_LIST_PATH.exists():
        try:
            whale_count = len(common.read_json(common.WHALE_LIST_PATH).get("whales", []))
        except Exception:
            pass

    stage = progress.get("stage", "not_started")
    if rankings_file.exists() and not progress.get("running"):
        stage = "done"

    # data_ready = either rankings parquet exists OR whale_list.json has whales (seed mode)
    whale_list_ready = whale_count > 0
    return {
        "setup_running": progress.get("running", False),
        "stage": stage,
        "data_ready": rankings_file.exists() or whale_list_ready,
        "trades_fetched": trades_file.exists(),
        "whales_selected": common.WHALE_LIST_PATH.exists(),
        "rows_downloaded": progress.get("rows_downloaded", 0),
        "wallets_scanned": progress.get("wallets_scanned", 0),
        "whale_count": whale_count,
    }


@router.get("/test-auth")
def test_auth():
    """Test if POLYMARKET_PRIVATE_KEY is valid and can auth with CLOB API."""
    import os
    common.load_env()
    key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "POLYMARKET_PRIVATE_KEY not set"}
    key_preview = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "too_short"
    try:
        from py_clob_client.client import ClobClient
        client = ClobClient(host="https://clob.polymarket.com", chain_id=137, key=key)
        address = client.get_address()
        creds = client.derive_api_key()
        return {
            "ok": True,
            "address": address,
            "api_key_preview": f"{creds.api_key[:8]}...",
            "key_preview": key_preview,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "key_preview": key_preview}


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
