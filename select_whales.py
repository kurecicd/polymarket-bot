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
        top_n = int(os.getenv("POLYMARKET_WHALE_TOP_N", "40"))

    run_id = common.new_run_id("select-whales")
    common.log_event("select_whales", run_id, "start", top_n=top_n)

    if not RANKINGS_PATH.exists():
        log.error(f"Missing {RANKINGS_PATH} — run rank_wallets.py first.")
        sys.exit(1)

    import requests as _req

    def _pusd_balance(address: str) -> float:
        PUSD = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
        data = "0x70a08231000000000000000000000000" + address.lower().removeprefix("0x")
        try:
            r = _req.post("https://polygon-bor-rpc.publicnode.com", json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": PUSD, "data": data}, "latest"], "id": 1,
            }, timeout=5)
            return int(r.json().get("result", "0x0"), 16) / 1e6
        except Exception:
            return 0.0

    df = pd.read_parquet(RANKINGS_PATH)
    log.info(f"Loaded {len(df):,} ranked wallets")

    top = df.head(top_n)

    def _category_breakdown(address: str) -> dict:
        """Fetch recent trades and compute category % breakdown."""
        try:
            r = _req.get("https://data-api.polymarket.com/trades",
                         params={"user": address, "limit": 100}, timeout=8)
            trades = r.json() if isinstance(r.json(), list) else []
            if not trades:
                return {}
            # Classify by keywords in title
            cats: dict[str, int] = {}
            for t in trades:
                title = (t.get("title") or "").lower()
                if any(k in title for k in ["bitcoin", "eth", "crypto", "btc", "sol", "doge", "xrp"]):
                    cat = "Crypto"
                elif any(k in title for k in ["trump", "biden", "president", "election", "vote", "congress", "senate", "democrat", "republican"]):
                    cat = "Politics"
                elif any(k in title for k in ["nba", "nfl", "soccer", "football", "basketball", "baseball", "tennis", "golf", "ufc", "mma"]):
                    cat = "Sports"
                elif any(k in title for k in ["ai ", "openai", "gpt", "tech", "apple", "google", "meta", "microsoft"]):
                    cat = "Tech"
                else:
                    cat = "Other"
                cats[cat] = cats.get(cat, 0) + 1
            total = sum(cats.values())
            return {k: round(v / total * 100) for k, v in sorted(cats.items(), key=lambda x: -x[1])}
        except Exception:
            return {}

    whale_list = []
    for i, (_, row) in enumerate(top.iterrows()):
        addr = row["maker_address"]
        balance = _pusd_balance(addr)
        categories = _category_breakdown(addr)
        if i % 10 == 0:
            log.info(f"Fetching data... {i}/{len(top)}")
        whale_list.append({
            "address": addr,
            "win_rate": None,  # not derivable from CTF exchange events; use roi_pct instead
            "total_profit_usdc": float(row["total_profit_usdc"]),
            "avg_position_size_usdc": float(row["avg_position_size_usdc"]),
            "total_trades": int(row["total_trades"]),
            "resolved_trades": int(row["resolved_trades"]),
            "roi_pct": float(row["roi_pct"]),
            "balance_usdc": balance,
            "categories": categories,
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
