#!/usr/bin/env python3
"""
Main monitoring daemon. Polls whale wallets for new trades and copies them.

Run (dry-run — no orders placed):
    python monitor.py

Run (live — places real orders):
    python monitor.py --execute

Run (live without AI consensus check):
    python monitor.py --execute --no-consensus

Designed to be invoked every 60 seconds via launchd/cron.
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import common
from consensus import run_consensus
from notify import send_trade_opened
from polymarket_client import PolymarketClient

USE_CONSENSUS = True  # overridden by --no-consensus flag

MAX_TRADES_PER_DAY = int(os.getenv("POLYMARKET_MAX_TRADES_PER_DAY", "10"))
MIN_LIQUIDITY = float(os.getenv("POLYMARKET_MIN_LIQUIDITY", "10000"))
HOURS_BEFORE_CLOSE = float(os.getenv("POLYMARKET_HOURS_BEFORE_CLOSE", "72"))
HOURS_MAX_TO_CLOSE = float(os.getenv("POLYMARKET_HOURS_MAX_TO_CLOSE", "1080"))  # 45 days
POSITION_PCT = float(os.getenv("POLYMARKET_POSITION_PCT", "0.02"))
PROFIT_TARGET_PCT = float(os.getenv("POLYMARKET_PROFIT_TARGET_PCT", "0.25"))
KEEP_LAST_SEEN = 200  # max trade IDs to remember per whale

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("monitor")


def _build_client() -> PolymarketClient:
    common.load_env()
    private_key = common.get_private_key()
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
    api_secret = os.getenv("POLYMARKET_API_SECRET", "").strip()
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

    if not common.has_real_value(private_key):
        raise RuntimeError("POLYMARKET_PRIVATE_KEY is not set in .env")

    funder = os.getenv("POLYMARKET_FUNDER_ADDRESS", "").strip() or None
    client = PolymarketClient(private_key=private_key, chain_id=chain_id, funder=funder)
    if common.has_real_value(api_key):
        client.set_api_credentials(api_key, api_secret, api_passphrase)
    else:
        creds = client.create_or_derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
    return client


def _poll_whale(
    client: PolymarketClient,
    address: str,
    known_ids: set[str],
) -> list[dict]:
    trades = client.get_trades(maker_address=address, limit=20)
    return [t for t in trades if t.get("id") not in known_ids]


def _is_tradeable(
    trade: dict,
    client: PolymarketClient,
    execution_state: dict,
) -> dict | None:
    if (trade.get("side") or "").upper() != "BUY":
        return None

    token_id = trade.get("asset_id") or trade.get("token_id") or ""
    condition_id = trade.get("market") or trade.get("condition_id") or ""

    active = execution_state.get("active_positions", {})
    if any(p.get("token_id") == token_id for p in active.values()):
        log.debug(f"Already holding token {token_id[:12]}... — skip")
        return None

    if common.count_todays_trades(execution_state) >= MAX_TRADES_PER_DAY:
        log.info("Daily trade limit reached — skipping signal")
        return None

    try:
        market = client.get_market(condition_id)
    except RuntimeError as exc:
        log.warning(f"Failed to fetch market {condition_id}: {exc}")
        return None

    liquidity = float(market.get("liquidity") or 0)
    if liquidity < MIN_LIQUIDITY:
        log.debug(f"Market liquidity ${liquidity:,.0f} < ${MIN_LIQUIDITY:,.0f} — skip")
        return None

    end_date_iso = market.get("end_date_iso") or market.get("endDateIso") or ""
    if not end_date_iso:
        log.debug("No end_date_iso on market — skip")
        return None

    hours_left = PolymarketClient.hours_until_end(end_date_iso)
    if hours_left <= HOURS_BEFORE_CLOSE:
        log.debug(f"Only {hours_left:.1f}h until close — skip")
        return None
    if hours_left > HOURS_MAX_TO_CLOSE:
        log.debug(f"{hours_left:.0f}h until close — too far out (max {HOURS_MAX_TO_CLOSE:.0f}h), skip")
        return None

    return {
        **trade,
        "token_id": token_id,
        "condition_id": condition_id,
        "market_question": market.get("question") or market.get("title") or "",
        "market_liquidity": liquidity,
        "end_date_iso": end_date_iso,
    }


def _execute_copy_trade(
    client: PolymarketClient,
    signal: dict,
    whale: dict,
    execution_state: dict,
    execute: bool,
) -> None:
    token_id = signal["token_id"]
    condition_id = signal["condition_id"]
    whale_price = float(signal.get("price") or 0)
    whale_size = float(signal.get("size") or 0)  # shares
    whale_usdc = whale_price * whale_size

    try:
        book = client.get_book(token_id)
        asks = book.get("asks") or []
        if not asks:
            log.warning(f"Empty order book for {token_id[:12]}... — skip")
            return
        best_ask = float(sorted(asks, key=lambda x: float(x.get("price", 1)))[0]["price"])
        entry_price = best_ask
    except RuntimeError as exc:
        log.warning(f"Failed to get book for {token_id[:12]}...: {exc}")
        return

    if entry_price <= 0 or entry_price >= 1:
        log.warning(f"Invalid entry price {entry_price} — skip")
        return

    usdc_balance = common.get_capital(client) if execute else 10_000.0
    if execute and usdc_balance < 1.0:
        log.warning("USDC balance too low — check wallet has funds on Polygon")
        return
    size_usdc = min(usdc_balance * POSITION_PCT, whale_usdc)
    size_usdc = round(size_usdc, 2)

    if size_usdc < 1.0:
        log.warning(f"Position size ${size_usdc:.2f} too small")
        return

    size_shares = round(size_usdc / entry_price, 4)
    profit_target_price = round(entry_price * (1 + PROFIT_TARGET_PCT), 4)
    position_id = f"{token_id[:16]}-{int(time.time())}"

    position_record = {
        "position_id": position_id,
        "token_id": token_id,
        "condition_id": condition_id,
        "market_question": signal["market_question"],
        "whale_address": whale["address"],
        "whale_win_rate": whale["win_rate"],
        "whale_entry_size_shares": whale_size,
        "side": "BUY",
        "entry_price": entry_price,
        "size_usdc": size_usdc,
        "size_shares": size_shares,
        "profit_target_price": profit_target_price,
        "end_date_iso": signal["end_date_iso"],
        "opened_at": common.iso_now(),
        "opened_at_ts": int(time.time()),
        "status": "open",
        "order_id": None,
    }

    log.info(
        f"{'[EXECUTE]' if execute else '[DRY-RUN]'} Copy trade: "
        f"{signal['market_question'][:60]} | "
        f"price={entry_price:.3f} | "
        f"size=${size_usdc:.2f} | "
        f"whale={whale['address'][:10]}..."
    )

    order_resp: dict = {}
    if execute:
        try:
            order_resp = client.place_limit_order(
                token_id=token_id,
                side="BUY",
                price=entry_price,
                size_usdc=size_usdc,
            )
            position_record["order_id"] = order_resp.get("orderID") or order_resp.get("order_id")
            log.info(f"Order placed: {position_record['order_id']}")
        except RuntimeError as exc:
            log.error(f"Order failed: {exc}")
            common.log_event("monitor", common.new_run_id("monitor"), "order_failed", error=str(exc), signal=signal)
            return

    execution_state["active_positions"][position_id] = position_record
    common.record_trade_today(execution_state)
    common.save_execution_state(execution_state)

    send_trade_opened(position_record, strategy="whale")
    common.append_jsonl(
        common.EXECUTION_LOG_PATH,
        {
            "event": "copy_trade_opened",
            "time": common.iso_now(),
            "execute": execute,
            "position": position_record,
            "order_response": order_resp,
        },
    )

    common.log_event(
        "monitor",
        common.new_run_id("monitor"),
        "copy_trade_opened",
        position_id=position_id,
        execute=execute,
        whale=whale["address"],
        market=signal["market_question"][:80],
        entry_price=entry_price,
        size_usdc=size_usdc,
    )


def run(execute: bool = False) -> None:
    client = _build_client()
    run_id = common.new_run_id("monitor")
    common.log_event("monitor", run_id, "start", execute=execute)

    if not common.WHALE_LIST_PATH.exists():
        log.error("runtime/whale_list.json not found — run select_whales.py first.")
        sys.exit(1)

    whale_data = common.read_json(common.WHALE_LIST_PATH)
    whales = whale_data.get("whales", [])
    log.info(f"Monitoring {len(whales)} whale wallets")

    monitor_state = common.load_monitor_state()
    execution_state = common.load_execution_state()
    if execute:
        execution_state["execution_mode"] = "execute"

    signals_found = 0
    trades_placed = 0

    for whale in whales:
        addr = whale["address"]
        known_ids: set[str] = set(monitor_state["last_seen_trade_ids"].get(addr, []))

        try:
            new_trades = _poll_whale(client, addr, known_ids)
        except RuntimeError as exc:
            log.warning(f"Failed to poll {addr[:10]}...: {exc}")
            continue

        for trade in new_trades:
            trade_id = trade.get("id", "")
            known_ids.add(trade_id)

            signal = _is_tradeable(trade, client, execution_state)
            if signal:
                signals_found += 1

                # Run 3-agent AI consensus before placing any trade
                if USE_CONSENSUS and common.has_real_value(os.getenv("ANTHROPIC_API_KEY", "")):
                    try:
                        result = run_consensus(signal, whale)
                        log.info(f"Consensus: {result.summary}")
                        if not result.approved:
                            log.info(f"Consensus REJECTED — skipping trade")
                            continue
                    except Exception as exc:
                        log.warning(f"Consensus check failed ({exc}) — proceeding without it")

                _execute_copy_trade(client, signal, whale, execution_state, execute)
                trades_placed += 1

        # Keep last KEEP_LAST_SEEN IDs per whale
        monitor_state["last_seen_trade_ids"][addr] = list(known_ids)[-KEEP_LAST_SEEN:]

    common.save_monitor_state(monitor_state)
    common.save_execution_state(execution_state)

    log.info(f"Poll complete | signals={signals_found} | trades={'placed' if execute else 'dry-run'}: {trades_placed}")
    common.log_event("monitor", run_id, "complete", signals=signals_found, trades=trades_placed, execute=execute)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Place real orders. Default: dry-run.")
    parser.add_argument("--no-consensus", action="store_true", help="Skip AI consensus check.")
    args = parser.parse_args()
    if args.no_consensus:
        USE_CONSENSUS = False  # noqa: F811
    try:
        run(execute=args.execute)
    except Exception as exc:
        log.error(f"Monitor failed: {exc}")
        common.log_event("monitor", common.new_run_id("monitor"), "failed", error=str(exc))
        sys.exit(1)
