import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as _req
from fastapi import APIRouter, HTTPException

import common

router = APIRouter()

_positions_cache: dict = {"data": None, "ts": 0}
_CACHE_TTL = 300  # 5-minute cache — fetching 40 whale positions is expensive


@router.get("")
def get_whales():
    if not common.WHALE_LIST_PATH.exists():
        raise HTTPException(status_code=404, detail="Whale list not generated yet. Run select_whales.py first.")
    return common.read_json(common.WHALE_LIST_PATH)


@router.get("/monitor-state")
def get_monitor_state():
    state = common.load_monitor_state()
    return {
        "last_poll_at": state.get("last_poll_at"),
        "wallets_tracked": len(state.get("last_seen_trade_ids", {})),
        "total_seen_trades": sum(
            len(v) for v in state.get("last_seen_trade_ids", {}).values()
        ),
    }


def _fetch_positions(address: str) -> list[dict]:
    try:
        r = _req.get(
            "https://data-api.polymarket.com/positions",
            params={"user": address, "sizeThreshold": 0},
            timeout=8,
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


@router.get("/live-positions")
def get_whale_live_positions():
    """
    Fetch current open positions held by all tracked whales.
    Groups by market and returns markets sorted by number of whales holding them.
    Results are cached for 5 minutes.
    """
    global _positions_cache
    if _positions_cache["data"] is not None and time.time() - _positions_cache["ts"] < _CACHE_TTL:
        return _positions_cache["data"]

    if not common.WHALE_LIST_PATH.exists():
        return []

    whale_data = common.read_json(common.WHALE_LIST_PATH)
    whales = whale_data.get("whales", [])
    if not whales:
        return []

    # Fetch all whale positions in parallel (40 HTTP calls → ~2-3s instead of 40s)
    whale_positions: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_positions, w["address"]): w for w in whales}
        for future in as_completed(futures):
            whale = futures[future]
            try:
                positions = future.result()
                if positions:
                    whale_positions[whale["address"]] = positions
            except Exception:
                pass

    # Group positions by market (conditionId)
    by_market: dict[str, dict] = defaultdict(lambda: {
        "condition_id": "",
        "title": "",
        "outcome": "",
        "whales": [],
        "total_value": 0.0,
        "avg_price": 0.0,
        "end_date": "",
    })

    for address, positions in whale_positions.items():
        for pos in positions:
            cid = pos.get("conditionId") or pos.get("condition_id") or ""
            if not cid:
                continue
            size = float(pos.get("size") or 0)
            if size <= 0:
                continue
            value = float(pos.get("currentValue") or pos.get("value") or 0)
            price = float(pos.get("pricePerShare") or pos.get("price") or 0)
            title = pos.get("title") or pos.get("market_question") or ""
            outcome = pos.get("outcome") or pos.get("side") or "YES"
            end_date = pos.get("endDate") or pos.get("end_date_iso") or ""

            m = by_market[cid]
            m["condition_id"] = cid
            m["title"] = title
            m["outcome"] = outcome
            m["end_date"] = end_date
            m["total_value"] = round(m["total_value"] + value, 2)
            if address not in [w["address"] for w in m["whales"]]:
                m["whales"].append({
                    "address": address,
                    "value": round(value, 2),
                    "size": round(size, 2),
                    "price": round(price, 4),
                })

    # Build result list sorted by whale count descending
    result = []
    for cid, m in by_market.items():
        whale_count = len(m["whales"])
        if whale_count < 2:
            continue  # only show markets where ≥2 whales are in
        prices = [w["price"] for w in m["whales"] if w["price"] > 0]
        avg_price = round(sum(prices) / len(prices), 4) if prices else 0.0

        # Compute days until close
        days_left = None
        if m["end_date"]:
            try:
                from datetime import datetime, timezone
                end_dt = datetime.fromisoformat(m["end_date"].replace("Z", "+00:00"))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                diff = (end_dt - datetime.now(timezone.utc)).total_seconds()
                days_left = round(diff / 86400, 1)
            except Exception:
                pass

        result.append({
            "condition_id": cid,
            "title": m["title"],
            "outcome": m["outcome"],
            "whale_count": whale_count,
            "total_whale_value": m["total_value"],
            "avg_price": avg_price,
            "end_date": m["end_date"],
            "days_left": days_left,
            "whales": sorted(m["whales"], key=lambda x: -x["value"])[:5],  # top 5 whales in this market
        })

    result.sort(key=lambda x: (-x["whale_count"], -x["total_whale_value"]))

    _positions_cache["data"] = result
    _positions_cache["ts"] = time.time()
    return result
