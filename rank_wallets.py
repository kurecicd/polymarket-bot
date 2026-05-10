#!/usr/bin/env python3
"""
Reads data/trades_raw.parquet and computes per-wallet performance stats.
Writes data/wallet_rankings.parquet.

Run:
    python rank_wallets.py
"""
import logging
import os
import sys
import time

import pandas as pd
import requests

import common

RAW_PATH = common.DATA_DIR / "trades_raw.parquet"
RANKINGS_PATH = common.DATA_DIR / "wallet_rankings.parquet"

MIN_TRADES = int(os.getenv("POLYMARKET_MIN_TRADE_COUNT", "50"))
MIN_WIN_RATE = float(os.getenv("POLYMARKET_MIN_WIN_RATE", "0.55"))
MIN_AVG_SIZE_USDC = float(os.getenv("POLYMARKET_MIN_AVG_SIZE_USDC", "500"))
GAMMA_BASE = "https://gamma-api.polymarket.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("rank_wallets")


def _fetch_market_resolutions(condition_ids: list[str]) -> dict[str, float | None]:
    """
    Returns {condition_id: resolved_outcome_value} where value is 1.0 (YES won),
    0.0 (NO won), or None (unresolved).
    Batches requests to avoid URL length limits.
    """
    resolutions: dict[str, float | None] = {}
    batch_size = 50
    sess = requests.Session()
    sess.headers["User-Agent"] = "polymarket-whale-bot/1.0"

    for i in range(0, len(condition_ids), batch_size):
        batch = condition_ids[i : i + batch_size]
        try:
            resp = sess.get(
                f"{GAMMA_BASE}/markets",
                params={"condition_ids": ",".join(batch)},
                timeout=20,
            )
            resp.raise_for_status()
            for market in resp.json() or []:
                cid = market.get("conditionId", "")
                outcome_prices = market.get("outcomePrices")
                # outcomePrices is a JSON string like "[1, 0]" or "[0, 1]"
                if outcome_prices:
                    try:
                        import json
                        prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                        # First token price (YES token outcome)
                        resolutions[cid] = float(prices[0]) if prices else None
                    except (ValueError, IndexError, TypeError):
                        resolutions[cid] = None
                else:
                    resolutions[cid] = None
        except requests.RequestException as exc:
            log.warning(f"Failed to fetch resolution batch {i//batch_size}: {exc}")
        time.sleep(0.3)

    return resolutions


def compute_wallet_stats(df: pd.DataFrame, resolutions: dict[str, float | None]) -> pd.DataFrame:
    """Compute per-wallet performance from raw trade records."""
    results = []

    for addr, wallet_df in df.groupby("maker_address"):
        usdc_in_total = 0.0
        usdc_out_total = 0.0
        resolved_trades = 0
        wins = 0
        losses = 0
        buy_count = 0
        markets_traded = set()

        for token_id, token_df in wallet_df.groupby("token_id"):
            buys = token_df[token_df["side"] == "BUY"]
            sells = token_df[token_df["side"] == "SELL"]

            if buys.empty:
                continue

            buy_count += len(buys)
            usdc_in = buys["usdc_amount"].sum()
            usdc_out = sells["usdc_amount"].sum()
            total_bought_shares = buys["size_shares"].sum()
            total_sold_shares = sells["size_shares"].sum()
            remaining_shares = max(0.0, total_bought_shares - total_sold_shares)

            # Find resolution outcome for this token's market
            condition_id = token_df["condition_id"].iloc[0]
            markets_traded.add(condition_id)
            outcome_value = resolutions.get(condition_id)

            if outcome_value is not None:
                # Market resolved — settle remaining shares
                settlement = remaining_shares * outcome_value
                net = usdc_out + settlement - usdc_in
                resolved_trades += 1
                if net > 0:
                    wins += 1
                else:
                    losses += 1
            else:
                # Unresolved — count realized P&L only
                net = usdc_out - usdc_in

            usdc_in_total += usdc_in
            usdc_out_total += usdc_out + (remaining_shares * (outcome_value or 0.0))

        if buy_count == 0:
            continue

        win_rate = wins / resolved_trades if resolved_trades > 0 else 0.0
        total_profit = usdc_out_total - (df[df["maker_address"] == addr]["usdc_amount"]).sum()
        # Simpler: usdc_out_total accumulated above already includes settlements
        total_profit = usdc_out_total - usdc_in_total
        avg_size = usdc_in_total / buy_count if buy_count > 0 else 0.0
        roi_pct = total_profit / usdc_in_total * 100 if usdc_in_total > 0 else 0.0

        last_ts = int(wallet_df["timestamp"].max())

        results.append({
            "maker_address": addr,
            "total_trades": buy_count,
            "resolved_trades": resolved_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 4),
            "total_usdc_in": round(usdc_in_total, 2),
            "total_profit_usdc": round(total_profit, 2),
            "roi_pct": round(roi_pct, 2),
            "avg_position_size_usdc": round(avg_size, 2),
            "markets_traded": len(markets_traded),
            "last_trade_ts": last_ts,
        })

    return pd.DataFrame(results)


def main() -> None:
    common.load_env()
    run_id = common.new_run_id("rank-wallets")
    common.log_event("rank_wallets", run_id, "start")

    if not RAW_PATH.exists():
        log.error(f"Missing {RAW_PATH} — run fetch_historical.py first.")
        sys.exit(1)

    log.info(f"Loading {RAW_PATH} ...")
    df = pd.read_parquet(RAW_PATH)
    log.info(f"Loaded {len(df):,} trades from {df['maker_address'].nunique():,} unique wallets")

    condition_ids = df["condition_id"].dropna().unique().tolist()
    log.info(f"Fetching resolutions for {len(condition_ids):,} markets from Gamma API ...")
    resolutions = _fetch_market_resolutions(condition_ids)
    resolved_count = sum(1 for v in resolutions.values() if v is not None)
    log.info(f"Got resolution data for {resolved_count:,} / {len(condition_ids):,} markets")

    log.info("Computing wallet stats ...")
    stats = compute_wallet_stats(df, resolutions)
    log.info(f"Computed stats for {len(stats):,} wallets")

    # Apply filters
    filtered = stats[
        (stats["resolved_trades"] >= MIN_TRADES) &
        (stats["win_rate"] >= MIN_WIN_RATE) &
        (stats["total_profit_usdc"] > 0) &
        (stats["avg_position_size_usdc"] >= MIN_AVG_SIZE_USDC)
    ].copy()

    filtered = filtered.sort_values(
        ["win_rate", "total_profit_usdc"], ascending=False
    ).reset_index(drop=True)

    log.info(f"After filters: {len(filtered):,} qualifying wallets")

    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    filtered.to_parquet(RANKINGS_PATH, engine="pyarrow", index=False)
    log.info(f"Saved rankings to {RANKINGS_PATH}")

    if not filtered.empty:
        log.info("\nTop 5 wallets:")
        log.info(filtered[["maker_address", "win_rate", "total_profit_usdc", "total_trades"]].head(5).to_string())

    common.log_event("rank_wallets", run_id, "complete", qualifying_wallets=len(filtered))


if __name__ == "__main__":
    main()
