#!/usr/bin/env python3
"""
Fetches Polymarket wallet rankings directly from the Polygon blockchain via Dune Analytics.
Requires DUNE_API_KEY in .env

Computes realized P&L for every wallet using the CTF Exchange OrderFilled events:
  - BUY: maker spent USDC (makerAssetId = 0) to receive outcome tokens
  - SELL: maker received USDC (takerAssetId = 0) from selling outcome tokens
  - realized_pnl = total_usdc_out - total_usdc_in

Run:
    python dune_fetch.py
    python dune_fetch.py --limit 10000  # fetch top 10k wallets
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
log = logging.getLogger("dune_fetch")

DUNE_API = "https://api.dune.com/api/v1"
RANKINGS_PATH = common.DATA_DIR / "wallet_rankings.parquet"

WALLET_RANKING_SQL = """
WITH buys AS (
    SELECT
        maker AS wallet,
        COUNT(*) AS buy_count,
        SUM(CAST(makerAmountFilled AS DOUBLE) / 1e6) AS usdc_spent,
        AVG(CAST(makerAmountFilled AS DOUBLE) / 1e6) AS avg_buy_size
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE CAST(makerAssetId AS VARCHAR) = '0'
      AND evt_block_time > CURRENT_TIMESTAMP - INTERVAL '90' DAY
    GROUP BY maker
    HAVING COUNT(*) >= 10
       AND SUM(CAST(makerAmountFilled AS DOUBLE) / 1e6) >= 1000
       AND AVG(CAST(makerAmountFilled AS DOUBLE) / 1e6) >= 200
),
sells AS (
    SELECT
        maker AS wallet,
        COUNT(*) AS sell_count,
        SUM(CAST(takerAmountFilled AS DOUBLE) / 1e6) AS usdc_received
    FROM polymarket_polygon.ctfexchange_evt_orderfilled
    WHERE CAST(takerAssetId AS VARCHAR) = '0'
      AND evt_block_time > CURRENT_TIMESTAMP - INTERVAL '90' DAY
    GROUP BY maker
)
SELECT
    b.wallet AS maker_address,
    b.buy_count AS total_trades,
    ROUND(b.usdc_spent, 2) AS total_usdc_in,
    ROUND(COALESCE(s.usdc_received, 0), 2) AS total_usdc_out,
    ROUND(COALESCE(s.usdc_received, 0) - b.usdc_spent, 2) AS total_profit_usdc,
    ROUND(
        (COALESCE(s.usdc_received, 0) - b.usdc_spent)
        / NULLIF(b.usdc_spent, 0) * 100,
        2
    ) AS roi_pct,
    ROUND(b.avg_buy_size, 2) AS avg_position_size_usdc,
    0.0 AS win_rate,
    0 AS resolved_trades,
    0 AS wins,
    0 AS losses
FROM buys b
LEFT JOIN sells s ON b.wallet = s.wallet
ORDER BY COALESCE(s.usdc_received, 0) - b.usdc_spent DESC
LIMIT {limit}
"""

DUNE_QUERY_ID = int(os.getenv("DUNE_QUERY_ID", "7465073"))


def _headers(key: str) -> dict:
    return {"X-Dune-API-Key": key}


def _execute_and_wait(key: str, sql: str) -> str | None:
    h = _headers(key)

    # Update existing query
    r = requests.patch(f"{DUNE_API}/query/{DUNE_QUERY_ID}",
                       headers=h, json={"query_sql": sql, "name": "Polymarket Wallet Rankings"},
                       timeout=30)
    if r.status_code not in (200, 201):
        log.error(f"Query update failed: {r.text[:200]}")
        return None

    # Execute
    r2 = requests.post(f"{DUNE_API}/query/{DUNE_QUERY_ID}/execute",
                       headers=h, json={}, timeout=30)
    if r2.status_code != 200:
        log.error(f"Execution failed: {r2.text[:200]}")
        return None

    exec_id = r2.json().get("execution_id")
    log.info(f"Execution started: {exec_id}")

    # Poll
    for i in range(120):
        time.sleep(5)
        r3 = requests.get(f"{DUNE_API}/execution/{exec_id}/status",
                          headers=h, timeout=15)
        state = r3.json().get("state", "")
        if i % 6 == 0:
            log.info(f"  [{i*5}s] {state}")
        if state == "QUERY_STATE_COMPLETED":
            return exec_id
        elif state == "QUERY_STATE_FAILED":
            log.error(f"Query failed: {r3.json().get('error', {})}")
            return None

    log.error("Query timed out after 10 minutes")
    return None


def _download_results(key: str, exec_id: str) -> list[dict]:
    h = _headers(key)
    all_rows = []
    offset = 0

    while True:
        r = requests.get(f"{DUNE_API}/execution/{exec_id}/results",
                         params={"limit": 1000, "offset": offset},
                         headers=h, timeout=30)
        data = r.json()
        rows = data.get("result", {}).get("rows", [])
        if not rows:
            break
        all_rows.extend(rows)
        total = data.get("result", {}).get("metadata", {}).get("total_row_count", 0)
        log.info(f"  Downloaded {len(all_rows)}/{total} wallets...")
        if len(all_rows) >= total:
            break
        offset += 1000
        time.sleep(0.3)

    return all_rows


def main(limit: int = 5000) -> None:
    common.load_env()
    key = os.getenv("DUNE_API_KEY", "").strip()
    if not common.has_real_value(key):
        raise RuntimeError("DUNE_API_KEY not set in .env")

    run_id = common.new_run_id("dune-fetch")
    common.log_event("dune_fetch", run_id, "start", limit=limit)
    log.info(f"Fetching top {limit:,} Polymarket wallets from Dune blockchain data...")

    sql = WALLET_RANKING_SQL.format(limit=limit)
    exec_id = _execute_and_wait(key, sql)
    if not exec_id:
        sys.exit(1)

    rows = _download_results(key, exec_id)
    if not rows:
        log.error("No results returned")
        sys.exit(1)

    df = pd.DataFrame(rows)
    df["roi_pct"] = pd.to_numeric(df["roi_pct"], errors="coerce").fillna(0)
    df["total_profit_usdc"] = pd.to_numeric(df["total_profit_usdc"], errors="coerce").fillna(0)
    df["avg_position_size_usdc"] = pd.to_numeric(df["avg_position_size_usdc"], errors="coerce").fillna(0)

    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RANKINGS_PATH, index=False)
    log.info(f"Saved {len(df):,} wallet rankings to {RANKINGS_PATH}")

    profitable = df[df["total_profit_usdc"] > 0]
    log.info(f"Profitable wallets: {len(profitable):,} / {len(df):,}")
    log.info(f"Top 5 by P&L:")
    for _, row in df.head(5).iterrows():
        log.info(f"  {row['maker_address'][:14]}... pnl=${row['total_profit_usdc']:,.0f} roi={row['roi_pct']:.0f}%")

    common.log_event("dune_fetch", run_id, "complete", wallets=len(df))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5000, help="Max wallets to fetch")
    args = parser.parse_args()
    main(limit=args.limit)
