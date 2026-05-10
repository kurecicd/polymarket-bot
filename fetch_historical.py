#!/usr/bin/env python3
"""
Fetches historical trade data from Polymarket's public data API.
No authentication required.

Strategy:
  1. Pull global trades feed (3000 recent trades) → collect ~1000 unique wallet addresses
  2. For each wallet, fetch their full trade history (up to 3500 trades per wallet)
  3. Save all trades to data/trades_raw.parquet
  4. rank_wallets.py then computes win rates and selects top performers

Run:
    python fetch_historical.py              # default: top 200 wallets
    python fetch_historical.py --wallets 500
"""
import argparse
import logging
import os
import sys
import time

import pandas as pd
import requests

import common

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_historical")

DATA_API = "https://data-api.polymarket.com"
OUTPUT_PATH = common.DATA_DIR / "trades_raw.parquet"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "polymarket-whale-bot/1.0"


def _get(url: str, params: dict, retries: int = 3) -> list | dict:
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return []


def _collect_from_endpoint(params_list: list[dict]) -> set[str]:
    """Collect wallet addresses by paginating through multiple parameter sets."""
    wallets: set[str] = set()
    for params in params_list:
        for offset in range(0, 3001, 500):
            try:
                p = {**params, "limit": 500, "offset": offset}
                data = _get(f"{DATA_API}/trades", p)
                if not isinstance(data, list) or not data:
                    break
                for trade in data:
                    addr = trade.get("proxyWallet", "")
                    if addr and addr.startswith("0x"):
                        wallets.add(addr.lower())
                if len(data) < 500:
                    break
                time.sleep(0.15)
            except Exception as exc:
                log.debug(f"Fetch error: {exc}")
                break
    return wallets


def collect_wallet_addresses(max_wallets: int = 500) -> set[str]:
    """
    Collect unique wallet addresses from:
    1. Global trades feed (recent 3000 trades)
    2. Top events by volume (historical high-activity markets)
    """
    wallets: set[str] = set()

    # Source 1: Global trades feed
    log.info("Collecting from global trades feed...")
    global_wallets = _collect_from_endpoint([{}])
    wallets.update(global_wallets)
    log.info(f"  Global feed: {len(wallets)} unique wallets")

    # Source 2: Top events by volume (these have the most active traders)
    log.info("Collecting from top events...")
    try:
        events_r = _get("https://gamma-api.polymarket.com/events",
                        {"limit": 100, "order": "volume", "ascending": "false"})
        if isinstance(events_r, list):
            event_params = [{"eventSlug": e.get("slug", "")}
                           for e in events_r if e.get("slug")]
            event_wallets = _collect_from_endpoint(event_params[:50])
            new = event_wallets - wallets
            wallets.update(event_wallets)
            log.info(f"  Top events: +{len(new)} new wallets (total: {len(wallets)})")
    except Exception as exc:
        log.warning(f"Event collection failed: {exc}")

    if len(wallets) > max_wallets:
        wallets = set(list(wallets)[:max_wallets])

    log.info(f"Total unique wallet addresses collected: {len(wallets)}")
    return wallets


def fetch_wallet_trades(address: str) -> list[dict]:
    """Fetch full trade history for a single wallet."""
    all_trades = []
    for offset in range(0, 3500, 500):
        try:
            data = _get(f"{DATA_API}/trades", {
                "user": address,
                "limit": 500,
                "offset": offset,
            })
            if not isinstance(data, list) or not data:
                break
            all_trades.extend(data)
            if len(data) < 500:
                break
            time.sleep(0.1)
        except Exception as exc:
            log.debug(f"Error fetching trades for {address[:12]}: {exc}")
            break
    return all_trades


def parse_trade(trade: dict) -> dict | None:
    """Convert API trade record to our standard format."""
    try:
        side = (trade.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            return None
        price = float(trade.get("price") or 0)
        size = float(trade.get("size") or 0)
        if price <= 0 or size <= 0:
            return None
        maker = (trade.get("proxyWallet") or "").lower()
        if not maker or not maker.startswith("0x"):
            return None

        return {
            "trade_id": str(trade.get("transactionHash") or "") + str(trade.get("asset") or ""),
            "timestamp": int(trade.get("timestamp") or 0),
            "block_number": 0,
            "maker_address": maker,
            "taker_address": "",
            "token_id": str(trade.get("asset") or ""),
            "condition_id": str(trade.get("conditionId") or ""),
            "market_question": str(trade.get("title") or "")[:120],
            "end_timestamp": 0,
            "side": side,
            "price": price,
            "size_shares": size,
            "usdc_amount": round(price * size, 6),
            "outcome": str(trade.get("outcome") or ""),
            "outcome_index": int(trade.get("outcomeIndex") or 0),
        }
    except Exception:
        return None


def main(max_wallets: int = 200) -> None:
    common.load_env()
    run_id = common.new_run_id("fetch-historical")
    common.log_event("fetch_historical", run_id, "start", max_wallets=max_wallets)

    # Load existing data
    existing_ids: set[str] = set()
    existing_df = pd.DataFrame()
    if OUTPUT_PATH.exists():
        existing_df = pd.read_parquet(OUTPUT_PATH)
        existing_ids = set(existing_df["trade_id"].dropna().tolist())
        log.info(f"Existing: {len(existing_df):,} trades")

    # Step 1: collect wallet addresses
    wallets = collect_wallet_addresses(max_wallets)

    if not wallets:
        log.error("Could not collect any wallet addresses")
        sys.exit(1)

    # Step 2: fetch per-wallet trade history
    all_records = []
    total = len(wallets)

    for i, addr in enumerate(sorted(wallets), 1):
        if i % 20 == 0:
            log.info(f"[{i}/{total}] {len(all_records):,} trades collected so far")

        trades = fetch_wallet_trades(addr)
        new = 0
        for t in trades:
            record = parse_trade(t)
            if record and record["trade_id"] and record["trade_id"] not in existing_ids:
                all_records.append(record)
                existing_ids.add(record["trade_id"])
                new += 1

        if new > 0:
            log.debug(f"  {addr[:12]}...: {new} new trades")
        time.sleep(0.05)

    log.info(f"Fetched {len(all_records):,} new trades from {total} wallets")

    if not all_records and existing_df.empty:
        log.error("No trades fetched")
        sys.exit(1)

    # Save
    new_df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    combined = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df
    combined = combined.drop_duplicates(subset=["trade_id"]).sort_values("timestamp").reset_index(drop=True)

    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUTPUT_PATH, engine="pyarrow", index=False, compression="snappy")
    log.info(f"Saved {len(combined):,} total trades to {OUTPUT_PATH}")
    common.log_event("fetch_historical", run_id, "complete",
                     new_trades=len(all_records), total=len(combined))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallets", type=int, default=200, help="Max wallets to scan")
    args = parser.parse_args()
    main(max_wallets=args.wallets)
