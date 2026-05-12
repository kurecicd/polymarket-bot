#!/usr/bin/env python3
"""
Checks all open positions for exit conditions and closes them when triggered.

Three exit conditions (evaluated in priority order):
  A. profit_target   — current price >= entry_price * 1.25
  B. whale_exiting   — whale has sold >30% of their entry shares since our entry
  C. market_closing  — market resolves within 72h

Run (dry-run):
    python position_manager.py

Run (live):
    python position_manager.py --execute

Designed to run every 5 minutes via launchd/cron.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import common
from notify import send_trade_closed
from polymarket_client import PolymarketClient

PROFIT_TARGET_PCT = float(os.getenv("POLYMARKET_PROFIT_TARGET_PCT", "0.25"))
WHALE_SHRINK_THRESH = float(os.getenv("POLYMARKET_WHALE_SHRINK_THRESH", "0.30"))
HOURS_BEFORE_CLOSE = float(os.getenv("POLYMARKET_HOURS_BEFORE_CLOSE", "72"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("position_manager")


def _build_client() -> PolymarketClient:
    common.load_env()
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip().removeprefix("0x")
    chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
    api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
    api_secret = os.getenv("POLYMARKET_API_SECRET", "").strip()
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

    if not common.has_real_value(private_key):
        raise RuntimeError("POLYMARKET_PRIVATE_KEY is not set in .env")

    client = PolymarketClient(private_key=private_key, chain_id=chain_id)
    if common.has_real_value(api_key):
        client.set_api_credentials(api_key, api_secret, api_passphrase)
    else:
        creds = client.derive_api_key()
        client.set_api_credentials(creds["api_key"], creds["api_secret"], creds["api_passphrase"])
    return client


def _check_exit_reason(client: PolymarketClient, position: dict) -> str | None:
    token_id = position["token_id"]
    entry_price = float(position["entry_price"])
    profit_target = float(position.get("profit_target_price", entry_price * (1 + PROFIT_TARGET_PCT)))

    # A. Profit target
    try:
        current_price = client.get_last_trade_price(token_id)
        if current_price >= profit_target:
            log.info(
                f"Profit target hit: current={current_price:.3f} >= target={profit_target:.3f} "
                f"for {position.get('market_question', '')[:50]}"
            )
            return "profit_target"
    except RuntimeError as exc:
        log.warning(f"Could not get price for {token_id[:12]}...: {exc}")

    # B. Whale exiting (sold >30% of entry position since our entry)
    whale_address = position.get("whale_address")
    whale_entry_shares = float(position.get("whale_entry_size_shares", 0))
    opened_at_ts = int(position.get("opened_at_ts", 0))

    if whale_address and whale_entry_shares > 0:
        try:
            recent_trades = client.get_trades(maker_address=whale_address, limit=100)
            whale_sells = [
                t for t in recent_trades
                if (t.get("asset_id") or t.get("token_id")) == token_id
                and (t.get("side") or "").upper() == "SELL"
                and int(t.get("timestamp", 0)) > opened_at_ts
            ]
            shares_sold = sum(float(t.get("size") or 0) for t in whale_sells)
            reduction_pct = shares_sold / whale_entry_shares if whale_entry_shares > 0 else 0.0
            if reduction_pct >= WHALE_SHRINK_THRESH:
                log.info(
                    f"Whale exiting: sold {reduction_pct:.1%} of entry for "
                    f"{position.get('market_question', '')[:50]}"
                )
                return "whale_exiting"
        except RuntimeError as exc:
            log.warning(f"Could not check whale trades for {whale_address[:10]}...: {exc}")

    # C. Market closing soon
    end_date_iso = position.get("end_date_iso", "")
    if end_date_iso:
        hours_left = PolymarketClient.hours_until_end(end_date_iso)
        if hours_left <= HOURS_BEFORE_CLOSE:
            log.info(
                f"Market closing in {hours_left:.1f}h (<= {HOURS_BEFORE_CLOSE}h threshold) "
                f"for {position.get('market_question', '')[:50]}"
            )
            return "market_closing_soon"

    return None


def _close_position(
    client: PolymarketClient,
    position: dict,
    reason: str,
    execute: bool,
) -> None:
    token_id = position["token_id"]
    size_shares = float(position.get("size_shares", 0))

    log.info(
        f"{'[EXECUTE]' if execute else '[DRY-RUN]'} Closing position "
        f"reason={reason} | "
        f"{position.get('market_question', '')[:60]} | "
        f"shares={size_shares:.2f}"
    )

    current_price = 0.0
    order_resp: dict = {}

    if execute:
        try:
            current_price = client.get_last_trade_price(token_id)
            # Place aggressive limit sell at best bid (or slightly below)
            book = client.get_book(token_id)
            bids = book.get("bids") or []
            if bids:
                best_bid = float(sorted(bids, key=lambda x: -float(x.get("price", 0)))[0]["price"])
                sell_price = max(0.01, round(best_bid - 0.001, 4))
            else:
                sell_price = max(0.01, round(current_price * 0.98, 4))

            order_resp = client.place_limit_order(
                token_id=token_id,
                side="SELL",
                price=sell_price,
                size_usdc=size_shares,  # size_usdc param is used as shares for SELL
            )
            log.info(f"Sell order placed: {order_resp.get('orderID') or order_resp.get('order_id')}")
        except RuntimeError as exc:
            log.error(f"Sell order failed: {exc}")
            common.log_event(
                "position_manager",
                common.new_run_id("pm"),
                "sell_order_failed",
                error=str(exc),
                position_id=position.get("position_id"),
            )
            return

    realized_pnl = round(
        (current_price - float(position.get("entry_price", 0))) * size_shares, 2
    ) if current_price > 0 else None

    position["status"] = "closed"
    position["closed_at"] = common.iso_now()
    position["close_reason"] = reason
    position["exit_price"] = current_price or None
    position["realized_pnl"] = realized_pnl

    send_trade_closed(position, reason)
    common.append_jsonl(
        common.EXECUTION_LOG_PATH,
        {
            "event": "position_closed",
            "time": common.iso_now(),
            "execute": execute,
            "reason": reason,
            "position": position,
            "order_response": order_resp,
        },
    )

    common.log_event(
        "position_manager",
        common.new_run_id("pm"),
        "position_closed",
        position_id=position.get("position_id"),
        reason=reason,
        execute=execute,
        realized_pnl=realized_pnl,
    )


def run(execute: bool = False) -> None:
    client = _build_client()
    run_id = common.new_run_id("position-manager")
    common.log_event("position_manager", run_id, "start", execute=execute)

    execution_state = common.load_execution_state()
    active = execution_state.get("active_positions", {})

    if not active:
        log.info("No open positions to check.")
        common.log_event("position_manager", run_id, "complete", checked=0, closed=0)
        return

    log.info(f"Checking {len(active)} open position(s)")
    closed_count = 0

    for position_id, position in list(active.items()):
        if position.get("status") != "open":
            continue

        reason = _check_exit_reason(client, position)
        if reason:
            _close_position(client, position, reason, execute)
            active[position_id] = position
            if execute:
                # Mark completed
                completed = execution_state.setdefault("completed_position_ids", [])
                completed.append(position_id)
                if len(completed) > 200:
                    execution_state["completed_position_ids"] = completed[-200:]
            closed_count += 1
        else:
            try:
                current_price = client.get_last_trade_price(position["token_id"])
                entry = float(position["entry_price"])
                unrealized_pnl = round((current_price - entry) * float(position.get("size_shares", 0)), 2)
                log.info(
                    f"Hold: {position.get('market_question', '')[:50]} | "
                    f"entry={entry:.3f} current={current_price:.3f} "
                    f"unrealized_pnl=${unrealized_pnl:+.2f}"
                )
            except RuntimeError:
                log.info(f"Hold: {position_id}")

    execution_state["active_positions"] = active
    common.save_execution_state(execution_state)

    log.info(f"Done | checked={len(active)} | closed={closed_count}")
    common.log_event("position_manager", run_id, "complete", checked=len(active), closed=closed_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Place real sell orders. Default: dry-run.")
    args = parser.parse_args()
    try:
        run(execute=args.execute)
    except Exception as exc:
        log.error(f"Position manager failed: {exc}")
        common.log_event("position_manager", common.new_run_id("pm"), "failed", error=str(exc))
        sys.exit(1)
