#!/usr/bin/env python3
"""
Fetches trade history using the authenticated Polymarket CLOB API.

Strategy:
  1. Get top markets by volume from Gamma API
  2. For each top market, fetch all trades via authenticated CLOB API
  3. Build per-wallet stats from observed trades
  4. Save to data/trades_raw.parquet

Requires POLYMARKET_PRIVATE_KEY in environment.

Run:
    python fetch_historical.py
    python fetch_historical.py --markets 50  # scan top 50 markets
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

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
OUTPUT_PATH = common.DATA_DIR / "trades_raw.parquet"

USDC_ADDRESS = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"


def _get_api_headers() -> dict:
    """Build auth headers from private key using py-clob-client."""
    common.load_env()
    key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
    if not common.has_real_value(key):
        raise RuntimeError("POLYMARKET_PRIVATE_KEY not set")

    try:
        from py_clob_client.client import ClobClient
        client = ClobClient(host=CLOB_BASE, chain_id=137, key=key)

        # Try to get existing API creds from env
        api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
        api_secret = os.getenv("POLYMARKET_API_SECRET", "").strip()
        api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

        if common.has_real_value(api_key):
            from py_clob_client.clob_types import ApiCreds
            client.set_api_creds(ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
            ))
        else:
            log.info("Deriving API key from private key...")
            creds = client.derive_api_key()
            log.info(f"Derived API key: {creds.api_key[:8]}...")
            from py_clob_client.clob_types import ApiCreds
            client.set_api_creds(ApiCreds(
                api_key=creds.api_key,
                api_secret=creds.api_secret,
                api_passphrase=creds.api_passphrase,
            ))

        return {
            "POLY-ADDRESS": client.get_address(),
            "POLY-API-KEY": client.api_creds.api_key,
            "POLY-PASSPHRASE": client.api_creds.api_passphrase,
            "POLY-TIMESTAMP": str(int(time.time())),
            "POLY-SIGNATURE": "",  # will be added per-request
        }
    except Exception as exc:
        log.warning(f"Could not set up CLOB auth: {exc}")
        return {}


def _fetch_top_markets(limit: int = 100) -> list[dict]:
    """Get top markets by volume from Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_BASE}/markets",
            params={
                "limit": limit,
                "order": "volume",
                "ascending": "false",
                "active": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()
        markets = resp.json() or []
        log.info(f"Fetched {len(markets)} markets from Gamma API")
        return markets
    except Exception as exc:
        log.error(f"Failed to fetch markets: {exc}")
        return []


def _fetch_market_trades(condition_id: str, session: requests.Session) -> list[dict]:
    """Fetch all trades for a market via CLOB API."""
    trades = []
    cursor = "MA=="  # initial cursor

    while True:
        try:
            resp = session.get(
                f"{CLOB_BASE}/trades",
                params={
                    "market": condition_id,
                    "limit": 500,
                    "cursor": cursor,
                },
                timeout=20,
            )
            if resp.status_code == 401:
                log.warning("Auth failed — trying without cursor")
                break
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("data") or (data if isinstance(data, list) else [])
            if not batch:
                break

            trades.extend(batch)
            next_cursor = data.get("next_cursor", "")
            if not next_cursor or next_cursor == cursor or next_cursor == "LTE=":
                break
            cursor = next_cursor
            time.sleep(0.1)

        except Exception as exc:
            log.debug(f"Trade fetch error for {condition_id[:12]}: {exc}")
            break

    return trades


def _parse_trade(trade: dict, condition_id: str, market_question: str, end_date: str) -> dict | None:
    """Parse a CLOB trade into our standard format."""
    try:
        side = (trade.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            return None

        price = float(trade.get("price") or 0)
        size = float(trade.get("size") or 0)
        if price <= 0 or size <= 0:
            return None

        maker = (trade.get("maker_address") or trade.get("user_address") or "").lower()
        if not maker or not maker.startswith("0x"):
            return None

        return {
            "trade_id": trade.get("id") or trade.get("trade_id") or "",
            "timestamp": int(trade.get("timestamp") or 0),
            "block_number": 0,
            "maker_address": maker,
            "taker_address": (trade.get("taker_address") or "").lower(),
            "token_id": trade.get("asset_id") or "",
            "condition_id": condition_id,
            "market_question": market_question[:120],
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

    # Set up authenticated session
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "polymarket-whale-bot/1.0",
        "Content-Type": "application/json",
    })

    # Try to add auth headers
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        key = os.getenv("POLYMARKET_PRIVATE_KEY", "").strip()
        clob = ClobClient(host=CLOB_BASE, chain_id=137, key=key)

        api_key = os.getenv("POLYMARKET_API_KEY", "").strip()
        if common.has_real_value(api_key):
            clob.set_api_creds(ApiCreds(
                api_key=api_key,
                api_secret=os.getenv("POLYMARKET_API_SECRET", ""),
                api_passphrase=os.getenv("POLYMARKET_API_PASSPHRASE", ""),
            ))
        else:
            creds = clob.derive_api_key()
            clob.set_api_creds(ApiCreds(
                api_key=creds.api_key,
                api_secret=creds.api_secret,
                api_passphrase=creds.api_passphrase,
            ))
            log.info(f"Derived CLOB API key: {creds.api_key[:8]}...")

        sess.headers["POLY-ADDRESS"] = clob.get_address()
        sess.headers["POLY-API-KEY"] = clob.api_creds.api_key
        sess.headers["POLY-PASSPHRASE"] = clob.api_creds.api_passphrase
        log.info(f"Authenticated as {clob.get_address()}")
    except Exception as exc:
        log.warning(f"Auth setup failed: {exc} — trying unauthenticated")

    # Load existing data if any
    existing_ids: set[str] = set()
    existing_df = pd.DataFrame()
    if OUTPUT_PATH.exists():
        existing_df = pd.read_parquet(OUTPUT_PATH)
        existing_ids = set(existing_df["trade_id"].dropna().tolist())
        log.info(f"Existing data: {len(existing_df):,} trades")

    markets = _fetch_top_markets(num_markets)
    if not markets:
        log.error("No markets fetched")
        sys.exit(1)

    all_records = []
    total_markets = len(markets)

    for i, market in enumerate(markets, 1):
        condition_id = market.get("conditionId") or market.get("condition_id") or ""
        question = market.get("question") or market.get("title") or ""
        end_date = market.get("endDateIso") or market.get("endDate") or ""

        if not condition_id:
            continue

        log.info(f"[{i}/{total_markets}] {question[:50]}...")
        trades = _fetch_market_trades(condition_id, sess)

        new_count = 0
        for t in trades:
            record = _parse_trade(t, condition_id, question, end_date)
            if record and record["trade_id"] not in existing_ids:
                all_records.append(record)
                existing_ids.add(record["trade_id"])
                new_count += 1

        if new_count:
            log.info(f"  → {new_count} new trades (total: {len(all_records):,})")

        time.sleep(0.2)

    if not all_records and existing_df.empty:
        log.error("No trades fetched at all — check auth")
        sys.exit(1)

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
    parser.add_argument("--markets", type=int, default=100, help="Number of top markets to scan")
    args = parser.parse_args()
    main(num_markets=args.markets)
