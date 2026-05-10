#!/usr/bin/env python3
"""
One-time (and incremental) historical trade fetch from the Polymarket subgraph.
Writes data/trades_raw.parquet.

Run:
    python fetch_historical.py           # full load or resume from last block
    python fetch_historical.py --reset   # wipe and restart from block 0
"""
import argparse
import logging
import sys
import time

import pandas as pd

import common
from polymarket_client import PolymarketClient

BATCH_SIZE = 1000
SLEEP_BETWEEN_BATCHES = 0.35  # stay under subgraph rate limits
OUTPUT_PATH = common.DATA_DIR / "trades_raw.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_historical")


def _build_client() -> PolymarketClient:
    common.load_env()
    key = (common.os.getenv("POLYMARKET_PRIVATE_KEY") or "").strip()
    chain_id = int(common.os.getenv("POLYMARKET_CHAIN_ID", "137"))
    if not common.has_real_value(key):
        # Allow fetching subgraph without real key (public endpoint)
        key = "0x" + "0" * 64
    return PolymarketClient(private_key=key, chain_id=chain_id)


def _classify_rows(raw_rows: list[dict]) -> list[dict]:
    records = []
    for row in raw_rows:
        try:
            side, token_id, price, shares = PolymarketClient.classify_subgraph_trade(row)
        except (KeyError, ValueError, ZeroDivisionError):
            continue

        market = row.get("market") or {}
        records.append({
            "trade_id": row["id"],
            "timestamp": int(row.get("timestamp", 0)),
            "block_number": int(row.get("blockNumber", 0)),
            "maker_address": (row.get("maker") or "").lower(),
            "taker_address": (row.get("taker") or "").lower(),
            "token_id": token_id,
            "condition_id": market.get("conditionId", ""),
            "market_question": market.get("question", ""),
            "end_timestamp": int(market.get("endTimestamp") or 0),
            "side": side,
            "price": price,
            "size_shares": shares,
            "usdc_amount": round(price * shares, 6),
        })
    return records


def _last_block(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    return int(df["block_number"].max())


def _load_existing() -> pd.DataFrame:
    if OUTPUT_PATH.exists():
        log.info(f"Loading existing data from {OUTPUT_PATH}")
        return pd.read_parquet(OUTPUT_PATH)
    return pd.DataFrame()


def _save(df: pd.DataFrame) -> None:
    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(subset=["trade_id"])
    df = df.sort_values("block_number").reset_index(drop=True)
    df.to_parquet(OUTPUT_PATH, engine="pyarrow", index=False, compression="snappy")
    log.info(f"Saved {len(df):,} total rows to {OUTPUT_PATH}")


def main(reset: bool = False) -> None:
    client = _build_client()
    run_id = common.new_run_id("fetch-historical")
    common.log_event("fetch_historical", run_id, "start", reset=reset)

    existing_df = pd.DataFrame() if reset else _load_existing()
    start_block = 0 if reset else _last_block(existing_df)
    if start_block > 0:
        # Re-fetch from slightly before last block to catch any missed events
        start_block = max(0, start_block - 10)

    log.info(f"Starting fetch from block {start_block:,} (existing rows: {len(existing_df):,})")

    all_new: list[dict] = []
    total_pages = 0
    consecutive_empty = 0

    while True:
        try:
            raw = client.fetch_trades_batch(min_block=start_block, batch_size=BATCH_SIZE)
        except RuntimeError as exc:
            log.error(f"Subgraph error: {exc}")
            time.sleep(10)
            continue

        if not raw:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                log.info("No more data — fetch complete.")
                break
            time.sleep(2)
            continue

        consecutive_empty = 0
        rows = _classify_rows(raw)
        all_new.extend(rows)
        total_pages += 1

        last_block_in_batch = max(int(r.get("blockNumber", 0)) for r in raw)
        start_block = last_block_in_batch + 1

        if total_pages % 100 == 0:
            log.info(
                f"Page {total_pages:,} | new rows: {len(all_new):,} | "
                f"latest block: {last_block_in_batch:,}"
            )

        # If batch was smaller than BATCH_SIZE, we've reached the tip
        if len(raw) < BATCH_SIZE:
            log.info(f"Partial page ({len(raw)} rows) — reached chain tip.")
            break

        time.sleep(SLEEP_BETWEEN_BATCHES)

    if all_new:
        new_df = pd.DataFrame(all_new)
        combined = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df
        _save(combined)
    else:
        log.info("No new rows fetched.")
        if not existing_df.empty:
            _save(existing_df)

    log.info(f"Done. Total pages fetched: {total_pages:,} | new rows: {len(all_new):,}")
    common.log_event("fetch_historical", run_id, "complete", pages=total_pages, new_rows=len(all_new))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe existing data and restart from block 0")
    args = parser.parse_args()
    try:
        main(reset=args.reset)
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        sys.exit(0)
