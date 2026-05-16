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


def _run_whale_position_scanner():
    """
    Every 10 minutes: look at what all 40 tracked whales are currently holding.
    If ≥3 whales hold the same market+outcome and we don't already have a position,
    run 3-agent consensus and place a trade if approved.
    Complements the 60s monitor (which catches new entries); this catches markets
    whales entered before we started watching them.
    """
    common.load_env()
    state = common.load_execution_state()
    if state.get("execution_mode") != "execute":
        return
    try:
        from api.routers.whales import analyze_whale_positions
        result = analyze_whale_positions(execute=True)
        traded = sum(1 for r in result.get("results", []) if r.get("traded"))
        analyzed = len(result.get("results", []))
        if analyzed > 0:
            common.log_event("position_scanner", common.new_run_id("ps"),
                             "scan_complete", analyzed=analyzed, traded=traded)
    except Exception as e:
        common.log_event("position_scanner", common.new_run_id("ps"), "scan_failed", error=str(e)[:200])


scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    common.load_env()
    scheduler.add_job(_run_monitor, "interval", seconds=60, id="monitor", max_instances=1)
    scheduler.add_job(_run_position_manager, "interval", seconds=300, id="position_manager", max_instances=1)
    scheduler.add_job(_run_whale_position_scanner, "interval", minutes=10, id="whale_position_scanner", max_instances=1)
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


@app.post("/api/debug/deploy-deposit-wallet")
def deploy_deposit_wallet():
    """Step 1: Deploy deposit wallet via Polymarket relayer-v2."""
    import os as _os, requests as _req, time as _time, hmac as _hmac, hashlib as _hashlib, base64 as _b64, json as _json
    common.load_env()
    try:
        key = common.get_private_key()
        api_key = _os.getenv("POLYMARKET_API_KEY", "").strip()
        api_secret = _os.getenv("POLYMARKET_API_SECRET", "").strip()
        api_passphrase = _os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

        from eth_account import Account
        acct = Account.from_key("0x" + key)
        owner = acct.address

        FACTORY = "0x00000000000Fb5C9ADea0298D729A0CB3823Cc07"
        RELAYER = "https://relayer-v2.polymarket.com"
        body = _json.dumps({"type": "WALLET-CREATE", "from": owner, "to": FACTORY}, separators=(",", ":"))

        relayer_api_key = _os.getenv("POLYMARKET_RELAYER_API_KEY", "").strip()
        headers = {
            "Content-Type": "application/json",
            "RELAYER_API_KEY": relayer_api_key,
            "RELAYER_API_KEY_ADDRESS": owner,
        }
        r = _req.post(f"{RELAYER}/submit", headers=headers, data=body, timeout=15)
        return {"status": r.status_code, "response": r.json() if r.text else {}, "owner": owner}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/debug/register-wallet")
def debug_register_wallet():
    """Approve USDC for CLOB exchange on-chain using raw JSON-RPC (no web3 middleware issues)."""
    import os as _os, requests as _req, json as _json
    common.load_env()
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        key = common.get_private_key()
        acct = Account.from_key("0x" + key)
        address = acct.address

        RPC = "https://polygon-bor-rpc.publicnode.com"
        USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
        CLOB = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

        def rpc(method, params):
            r = _req.post(RPC, json={"jsonrpc":"2.0","method":method,"params":params,"id":1}, timeout=10)
            return r.json().get("result")

        # Check current allowance
        allow_data = "0xdd62ed3e" + "000000000000000000000000" + address[2:].lower() + "000000000000000000000000" + CLOB[2:].lower()
        allowance = int(rpc("eth_call", [{"to": USDC, "data": allow_data}, "latest"]) or "0x0", 16) / 1e6
        already_approved = allowance > 1
        tx_hash = None
        if not already_approved:
            approve_data = "0x095ea7b3" + "000000000000000000000000" + CLOB[2:].lower() + "f" * 64
            nonce = int(rpc("eth_getTransactionCount", [address, "latest"]) or "0x0", 16)
            gas_price = int(rpc("eth_gasPrice", []) or "0x0", 16)
            tx = {"nonce": nonce, "gasPrice": gas_price, "gas": 100000, "to": USDC, "value": 0, "data": approve_data, "chainId": 137}
            signed = acct.sign_transaction(tx)
            tx_hash = rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex()])

        # Always ping Polymarket backend to register the wallet
        from polymarket_client import PolymarketClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
        client = PolymarketClient(private_key=key)
        creds = client.create_or_derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
        update_result = client._clob.update_balance_allowance(
            params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        return {"address": address, "allowance_usdc": allowance, "tx_hash": tx_hash, "backend_update": update_result}
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
        # Always derive credentials from the private key with deposit wallet context
        creds = client.create_or_derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
        # Use the Bitcoin/GTA VI market NO token
        token_id = "91863162118308663069733924043159186005106558783397508844234610341221325526200"
        order_args = OrderArgs(token_id=token_id, price=0.5, size=10.0, side="BUY")
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
