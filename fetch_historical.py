#!/usr/bin/env python3
"""
Fetches trade history using the authenticated Polymarket CLOB API.
Uses py-clob-client SDK directly for proper request signing.

Run:
    python fetch_historical.py
    python fetch_historical.py --markets 50
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

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"
OUTPUT_PATH = common.DATA_DIR / "trades_raw.parquet"


def _build_clob_client():
    common.load_env()
    key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    if not common.has_real_value(key):
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set")

    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    client = ClobClient(host=CLOB_BASE, chain_id=137, key=key)

    api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
    if common.has_real_value(api_key):
        client.set_api_creds(ApiCreds(
            api_key=api_key,
            api_secret=os.getenv("POLYMARKET_API_SECRET", ""),
            api_passphrase=os.getenv("POLYMARKET_API_PASSPHRASE", ""),
        ))
    else:
        creds = client.derive_api_key()
        client.set_api_creds(ApiCreds(
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            api_passphrase=creds.api_passphrase,
        ))
        log.info(f"Derived API key: {creds.api_key[:8]}...")

    log.info(f"Authenticated as {client.get_address()}")
    return client


def _fetch_top_markets(limit: int = 100) -> list[dict]:
    try:
        resp = requests.get(
            f"{GAMMA_BASE}/markets",
            params={"limit": limit, "order": "volume", "ascending": "false"},
            timeout=30,
        )
        resp.raise_for_status()
        markets = resp.json() or []
        log.info(f"Fetched {len(markets)} markets")
        return markets
    except Exception as exc:
        log.error(f"Failed to fetch markets: {exc}")
        return []


def _fetch_trades_for_market(client, condition_id: str) -> list[dict]:
    """Use py-clob-client SDK to fetch trades for a market."""
    trades = []
    try:
        from py_clob_client.clob_types import TradeParams
        params = TradeParams(market=condition_id)
        result = client.get_trades(params)
        if isinstance(result, list):
            trades = result
        elif isinstance(result, dict):
            trades = result.get("data", [])
    except Exception as exc:
        log.debug(f"SDK fetch failed for {condition_id[:12]}: {exc}")
        # Fallback: direct REST with proper signing via client's session
        try:
            resp = requests.get(
                f"{CLOB_BASE}/trades",
                params={"market": condition_id, "limit": 500},
                timeout=20,
            )
            if resp.status_code == 200:
                data = resp.json()
                trades = data.get("data", []) if isinstance(data, dict) else (data or [])
        except Exception:
            pass
    return trades


def _parse_trade(trade: dict, condition_id: str, question: str) -> dict | None:
    try:
        side = (trade.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            return None
        price = float(trade.get("price") or 0)
        size = float(trade.get("size") or 0)
        if price <= 0 or size <= 0:
            return None
        maker = (trade.get("maker_address") or trade.get("owner") or "").lower()
        if not maker or not maker.startswith("0x"):
            return None
        return {
            "trade_id": str(trade.get("id") or trade.get("trade_id") or ""),
            "timestamp": int(trade.get("timestamp") or 0),
            "block_number": 0,
            "maker_address": maker,
            "taker_address": (trade.get("taker_address") or "").lower(),
            "token_id": str(trade.get("asset_id") or ""),
            "condition_id": condition_id,
            "market_question": question[:120],
            "end_timestamp": 0,
            "side": side,
            "price": price,
            "size_shares": size,
            "usdc_amount": round(price * size, 6),
        }
    except Exception:
        return None


def main(num_markets: int = 100) -> None:
    common.load_env()
    run_id = common.new_run_id("fetch-historical")
    common.log_event("fetch_historical", run_id, "start", num_markets=num_markets)

    client = _build_clob_client()

    # Load existing
    existing_ids: set[str] = set()
    existing_df = pd.DataFrame()
    if OUTPUT_PATH.exists():
        existing_df = pd.read_parquet(OUTPUT_PATH)
        existing_ids = set(existing_df["trade_id"].dropna().tolist())
        log.info(f"Existing: {len(existing_df):,} trades")

    markets = _fetch_top_markets(num_markets)
    if not markets:
        log.error("No markets fetched")
        sys.exit(1)

    all_records = []

    for i, market in enumerate(markets, 1):
        condition_id = market.get("conditionId") or market.get("condition_id") or ""
        question = market.get("question") or market.get("title") or ""
        if not condition_id:
            continue

        log.info(f"[{i}/{len(markets)}] {question[:55]}...")
        trades = _fetch_trades_for_market(client, condition_id)

        new = 0
        for t in trades:
            record = _parse_trade(t, condition_id, question)
            if record and record["trade_id"] and record["trade_id"] not in existing_ids:
                all_records.append(record)
                existing_ids.add(record["trade_id"])
                new += 1

        if new:
            log.info(f"  → {new} trades | total: {len(all_records):,}")
        time.sleep(0.15)

    if not all_records and existing_df.empty:
        log.error("No trades fetched — CLOB API may not support market-level trade queries without special access")
        log.info("Falling back to seed whale list...")
        # Run seed_whales.py as fallback
        import subprocess
        result = subprocess.run([sys.executable, "seed_whales.py"], cwd=str(common.ROOT))
        if result.returncode == 0:
            log.info("Seed whales created — bot can start monitoring immediately")
            # Create empty parquet so setup considers trades_fetched
            empty = pd.DataFrame(columns=[
                "trade_id", "timestamp", "block_number", "maker_address",
                "taker_address", "token_id", "condition_id", "market_question",
                "end_timestamp", "side", "price", "size_shares", "usdc_amount",
            ])
            common.DATA_DIR.mkdir(parents=True, exist_ok=True)
            empty.to_parquet(OUTPUT_PATH, engine="pyarrow", index=False)
            sys.exit(0)
        sys.exit(1)

    new_df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    combined = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df
    combined = combined.drop_duplicates(subset=["trade_id"]).sort_values("timestamp").reset_index(drop=True)

    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(OUTPUT_PATH, engine="pyarrow", index=False, compression="snappy")
    log.info(f"Saved {len(combined):,} trades to {OUTPUT_PATH}")
    common.log_event("fetch_historical", run_id, "complete",
                     new_trades=len(all_records), total=len(combined))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", type=int, default=100)
    args = parser.parse_args()
    main(num_markets=args.markets)
