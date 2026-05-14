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


@app.get("/api/debug/balance")
def debug_balance():
    """Show wallet address and live USDC balance from Polygon blockchain."""
    import os as _os
    common.load_env()
    key = common.get_private_key()
    if not key:
        return {"error": "POLYMARKET_PRIVATE_KEY not set"}
    try:
        from polymarket_client import PolymarketClient
        funder = _os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None
        client = PolymarketClient(private_key=key, funder=funder)
        usdc = client.get_usdc_balance()
        return {"address": client.address, "usdc_balance": usdc, "funder": funder}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/debug/logs")
def debug_logs(n: int = 50):
    """Return last N lines from event_log.jsonl and execution_log.jsonl."""
    import json as _json

    def _tail(path: Path, lines: int) -> list:
        if not path.exists():
            return []
        try:
            raw = path.read_text().strip().splitlines()
            return [_json.loads(l) for l in raw[-lines:] if l.strip()]
        except Exception as exc:
            return [{"error": str(exc)}]

    return {
        "event_log": _tail(common.EVENT_LOG_PATH, n),
        "execution_log": _tail(common.EXECUTION_LOG_PATH, n),
    }


@app.delete("/api/debug/clear-simulated-positions")
def clear_simulated_positions():
    """Remove dry-run positions that were never real orders (order_response empty)."""
    state = common.load_execution_state()
    before = len(state.get("active_positions", {}))
    state["active_positions"] = {
        k: v for k, v in state.get("active_positions", {}).items()
        if v.get("order_id")  # keep only positions with a real order ID
    }
    # Also reset daily_trade_log entries that came from dry runs
    state["daily_trade_log"] = []
    common.save_execution_state(state)
    after = len(state["active_positions"])
    return {"removed": before - after, "remaining": after}


@app.get("/api/debug/register-wallet")
def debug_register_wallet():
    """Approve USDC for CLOB exchange on-chain + update balance allowance."""
    import os as _os
    common.load_env()
    try:
        from web3 import Web3
        from eth_account import Account

        key = common.get_private_key()
        w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
        from web3.middleware import ExtraDataToPOAMiddleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        account = Account.from_key("0x" + key)
        address = account.address

        USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
        CLOB_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
        MAX = 2**256 - 1

        usdc = w3.eth.contract(
            address=Web3.to_checksum_address(USDC),
            abi=[{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}]
        )
        current_allowance = w3.eth.call({"to": USDC, "data": "0xdd62ed3e" + "0"*24 + address[2:].lower() + "0"*24 + CLOB_EXCHANGE[2:].lower()})
        allowance = int(current_allowance.hex(), 16)

        if allowance > 10**6:
            return {"address": address, "status": "already_approved", "allowance_usdc": allowance / 1e6}

        nonce = w3.eth.get_transaction_count(address)
        tx = usdc.functions.approve(
            Web3.to_checksum_address(CLOB_EXCHANGE), MAX
        ).build_transaction({"from": address, "nonce": nonce, "gas": 100000, "chainId": 137})
        signed = w3.eth.account.sign_transaction(tx, "0x" + key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        return {"address": address, "status": "approved", "tx_hash": tx_hash.hex()}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/debug/test-order")
def debug_test_order():
    """Place a minimal test order and return the raw signed order + response."""
    import os as _os, json as _json
    common.load_env()
    key = common.get_private_key()
    if not key:
        return {"error": "POLYMARKET_PRIVATE_KEY not set"}
    try:
        from polymarket_client import PolymarketClient
        from py_clob_client_v2.clob_types import OrderArgs, OrderType
        funder = _os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None
        client = PolymarketClient(private_key=key, funder=funder)
        creds = client.create_or_derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
        # Use the Bitcoin/GTA VI market NO token
        token_id = "91863162118308663069733924043159186005106558783397508844234610341221325526200"
        order_args = OrderArgs(token_id=token_id, price=0.5, size=2.0, side="BUY")
        signed = client._clob.create_order(order_args)
        # Serialize order
        import dataclasses as _dc
        signed_dict = _dc.asdict(signed) if _dc.is_dataclass(signed) else signed.__dict__ if hasattr(signed, '__dict__') else {"str": str(signed)}
        # Post through client normally and capture result
        try:
            resp = client._clob.post_order(signed, OrderType.GTC)
            return {"signed_order": signed_dict, "response": resp}
        except Exception as post_exc:
            return {"signed_order": signed_dict, "post_error": str(post_exc)}
    except Exception as exc:
        return {"error": str(exc), "type": type(exc).__name__}


_last_qb_output: dict = {"stdout": "", "stderr": "", "returncode": None, "ran_at": None}

@app.post("/api/debug/run-quick-bets")
def run_quick_bets_debug(execute: bool = False):
    """Run quick_bets.py synchronously and return full output for debugging."""
    import os as _os
    args = [PYTHON, str(ROOT / "quick_bets.py")]
    if execute:
        args.append("--execute")
    result = subprocess.run(
        args,
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


@app.get("/api/capital")
def get_capital():
    return {"capital": common.get_capital()}

@app.post("/api/capital/{amount}")
def set_capital(amount: float):
    """Set trading capital without redeploying. Bot uses 2% of this per trade."""
    if amount < 0:
        return {"error": "amount must be >= 0"}
    common.set_capital(amount)
    return {"capital": amount, "bet_size_2pct": round(amount * 0.02, 2)}


@app.post("/api/mode/{mode}")
def set_mode(mode: str):
    """Switch between dry_run and execute mode. Persists across restarts."""
    if mode not in ("execute", "dry_run"):
        return {"error": "mode must be execute or dry_run"}
    state = common.load_execution_state()
    state["execution_mode"] = mode
    common.save_execution_state(state)
    return {"execution_mode": mode}
