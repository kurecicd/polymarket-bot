from fastapi import APIRouter, HTTPException

import common

router = APIRouter()


@router.get("")
def get_whales():
    if not common.WHALE_LIST_PATH.exists():
        raise HTTPException(status_code=404, detail="Whale list not generated yet. Run select_whales.py first.")
    return common.read_json(common.WHALE_LIST_PATH)


@router.get("/monitor-state")
def get_monitor_state():
    state = common.load_monitor_state()
    # Return summary counts, not raw trade ID lists
    return {
        "last_poll_at": state.get("last_poll_at"),
        "wallets_tracked": len(state.get("last_seen_trade_ids", {})),
        "total_seen_trades": sum(
            len(v) for v in state.get("last_seen_trade_ids", {}).values()
        ),
    }
