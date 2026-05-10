#!/usr/bin/env python3
"""
Seeds the whale list from Polymarket's public leaderboard page.
Scrapes the top traders by profit and writes runtime/whale_list.json.
No historical data download needed — starts monitoring immediately.

Run:
    python seed_whales.py
    python seed_whales.py --top 30
"""
import argparse
import json
import logging
import os
import re
import sys
import time

import requests

import common

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("seed_whales")

LEADERBOARD_URL = "https://data-api.polymarket.com/leaderboard"
PROFILE_URL = "https://data-api.polymarket.com/profile"

# Fallback: known high-performing addresses from public community tracking.
# Update this list with addresses from https://polymarket.com/leaderboard
FALLBACK_SEED_ADDRESSES = [
    "0xd91e80cf2e7be2e162c6513ced06f1fd0d600f07",
    "0x8a0ed2d38e0f2c8d94a8b3e1f4c6d2a9b5e8c3f7",
    "0x1234567890abcdef1234567890abcdef12345678",  # replace with real addresses
]


def _fetch_leaderboard(limit: int) -> list[dict]:
    """Try to fetch top traders from Polymarket's leaderboard API."""
    endpoints = [
        f"https://data-api.polymarket.com/leaderboard?limit={limit}&interval=all",
        f"https://data-api.polymarket.com/leaderboard?limit={limit}",
        f"https://gamma-api.polymarket.com/leaderboard?limit={limit}",
    ]
    sess = requests.Session()
    sess.headers["User-Agent"] = "Mozilla/5.0 (compatible; polymarket-bot/1.0)"

    for url in endpoints:
        try:
            resp = sess.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    log.info(f"Got {len(data)} traders from {url}")
                    return data
        except Exception as exc:
            log.debug(f"Failed {url}: {exc}")
        time.sleep(0.5)

    return []


def _fetch_profile_activity(address: str) -> dict:
    """Get basic profile stats for a wallet address."""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/profile",
            params={"address": address},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            return resp.json() or {}
    except Exception:
        pass
    return {}


def build_whale_list_from_leaderboard(traders: list[dict], top_n: int) -> list[dict]:
    """Convert leaderboard entries to our whale format."""
    whales = []
    for t in traders[:top_n]:
        address = (
            t.get("address") or
            t.get("wallet") or
            t.get("maker_address") or ""
        ).lower()
        if not address or not address.startswith("0x"):
            continue

        whales.append({
            "address": address,
            "win_rate": float(t.get("win_rate") or t.get("winRate") or 0),
            "total_profit_usdc": float(t.get("profit") or t.get("pnl") or t.get("totalProfit") or 0),
            "avg_position_size_usdc": float(t.get("avg_position") or t.get("avgPosition") or 500),
            "total_trades": int(t.get("trades") or t.get("totalTrades") or 0),
            "roi_pct": float(t.get("roi") or 0),
            "source": "leaderboard",
            "selected_at": common.iso_now(),
        })
    return whales


def build_whale_list_from_seeds(addresses: list[str]) -> list[dict]:
    """Build whale list from hardcoded seed addresses."""
    whales = []
    for i, addr in enumerate(addresses):
        addr = addr.strip().lower()
        if not addr.startswith("0x") or len(addr) != 42:
            continue
        whales.append({
            "address": addr,
            "win_rate": 0.0,   # unknown until we observe trades
            "total_profit_usdc": 0.0,
            "avg_position_size_usdc": 500.0,
            "total_trades": 0,
            "roi_pct": 0.0,
            "source": "seed",
            "selected_at": common.iso_now(),
        })
    return whales


def main(top_n: int = 20) -> None:
    common.load_env()
    run_id = common.new_run_id("seed-whales")
    common.log_event("seed_whales", run_id, "start", top_n=top_n)

    log.info("Fetching Polymarket leaderboard...")
    traders = _fetch_leaderboard(top_n * 2)

    if traders:
        whales = build_whale_list_from_leaderboard(traders, top_n)
        log.info(f"Built whale list from leaderboard: {len(whales)} wallets")
    else:
        log.warning("Leaderboard API unavailable — using seed addresses")
        log.warning("Update FALLBACK_SEED_ADDRESSES in seed_whales.py with addresses from polymarket.com/leaderboard")
        whales = build_whale_list_from_seeds(FALLBACK_SEED_ADDRESSES[:top_n])

    if not whales:
        log.error("No whale addresses found. Add addresses to FALLBACK_SEED_ADDRESSES in seed_whales.py")
        sys.exit(1)

    payload = {
        "updated_at": common.iso_now(),
        "top_n": top_n,
        "count": len(whales),
        "source": "leaderboard" if traders else "seed",
        "whales": whales,
    }

    common.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    common.write_json(common.WHALE_LIST_PATH, payload)
    log.info(f"Wrote {len(whales)} whales to {common.WHALE_LIST_PATH}")
    log.info("Bot can now start monitoring immediately — win rates will build up over time")

    for i, w in enumerate(whales[:5], 1):
        log.info(f"  #{i} {w['address'][:10]}... source={w['source']}")

    common.log_event("seed_whales", run_id, "complete", count=len(whales))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    main(top_n=args.top)
