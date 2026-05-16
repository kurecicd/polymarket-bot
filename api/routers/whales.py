import json
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests as _req
from fastapi import APIRouter, HTTPException

import common

router = APIRouter()

_positions_cache: dict = {"data": None, "ts": 0}
_CACHE_TTL = 300  # 5-minute cache — 40 parallel HTTP calls


@router.get("")
def get_whales():
    if not common.WHALE_LIST_PATH.exists():
        raise HTTPException(status_code=404, detail="Whale list not generated yet.")
    return common.read_json(common.WHALE_LIST_PATH)


@router.get("/monitor-state")
def get_monitor_state():
    state = common.load_monitor_state()
    return {
        "last_poll_at": state.get("last_poll_at"),
        "wallets_tracked": len(state.get("last_seen_trade_ids", {})),
        "total_seen_trades": sum(len(v) for v in state.get("last_seen_trade_ids", {}).values()),
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


def _days_left(end_date: str) -> float | None:
    if not end_date:
        return None
    try:
        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        return round((end_dt - datetime.now(timezone.utc)).total_seconds() / 86400, 1)
    except Exception:
        return None


def _load_consensus_events() -> list[dict]:
    """Read up to 500 vote_complete events from event_log, newest first."""
    if not common.EVENT_LOG_PATH.exists():
        return []
    events = []
    try:
        for line in reversed(common.EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("event") == "vote_complete":
                    events.append(e)
                    if len(events) >= 500:
                        break
            except Exception:
                pass
    except Exception:
        pass
    return events


def _match_consensus(title: str, events: list[dict]) -> dict | None:
    key = title.lower().strip()[:40]
    if not key:
        return None
    for e in events:
        ev_market = (e.get("details", {}).get("market") or "").lower().strip()
        if ev_market and (key[:35] in ev_market or ev_market[:35] in key):
            d = e.get("details", {})
            return {
                "time": e.get("time"),
                "approved": d.get("approved"),
                "buy_count": d.get("buy_count"),
                "votes": d.get("votes", []),
            }
    return None


@router.get("/live-positions")
def get_whale_live_positions():
    """
    Returns:
      - by_market: markets sorted by number of whales holding them (≥2 whales, grouped by condition_id+outcome)
      - by_whale: each whale's current portfolio (all 40 whales, all positions)
    Cached 5 minutes.
    """
    global _positions_cache
    if _positions_cache["data"] is not None and time.time() - _positions_cache["ts"] < _CACHE_TTL:
        return _positions_cache["data"]

    if not common.WHALE_LIST_PATH.exists():
        return {"by_market": [], "by_whale": []}

    whale_meta = {w["address"]: w for w in common.read_json(common.WHALE_LIST_PATH).get("whales", [])}
    if not whale_meta:
        return {"by_market": [], "by_whale": []}

    # Fetch all whale positions in parallel
    raw: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_positions, addr): addr for addr in whale_meta}
        for future in as_completed(futures):
            addr = futures[future]
            try:
                result = future.result()
                raw[addr] = result if result else []
            except Exception:
                raw[addr] = []

    # ── per_market grouping (by condition_id + outcome so YES/NO are separate) ──
    by_market: dict[str, dict] = {}

    for address, positions in raw.items():
        for pos in positions:
            cid = pos.get("conditionId") or pos.get("condition_id") or ""
            if not cid:
                continue
            size = float(pos.get("size") or 0)
            if size <= 0:
                continue
            value = float(pos.get("currentValue") or pos.get("value") or 0)
            price = float(pos.get("pricePerShare") or pos.get("price") or 0)
            title = pos.get("title") or pos.get("question") or ""
            outcome = (pos.get("outcome") or "YES").upper()
            end_date = pos.get("endDate") or pos.get("end_date_iso") or ""
            asset = pos.get("asset") or pos.get("token_id") or ""

            key = f"{cid}|{outcome}"
            if key not in by_market:
                by_market[key] = {
                    "condition_id": cid,
                    "token_id": asset,
                    "title": title,
                    "outcome": outcome,
                    "end_date": end_date,
                    "total_value": 0.0,
                    "whales": [],
                }
            m = by_market[key]
            if not m["title"] and title:
                m["title"] = title
            if not m["end_date"] and end_date:
                m["end_date"] = end_date
            if not m["token_id"] and asset:
                m["token_id"] = asset
            m["total_value"] = round(m["total_value"] + value, 2)
            if address not in {w["address"] for w in m["whales"]}:
                m["whales"].append({
                    "address": address,
                    "value": round(value, 2),
                    "size": round(size, 2),
                    "price": round(price, 4),
                })

    consensus_events = _load_consensus_events()

    market_list = []
    for m in by_market.values():
        whale_count = len(m["whales"])
        if whale_count < 2:
            continue
        prices = [w["price"] for w in m["whales"] if w["price"] > 0]
        avg_price = round(sum(prices) / len(prices), 4) if prices else 0.0
        market_list.append({
            "condition_id": m["condition_id"],
            "token_id": m["token_id"],
            "title": m["title"],
            "outcome": m["outcome"],
            "whale_count": whale_count,
            "total_whale_value": m["total_value"],
            "avg_price": avg_price,
            "end_date": m["end_date"],
            "days_left": _days_left(m["end_date"]),
            "whales": sorted(m["whales"], key=lambda x: -x["value"])[:5],
            "consensus": _match_consensus(m["title"], consensus_events),
        })

    market_list.sort(key=lambda x: (-x["whale_count"], -x["total_whale_value"]))

    # ── per_whale portfolio ──
    whale_list = []
    for address, positions in raw.items():
        meta = whale_meta.get(address, {})
        whale_positions = []
        for pos in positions:
            size = float(pos.get("size") or 0)
            if size <= 0:
                continue
            value = float(pos.get("currentValue") or pos.get("value") or 0)
            price = float(pos.get("pricePerShare") or pos.get("price") or 0)
            end_date = pos.get("endDate") or pos.get("end_date_iso") or ""
            whale_positions.append({
                "title": pos.get("title") or pos.get("question") or "",
                "outcome": (pos.get("outcome") or "YES").upper(),
                "price": round(price, 4),
                "size": round(size, 2),
                "value": round(value, 2),
                "end_date": end_date,
                "days_left": _days_left(end_date),
                "condition_id": pos.get("conditionId") or pos.get("condition_id") or "",
            })
        whale_positions.sort(key=lambda x: -x["value"])
        if whale_positions:  # only include whales that hold something
            whale_list.append({
                "address": address,
                "roi_pct": meta.get("roi_pct", 0),
                "total_profit_usdc": meta.get("total_profit_usdc", 0),
                "position_count": len(whale_positions),
                "positions": whale_positions,
            })

    whale_list.sort(key=lambda x: (-x["roi_pct"], -x["position_count"]))

    result = {"by_market": market_list, "by_whale": whale_list}
    _positions_cache["data"] = result
    _positions_cache["ts"] = time.time()
    return result


@router.post("/live-positions/analyze")
def analyze_whale_positions(execute: bool = False):
    """
    Run 3-agent consensus on the top whale-concentration markets.
    If execute=True and consensus approves, places a BUY order.
    """
    from polymarket_client import PolymarketClient
    from consensus import run_consensus

    common.load_env()

    cached = get_whale_live_positions()
    markets = cached.get("by_market", []) if isinstance(cached, dict) else []
    if not markets:
        return {"results": [], "message": "No whale positions found — refresh first"}

    try:
        key = common.get_private_key()
        funder = os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None
        client = PolymarketClient(
            private_key=key,
            chain_id=int(os.getenv("POLYMARKET_CHAIN_ID", "137")),
            funder=funder,
        )
        creds = client.create_or_derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
    except Exception as exc:
        return {"error": f"Could not build client: {exc}"}

    execution_state = common.load_execution_state()
    active = execution_state.get("active_positions", {})
    results = []

    MIN_WHALES_TO_TRADE = 3  # place a real trade only when ≥3 whales agree on same side
    # Consensus always runs for ≥2 whales (so results show in dashboard panel)

    for market in markets[:15]:  # check top 15 by whale count
        cid = market["condition_id"]
        title = market["title"]
        outcome = market["outcome"]

        # Skip if already holding this exact market+outcome
        already_in = any(
            p.get("condition_id") == cid and p.get("status") == "open"
            for p in active.values()
        )
        if already_in:
            results.append({"market": title[:60], "status": "already_holding", "outcome": outcome})
            continue

        # Fetch market from CLOB to get live data
        try:
            clob_market = client.get_market(cid)
        except Exception as exc:
            results.append({"market": title[:60], "status": "fetch_failed", "error": str(exc)[:100]})
            continue

        end_date = clob_market.get("end_date_iso") or clob_market.get("endDateIso") or ""
        if not end_date:
            results.append({"market": title[:60], "status": "filtered", "reason": "no end date"})
            continue

        hours_left = PolymarketClient.hours_until_end(end_date)
        if hours_left <= 72:
            results.append({"market": title[:60], "status": "filtered", "reason": f"only {hours_left:.0f}h left"})
            continue
        if hours_left > 1080:
            results.append({"market": title[:60], "status": "filtered", "reason": "too far out (>45 days)"})
            continue

        liquidity = float(clob_market.get("liquidity") or 0)
        if liquidity < 10_000:
            results.append({"market": title[:60], "status": "filtered", "reason": f"low liquidity ${liquidity:.0f}"})
            continue

        # Find the right token_id for the desired outcome
        token_id = market.get("token_id") or ""
        if not token_id:
            for tok in (clob_market.get("tokens") or []):
                if (tok.get("outcome") or "").upper() == outcome:
                    token_id = tok.get("token_id", "")
                    break
        if not token_id:
            results.append({"market": title[:60], "status": "filtered", "reason": "no token ID"})
            continue

        # Get live best_ask from order book
        try:
            book = client.get_book(token_id)
            asks = book.get("asks") or []
            if not asks:
                results.append({"market": title[:60], "status": "filtered", "reason": "empty order book"})
                continue
            best_ask = float(min(asks, key=lambda x: float(x.get("price", 1)))["price"])
        except Exception:
            results.append({"market": title[:60], "status": "filtered", "reason": "book fetch failed"})
            continue

        if best_ask <= 0.10 or best_ask >= 0.90:
            results.append({"market": title[:60], "status": "filtered", "reason": f"price {best_ask:.2f} outside 10-90%"})
            continue

        # Build signal and run 3-agent consensus
        signal = {
            "market_question": title,
            "market_liquidity": liquidity,
            "end_date_iso": end_date,
            "token_id": token_id,
            "condition_id": cid,
            "price": str(best_ask),
            "size": str(market["total_whale_value"]),
            "hours_left": hours_left,
        }
        whale_summary = {
            "address": f"{market['whale_count']}_tracked_whales",
            "roi_pct": 0,
            "win_rate": None,
            "total_profit_usdc": market["total_whale_value"],
            "total_trades": market["whale_count"],
            "avg_position_size_usdc": round(market["total_whale_value"] / max(market["whale_count"], 1), 2),
        }

        try:
            consensus_result = run_consensus(signal, whale_summary)
            approved = consensus_result.approved
            vote_details = [
                {
                    "agent": v.agent,
                    "decision": v.decision,
                    "confidence": v.confidence,
                    "reasoning": v.reasoning,
                }
                for v in consensus_result.votes
            ]
        except Exception as exc:
            results.append({"market": title[:60], "status": "consensus_failed", "error": str(exc)[:100]})
            continue

        entry = {
            "market": title[:60],
            "outcome": outcome,
            "whale_count": market["whale_count"],
            "price": best_ask,
            "status": "approved" if approved else "rejected",
            "buy_count": consensus_result.buy_count,
            "votes": vote_details,
        }

        if approved and execute and market["whale_count"] >= MIN_WHALES_TO_TRADE:
            try:
                import time as _t
                usdc_balance = common.get_capital(client)
                size_usdc = round(max(usdc_balance * 0.02, 5.5 * best_ask), 2)
                order_resp = client.place_limit_order(
                    token_id=token_id, side="BUY", price=best_ask, size_usdc=size_usdc
                )
                pid = f"wp-{token_id[:12]}-{int(_t.time())}"
                position_record = {
                    "position_id": pid,
                    "token_id": token_id,
                    "condition_id": cid,
                    "market_question": title,
                    "whale_address": f"whale_positions_{market['whale_count']}x",
                    "whale_win_rate": None,
                    "whale_entry_size_shares": 0.0,
                    "side": "BUY",
                    "entry_price": best_ask,
                    "size_usdc": size_usdc,
                    "size_shares": round(size_usdc / best_ask, 4),
                    "profit_target_price": round(best_ask * 1.20, 4),
                    "end_date_iso": end_date,
                    "opened_at": common.iso_now(),
                    "opened_at_ts": int(_t.time()),
                    "status": "open",
                    "strategy": "whale_positions",
                    "order_id": order_resp.get("orderID") or order_resp.get("order_id"),
                }
                execution_state.setdefault("active_positions", {})[pid] = position_record
                common.record_trade_today(execution_state)
                common.save_execution_state(execution_state)
                common.append_jsonl(common.EXECUTION_LOG_PATH, {
                    "event": "copy_trade_opened",
                    "time": common.iso_now(),
                    "execute": True,
                    "position": position_record,
                    "order_response": order_resp,
                })
                entry["traded"] = True
                entry["order_id"] = position_record["order_id"]
            except Exception as exc:
                entry["trade_error"] = str(exc)[:200]

        results.append(entry)

    # Bust cache so next GET shows fresh consensus data
    _positions_cache["ts"] = 0

    common.log_event("dashboard", "ANALYZE_WHALE_POSITIONS", "button_press",
                     execute=execute, markets_analyzed=len(results))
    return {"results": results, "execute": execute}
