#!/usr/bin/env python3
"""
Reads data/wallet_rankings.parquet and writes runtime/whale_list.json
with the top N wallets to monitor.

Run:
    python select_whales.py
    python select_whales.py --top 30
"""
import argparse
import logging
import os
import sys

import pandas as pd

import common

RANKINGS_PATH = common.DATA_DIR / "wallet_rankings.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("select_whales")


def main(top_n: int | None = None) -> None:
    common.load_env()
    if top_n is None:
        top_n = int(os.getenv("POLYMARKET_WHALE_TOP_N", "20"))

    run_id = common.new_run_id("select-whales")
    common.log_event("select_whales", run_id, "start", top_n=top_n)

    if not RANKINGS_PATH.exists():
        log.error(f"Missing {RANKINGS_PATH} — run rank_wallets.py first.")
        sys.exit(1)

    df = pd.read_parquet(RANKINGS_PATH)
    log.info(f"Loaded {len(df):,} ranked wallets")

    top = df.head(top_n)

    whale_list = []
    for _, row in top.iterrows():
        whale_list.append({
            "address": row["maker_address"],
            "win_rate": float(row["win_rate"]),
            "total_profit_usdc": float(row["total_profit_usdc"]),
            "avg_position_size_usdc": float(row["avg_position_size_usdc"]),
            "total_trades": int(row["total_trades"]),
            "resolved_trades": int(row["resolved_trades"]),
            "roi_pct": float(row["roi_pct"]),
            "selected_at": common.iso_now(),
        })

    payload = {
        "updated_at": common.iso_now(),
        "top_n": top_n,
        "count": len(whale_list),
        "whales": whale_list,
    }

    common.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    common.write_json(common.WHALE_LIST_PATH, payload)
    log.info(f"Wrote {len(whale_list)} whales to {common.WHALE_LIST_PATH}")

    for i, w in enumerate(whale_list[:5], 1):
        log.info(
            f"  #{i} {w['address'][:10]}... "
            f"win_rate={w['win_rate']:.1%} "
            f"profit=${w['total_profit_usdc']:,.0f} "
            f"trades={w['total_trades']}"
        )

    common.log_event("select_whales", run_id, "complete", count=len(whale_list))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=None, help="Number of top wallets to select")
    args = parser.parse_args()
    main(top_n=args.top)
