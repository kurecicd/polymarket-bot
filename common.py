#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LOCAL_ENV = ROOT / ".env"

# On Railway, persistent volume is mounted at /data
_PERSISTENT = Path("/data") if Path("/data").exists() and Path("/data").is_dir() else ROOT
DATA_DIR = _PERSISTENT / "data"
RUNTIME_DIR = _PERSISTENT / "runtime"

EXECUTION_STATE_PATH = RUNTIME_DIR / "execution_state.json"
MONITOR_STATE_PATH = RUNTIME_DIR / "monitor_state.json"
WHALE_LIST_PATH = RUNTIME_DIR / "whale_list.json"
EXECUTION_LOG_PATH = RUNTIME_DIR / "execution_log.jsonl"
EVENT_LOG_PATH = RUNTIME_DIR / "event_log.jsonl"

PLACEHOLDER_VALUES = {"", "replace_me", "your_private_key_here"}


def load_env() -> list[str]:
    loaded: list[str] = []
    if LOCAL_ENV.exists():
        with LOCAL_ENV.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                current = os.environ.get(key)
                if key and (current is None or current.strip() in PLACEHOLDER_VALUES):
                    os.environ[key] = value
        loaded.append(str(LOCAL_ENV))
    return loaded


def has_real_value(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in PLACEHOLDER_VALUES)


def get_private_key() -> str:
    """Read private key from POLYMARKET_PRIVATE_KEY, POLYMARKET_PRIVATE_KEY_RABBY, or POLYMARKET_PRIVATE_KEY_POLY — whichever is set."""
    for var in ("POLYMARKET_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY_RABBY", "POLYMARKET_PRIVATE_KEY_POLY"):
        val = os.getenv(var, "").strip().removeprefix("0x")
        if has_real_value(val):
            return val
    raise RuntimeError("No private key found — set POLYMARKET_PRIVATE_KEY, POLYMARKET_PRIVATE_KEY_RABBY or POLYMARKET_PRIVATE_KEY_POLY in Railway")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}-{os.getpid()}"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def log_event(script: str, run_id: str, event_type: str, **details: Any) -> None:
    append_jsonl(
        EVENT_LOG_PATH,
        {
            "time": iso_now(),
            "script": script,
            "run_id": run_id,
            "event": event_type,
            "details": details,
        },
    )


def get_capital(client=None) -> float:
    """Return live USDC balance from blockchain. Falls back to env/state if client not provided."""
    if client is not None:
        try:
            bal = client.get_usdc_balance()
            if bal > 0:
                return bal
        except Exception:
            pass
    # Env var override (useful for testing)
    env_val = float(os.getenv("POLYMARKET_CAPITAL", "0"))
    if env_val > 0:
        return env_val
    try:
        state = read_json(EXECUTION_STATE_PATH)
        return float(state.get("capital", 0))
    except Exception:
        return 0.0


def set_capital(amount: float) -> None:
    """Update capital in state file — takes effect immediately, no redeploy needed."""
    EXECUTION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if EXECUTION_STATE_PATH.exists():
        state = read_json(EXECUTION_STATE_PATH)
    else:
        state = {}
    state["capital"] = amount
    write_json(EXECUTION_STATE_PATH, state)


def load_execution_state() -> dict[str, Any]:
    if not EXECUTION_STATE_PATH.exists():
        return {
            "schema_version": 1,
            "execution_mode": "dry_run",
            "updated_at": None,
            "active_positions": {},
            "completed_position_ids": [],
            "daily_trade_log": [],
        }
    return read_json(EXECUTION_STATE_PATH)


def save_execution_state(state: dict[str, Any]) -> None:
    state["updated_at"] = iso_now()
    write_json(EXECUTION_STATE_PATH, state)


def load_monitor_state() -> dict[str, Any]:
    if not MONITOR_STATE_PATH.exists():
        return {"last_seen_trade_ids": {}, "last_poll_at": None}
    return read_json(MONITOR_STATE_PATH)


def save_monitor_state(state: dict[str, Any]) -> None:
    state["last_poll_at"] = iso_now()
    write_json(MONITOR_STATE_PATH, state)


def count_todays_trades(execution_state: dict[str, Any]) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(1 for entry in execution_state.get("daily_trade_log", []) if entry.startswith(today))


def record_trade_today(execution_state: dict[str, Any]) -> None:
    log = execution_state.setdefault("daily_trade_log", [])
    log.append(iso_now())
    # Keep last 100 entries only
    if len(log) > 100:
        execution_state["daily_trade_log"] = log[-100:]
