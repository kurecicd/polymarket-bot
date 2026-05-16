import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

import common

router = APIRouter()


def _read_jsonl(path: Path, n: int = 500) -> list[dict]:
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
def get_stats():
    execution_state = common.load_execution_state()
    log_entries = _read_jsonl(common.EXECUTION_LOG_PATH)

    trade_events = [e for e in log_entries if e.get("event") == "copy_trade_opened"]
    close_events = [e for e in log_entries if e.get("event") == "position_closed"]

    total_trades = len(trade_events)
    wins = sum(1 for e in close_events if float((e.get("position") or {}).get("realized_pnl") or 0) > 0)
    losses = len(close_events) - wins
    win_rate = wins / len(close_events) if close_events else 0.0

    total_pnl = sum(float((e.get("position") or {}).get("realized_pnl") or 0) for e in close_events)

    hold_hours = []
    for e in close_events:
        pos = e.get("position") or {}
        opened = pos.get("opened_at_ts")
        closed = pos.get("closed_at")
        if opened and closed:
            try:
                closed_ts = datetime.fromisoformat(closed.replace("Z", "+00:00")).timestamp()
                hold_hours.append((closed_ts - float(opened)) / 3600)
            except Exception:
                pass
    avg_hold = round(sum(hold_hours) / len(hold_hours), 1) if hold_hours else 0.0

    active = execution_state.get("active_positions", {})
    open_count = sum(1 for p in active.values() if p.get("status") == "open")
    daily_count = common.count_todays_trades(execution_state)

    whale_list = {}
    if common.WHALE_LIST_PATH.exists():
        whale_list = common.read_json(common.WHALE_LIST_PATH)

    # Live pUSD balance from deposit wallet
    balance_usdc = 0.0
    try:
        import os, requests as _req
        common.load_env()
        key = common.get_private_key().strip()
        funder = os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None
        addr = funder or ""
        if addr:
            PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
            data = "0x70a08231000000000000000000000000" + addr.lower().removeprefix("0x")
            r = _req.post("https://polygon-bor-rpc.publicnode.com", json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": PUSD, "data": data}, "latest"], "id": 1,
            }, timeout=5)
            balance_usdc = int(r.json().get("result", "0x0"), 16) / 1e6
    except Exception:
        pass

    invested_usdc = sum(
        float(p.get("size_usdc", 0))
        for p in active.values()
        if p.get("status") == "open"
    )

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "avg_hold_hours": avg_hold,
        "open_positions": open_count,
        "daily_trades": daily_count,
        "whale_count": len(whale_list.get("whales", [])),
        "execution_mode": execution_state.get("execution_mode", "dry_run"),
        "balance_usdc": round(balance_usdc, 2),
        "invested_usdc": round(invested_usdc, 2),
    }


def _classify_market(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["bitcoin", "btc", "eth", "crypto", "solana", "doge", "xrp", "coinbase", "binance", "token", "blockchain"]):
        return "Crypto"
    if any(k in t for k in ["trump", "biden", "harris", "president", "election", "democrat", "republican", "senate", "congress", "vote", "political", "fed ", "federal reserve", "tariff", "nato"]):
        return "Politics"
    if any(k in t for k in ["nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball", "baseball", "tennis", "golf", "ufc", "mma", "world cup", "champion", "playoff", "super bowl", "fifa"]):
        return "Sports"
    if any(k in t for k in ["ai ", "openai", "gpt", "llm", "anthropic", "google", "apple", "microsoft", "meta ", "nvidia", "tech", "startup"]):
        return "Tech"
    if any(k in t for k in ["oil", "gold", "inflation", "gdp", "recession", "rate", "economy", "market cap", "s&p", "nasdaq", "dow"]):
        return "Economy"
    return "Other"


@router.get("/heatmap")
def get_heatmap():
    """Category heat map: top markets by volume grouped by category."""
    import requests as _req
    from collections import defaultdict

    try:
        r = _req.get("https://gamma-api.polymarket.com/events",
                     params={"limit": 200, "active": "true", "closed": "false",
                             "order": "volume", "ascending": "false"}, timeout=10)
        events = r.json()
    except Exception:
        return []

    cats: dict[str, dict] = defaultdict(lambda: {"volume": 0.0, "liquidity": 0.0, "count": 0, "markets": []})

    for e in events:
        title = e.get("title") or ""
        vol = float(e.get("volume") or 0)
        liq = float(e.get("liquidity") or 0)
        cat = _classify_market(title)
        cats[cat]["volume"] += vol
        cats[cat]["liquidity"] += liq
        cats[cat]["count"] += 1
        cats[cat]["markets"].append({"title": title[:60], "volume": round(vol), "liquidity": round(liq)})

    result = []
    for cat, data in sorted(cats.items(), key=lambda x: -x[1]["volume"]):
        top3 = sorted(data["markets"], key=lambda x: -x["volume"])[:3]
        result.append({
            "category": cat,
            "volume": round(data["volume"]),
            "liquidity": round(data["liquidity"]),
            "market_count": data["count"],
            "top_markets": top3,
        })
    return result
