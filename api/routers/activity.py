import json
from pathlib import Path

from fastapi import APIRouter

import common

router = APIRouter()

INTERESTING_EVENTS = {
    "copy_trade_opened", "position_closed", "vote_complete",
    "order_failed", "sell_order_failed", "daily_limit_reached",
    "quick_bet_placed",
}


def _read_jsonl(path: Path, n: int = 200) -> list[dict]:
    if not path.exists():
        return []
    lines = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except Exception:
                    pass
    return lines[-n:]


@router.get("")
def get_activity(limit: int = 50):
    events = _read_jsonl(common.EVENT_LOG_PATH)
    filtered = [e for e in events if e.get("event") in INTERESTING_EVENTS]
    return list(reversed(filtered[-limit:]))


@router.get("/consensus")
def get_consensus_log(limit: int = 20):
    events = _read_jsonl(common.EVENT_LOG_PATH)
    consensus = [e for e in events if e.get("event") == "vote_complete"]
    return list(reversed(consensus[-limit:]))


@router.get("/trades")
def get_trade_log(limit: int = 50):
    entries = _read_jsonl(common.EXECUTION_LOG_PATH)
    return list(reversed(entries[-limit:]))
