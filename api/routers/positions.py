import json
from pathlib import Path

from fastapi import APIRouter

import common

router = APIRouter()


def _read_jsonl(path: Path, n: int = 100) -> list[dict]:
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
def get_positions():
    execution_state = common.load_execution_state()
    active = execution_state.get("active_positions", {})

    open_positions = [
        p for p in active.values()
        if p.get("status") == "open"
    ]
    open_positions.sort(key=lambda x: x.get("opened_at", ""), reverse=True)

    log_entries = _read_jsonl(common.EXECUTION_LOG_PATH)
    closed = [
        e.get("position", {})
        for e in log_entries
        if e.get("event") == "position_closed"
    ][-20:]

    return {
        "open": open_positions,
        "closed": list(reversed(closed)),
    }


@router.get("/open")
def get_open_positions():
    execution_state = common.load_execution_state()
    active = execution_state.get("active_positions", {})
    return [p for p in active.values() if p.get("status") == "open"]
