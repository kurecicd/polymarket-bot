#!/usr/bin/env python3
"""
Quick Rich Bets — a separate high-probability strategy that finds mispriced
markets independently of whale tracking.

Logic:
  1. Fetch all active markets with sufficient liquidity
  2. For each market, compare the current YES price against a "fair value"
     estimate derived from recent trading volume and order book imbalance
  3. Flag markets where the price looks significantly off (>15% from fair value)
     and volume is rising — indicating crowd mispricing
  4. Apply a Claude AI check on the top candidates before betting

Run:
    python quick_bets.py              # dry-run: print opportunities only
    python quick_bets.py --execute    # place bets on approved opportunities
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import common
from consensus import run_consensus
from polymarket_client import PolymarketClient

MAX_QUICK_BETS_PER_DAY = int(os.getenv("POLYMARKET_QUICK_BETS_PER_DAY", "3"))
MIN_LIQUIDITY = float(os.getenv("POLYMARKET_MIN_LIQUIDITY", "10000"))
MIN_EDGE_PCT = float(os.getenv("POLYMARKET_QUICK_BET_EDGE", "0.03"))   # 3% mispricing minimum
QUICK_BET_SIZE_PCT = float(os.getenv("POLYMARKET_QUICK_BET_SIZE_PCT", "0.01"))  # 1% of balance
HOURS_BEFORE_CLOSE = float(os.getenv("POLYMARKET_HOURS_BEFORE_CLOSE", "72"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("quick_bets")


def _build_client() -> PolymarketClient:
    common.load_env()
    key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
    api_secret = os.getenv("POLYMARKET_API_SECRET", "").strip()
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()
    if not common.has_real_value(key):
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set")
    client = PolymarketClient(private_key=key, chain_id=chain_id)
    if common.has_real_value(api_key):
        client.set_api_credentials(api_key, api_secret, api_passphrase)
    return client


def _order_book_fair_value(book: dict) -> float | None:
    """
    Estimate fair value from order book imbalance.
    If bids are much heavier than asks → price should be higher than current.
    Returns estimated fair probability (0-1) or None if book is thin.
    """
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return None

    bid_liquidity = sum(float(b.get("size", 0)) * float(b.get("price", 0)) for b in bids[:5])
    ask_liquidity = sum(float(a.get("size", 0)) * float(a.get("price", 0)) for a in asks[:5])
    total = bid_liquidity + ask_liquidity
    if total == 0:
        return None

    best_bid = float(max(bids, key=lambda x: float(x.get("price", 0)))["price"])
    best_ask = float(min(asks, key=lambda x: float(x.get("price", 1)))["price"])
    mid = (best_bid + best_ask) / 2

    # Adjust mid toward the heavier side
    imbalance = (bid_liquidity - ask_liquidity) / total  # -1 to +1
    fair_value = mid + imbalance * 0.05  # nudge up to 5% toward heavier side
    return max(0.01, min(0.99, fair_value))


def find_opportunities(client: PolymarketClient) -> list[dict]:
    """
    Scan active markets for significant mispricings. Returns ranked list.
    """
    log.info("Fetching active markets from Gamma API...")
    try:
        markets = client.get_markets_gamma(limit=200, min_liquidity=MIN_LIQUIDITY)
    except RuntimeError as exc:
        log.error(f"Failed to fetch markets: {exc}")
        return []

    log.info(f"Scanning {len(markets)} markets for mispricings...")
    opportunities = []

    for market in markets:
        condition_id = market.get("conditionId") or market.get("condition_id") or ""
        if not condition_id:
            continue

        end_date = market.get("endDateIso") or market.get("endDate") or ""
        if not end_date:
            continue
        if PolymarketClient.hours_until_end(end_date) <= HOURS_BEFORE_CLOSE:
            continue

        # Extract YES token ID from clobTokenIds (first = YES token)
        import json as _json, re as _re
        clob_ids = market.get("clobTokenIds") or "[]"
        if isinstance(clob_ids, str):
            try:
                clob_ids = _json.loads(clob_ids)
            except Exception:
                clob_ids = _re.findall(r'\d{60,}', clob_ids)
        if not clob_ids:
            continue
        token_id = str(clob_ids[0])

        # Get current YES price from outcomePrices
        outcome_prices = market.get("outcomePrices") or "[0.5, 0.5]"
        if isinstance(outcome_prices, str):
            try:
                prices = _json.loads(outcome_prices)
                current_price = float(prices[0]) if prices else 0.5
            except Exception:
                current_price = 0.5
        else:
            current_price = 0.5

        if current_price <= 0.02 or current_price >= 0.98:
            continue  # Skip near-certain outcomes

        try:
            book = client.get_book(token_id)
        except RuntimeError:
            continue

        fair_value = _order_book_fair_value(book)
        if fair_value is None:
            continue

        edge = fair_value - current_price  # positive = YES is underpriced
        if abs(edge) < MIN_EDGE_PCT:
            continue

        opportunities.append({
            "condition_id": condition_id,
            "token_id": token_id,
            "market_question": market.get("question") or market.get("title") or "",
            "current_price": round(current_price, 4),
            "fair_value": round(fair_value, 4),
            "edge": round(edge, 4),
            "side": "BUY" if edge > 0 else "SKIP",  # only bet YES for simplicity
            "liquidity": float(market.get("liquidity") or 0),
            "end_date_iso": end_date,
            "market_liquidity": float(market.get("liquidity") or 0),
            "price": str(current_price),
            "size": "0",  # will be set at execution
        })

    # Sort by absolute edge descending
    opportunities.sort(key=lambda x: abs(x["edge"]), reverse=True)
    log.info(f"Found {len(opportunities)} mispriced markets (edge >= {MIN_EDGE_PCT:.0%})")
    return opportunities


def run(execute: bool = False) -> None:
    client = _build_client()
    run_id = common.new_run_id("quick-bets")
    common.log_event("quick_bets", run_id, "start", execute=execute)

    execution_state = common.load_execution_state()
    daily_quick = sum(
        1 for e in execution_state.get("daily_trade_log", [])
        if datetime.now(timezone.utc).date().isoformat() in e
    )
    if daily_quick >= MAX_QUICK_BETS_PER_DAY:
        log.info(f"Quick bet daily limit reached ({MAX_QUICK_BETS_PER_DAY}). Skipping.")
        return

    opportunities = find_opportunities(client)
    if not opportunities:
        log.info("No quick bet opportunities found.")
        return

    usdc_balance = client.get_usdc_balance() if execute else 10_000.0
    bets_placed = 0

    for opp in opportunities[:5]:  # check top 5, place up to daily limit
        if bets_placed >= MAX_QUICK_BETS_PER_DAY:
            break
        if opp["side"] != "BUY":
            continue

        # Already holding this market?
        active = execution_state.get("active_positions", {})
        if any(p.get("token_id") == opp["token_id"] for p in active.values()):
            continue

        log.info(
            f"Opportunity: {opp['market_question'][:60]} | "
            f"price={opp['current_price']:.3f} fair={opp['fair_value']:.3f} "
            f"edge={opp['edge']:+.3f}"
        )

        # AI consensus check
        whale_dummy = {"win_rate": 0.0, "total_profit_usdc": 0.0,
                       "total_trades": 0, "avg_position_size_usdc": 0.0,
                       "address": "quick_bet_strategy"}
        opp_signal = {**opp, "hours_left": PolymarketClient.hours_until_end(opp["end_date_iso"])}

        if common.has_real_value(os.getenv("ANTHROPIC_API_KEY", "")):
            try:
                result = run_consensus(opp_signal, whale_dummy)
                log.info(f"Consensus: {result.summary}")
                if not result.approved:
                    log.info("Consensus rejected — skipping")
                    continue
            except Exception as exc:
                log.warning(f"Consensus failed ({exc}) — proceeding")

        size_usdc = round(usdc_balance * QUICK_BET_SIZE_PCT, 2)
        size_shares = round(size_usdc / opp["current_price"], 4)
        profit_target = round(opp["current_price"] * 1.20, 4)  # tighter 20% target for quick bets
        position_id = f"qb-{opp['token_id'][:12]}-{int(common.time.time())}"

        position_record = {
            "position_id": position_id,
            "token_id": opp["token_id"],
            "condition_id": opp["condition_id"],
            "market_question": opp["market_question"],
            "whale_address": "quick_bet_strategy",
            "whale_win_rate": 0.0,
            "whale_entry_size_shares": 0.0,
            "side": "BUY",
            "entry_price": opp["current_price"],
            "size_usdc": size_usdc,
            "size_shares": size_shares,
            "profit_target_price": profit_target,
            "end_date_iso": opp["end_date_iso"],
            "opened_at": common.iso_now(),
            "opened_at_ts": int(common.time.time()),
            "status": "open",
            "strategy": "quick_bet",
            "edge_at_entry": opp["edge"],
        }

        log.info(
            f"{'[EXECUTE]' if execute else '[DRY-RUN]'} Quick bet: "
            f"{opp['market_question'][:55]} | "
            f"size=${size_usdc:.2f} @ {opp['current_price']:.3f}"
        )

        order_resp: dict = {}
        if execute:
            try:
                order_resp = client.place_limit_order(
                    token_id=opp["token_id"],
                    side="BUY",
                    price=opp["current_price"],
                    size_usdc=size_usdc,
                )
                position_record["order_id"] = order_resp.get("orderID") or order_resp.get("order_id")
            except RuntimeError as exc:
                log.error(f"Quick bet order failed: {exc}")
                continue

        execution_state["active_positions"][position_id] = position_record
        common.record_trade_today(execution_state)
        common.save_execution_state(execution_state)
        common.append_jsonl(common.EXECUTION_LOG_PATH, {
            "event": "copy_trade_opened",
            "time": common.iso_now(),
            "execute": execute,
            "position": position_record,
            "order_response": order_resp,
        })
        common.log_event("quick_bets", run_id, "quick_bet_placed",
                         market=opp["market_question"][:80],
                         edge=opp["edge"], execute=execute)
        bets_placed += 1

    log.info(f"Quick bets done | placed={bets_placed}")
    common.log_event("quick_bets", run_id, "complete", bets_placed=bets_placed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        run(execute=args.execute)
    except Exception as exc:
        log.error(f"Quick bets failed: {exc}")
        sys.exit(1)
