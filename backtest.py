#!/usr/bin/env python3
"""
Backtesting — simulates the whale copy strategy on historical data.

Uses data/trades_raw.parquet to replay history:
  1. Loads all trades chronologically
  2. Identifies top whale wallets (same ranking logic as rank_wallets.py)
     but only using data available BEFORE the backtest window
  3. Simulates copying every whale BUY trade in the test window
  4. Applies the same exit conditions (profit target, whale exit, market closing)
  5. Outputs a summary: total return, win rate, avg hold, Sharpe ratio

Run:
    python backtest.py
    python backtest.py --start 2024-01-01 --end 2024-06-01
    python backtest.py --top-n 10 --position-pct 0.03
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import common
from rank_wallets import compute_wallet_stats

RAW_PATH = common.DATA_DIR / "trades_raw.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("backtest")


def _parse_date(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())


def run_backtest(
    start_ts: int,
    end_ts: int,
    top_n: int = 20,
    position_pct: float = 0.02,
    profit_target_pct: float = 0.25,
    whale_shrink_thresh: float = 0.30,
    hours_before_close: float = 72.0,
    initial_balance: float = 1000.0,
) -> dict:
    if not RAW_PATH.exists():
        log.error(f"Missing {RAW_PATH} — run fetch_historical.py first")
        sys.exit(1)

    log.info(f"Loading {RAW_PATH} ...")
    df = pd.read_parquet(RAW_PATH)
    log.info(f"Loaded {len(df):,} trades")

    # Train on data BEFORE backtest window
    train_df = df[df["timestamp"] < start_ts].copy()
    test_df = df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()
    log.info(f"Train: {len(train_df):,} trades  |  Test window: {len(test_df):,} trades")

    if train_df.empty:
        log.error("No training data before start date — use an earlier start date")
        sys.exit(1)

    # Build fake resolutions from test data (use actual final prices)
    # For simplicity: use the final SELL price per token as outcome proxy
    # In real data, resolution comes from Gamma API; here we approximate
    resolutions: dict[str, float | None] = {}
    for cid in train_df["condition_id"].unique():
        token_sells = train_df[
            (train_df["condition_id"] == cid) & (train_df["side"] == "SELL")
        ]["price"]
        if not token_sells.empty:
            last_price = float(token_sells.iloc[-1])
            # If last sell was at >0.95, treat as resolved YES=1
            resolutions[cid] = 1.0 if last_price > 0.95 else (0.0 if last_price < 0.05 else None)
        else:
            resolutions[cid] = None

    log.info("Ranking whale wallets on training data...")
    stats = compute_wallet_stats(train_df, resolutions)
    if stats.empty:
        log.error("No qualifying wallets found in training data")
        sys.exit(1)

    whale_wallets = set(
        stats[
            (stats["resolved_trades"] >= 10) &
            (stats["win_rate"] >= 0.55) &
            (stats["total_profit_usdc"] > 0)
        ].head(top_n)["maker_address"].tolist()
    )
    log.info(f"Selected {len(whale_wallets)} whale wallets for backtest")

    # Simulation
    balance = initial_balance
    open_positions: dict[str, dict] = {}
    closed_trades: list[dict] = []
    test_df_sorted = test_df.sort_values("timestamp")

    for _, row in test_df_sorted.iterrows():
        ts = int(row["timestamp"])

        # Check exits on open positions at this timestamp
        for pos_id, pos in list(open_positions.items()):
            current_price = row["price"] if row["token_id"] == pos["token_id"] else pos["entry_price"]
            profit_target = pos["entry_price"] * (1 + profit_target_pct)
            end_ts_pos = int(pos.get("end_timestamp", end_ts + 1))
            hours_left = (end_ts_pos - ts) / 3600

            # Check whale selling
            whale_sell = (
                row["maker_address"] == pos["whale_address"]
                and row["token_id"] == pos["token_id"]
                and row["side"] == "SELL"
                and int(row.get("size_shares", 0)) / max(pos["whale_entry_shares"], 1) >= whale_shrink_thresh
            )

            exit_reason = None
            exit_price = current_price
            if current_price >= profit_target:
                exit_reason = "profit_target"
                exit_price = profit_target
            elif whale_sell:
                exit_reason = "whale_exiting"
            elif hours_left <= hours_before_close:
                exit_reason = "market_closing_soon"

            if exit_reason:
                pnl = (exit_price - pos["entry_price"]) * pos["size_shares"]
                balance += pos["size_usdc"] + pnl
                closed_trades.append({
                    "position_id": pos_id,
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "size_usdc": pos["size_usdc"],
                    "size_shares": pos["size_shares"],
                    "pnl": round(pnl, 4),
                    "pnl_pct": round(pnl / pos["size_usdc"] * 100, 2),
                    "exit_reason": exit_reason,
                    "hold_hours": round((ts - pos["opened_at_ts"]) / 3600, 1),
                })
                del open_positions[pos_id]

        # Check if this row is a whale signal
        if (
            row["maker_address"] in whale_wallets
            and row["side"] == "BUY"
            and row["price"] > 0.02
            and row["price"] < 0.98
        ):
            token_id = row["token_id"]
            # Not already holding this token
            if any(p["token_id"] == token_id for p in open_positions.values()):
                continue
            # Max 10 concurrent positions
            if len(open_positions) >= 10:
                continue

            size_usdc = balance * position_pct
            if size_usdc < 1:
                continue
            size_shares = size_usdc / row["price"]
            balance -= size_usdc

            pos_id = f"{token_id[:12]}-{ts}"
            open_positions[pos_id] = {
                "token_id": token_id,
                "condition_id": row["condition_id"],
                "whale_address": row["maker_address"],
                "entry_price": row["price"],
                "size_usdc": size_usdc,
                "size_shares": size_shares,
                "whale_entry_shares": row["size_shares"],
                "opened_at_ts": ts,
                "end_timestamp": row.get("end_timestamp", end_ts + 86400 * 30),
            }

    # Force-close remaining positions at end of test window
    for pos_id, pos in open_positions.items():
        closed_trades.append({
            "position_id": pos_id,
            "entry_price": pos["entry_price"],
            "exit_price": pos["entry_price"],  # assume flat
            "size_usdc": pos["size_usdc"],
            "size_shares": pos["size_shares"],
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "exit_reason": "end_of_backtest",
            "hold_hours": round((end_ts - pos["opened_at_ts"]) / 3600, 1),
        })
        balance += pos["size_usdc"]

    # Summary stats
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in closed_trades)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    avg_hold = sum(t["hold_hours"] for t in closed_trades) / total_trades if total_trades else 0.0
    total_return_pct = (balance - initial_balance) / initial_balance * 100

    summary = {
        "start": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_hold_hours": round(avg_hold, 1),
        "whale_wallets_used": len(whale_wallets),
        "position_pct": position_pct,
    }
    return summary, closed_trades


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-01", help="Backtest start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-07-01", help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--position-pct", type=float, default=0.02)
    parser.add_argument("--balance", type=float, default=1000.0)
    args = parser.parse_args()

    start_ts = _parse_date(args.start)
    end_ts = _parse_date(args.end)

    log.info(f"Running backtest: {args.start} → {args.end}")
    summary, trades = run_backtest(
        start_ts=start_ts,
        end_ts=end_ts,
        top_n=args.top_n,
        position_pct=args.position_pct,
        initial_balance=args.balance,
    )

    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    for k, v in summary.items():
        print(f"  {k:<25} {v}")
    print("=" * 50)

    out_path = common.DATA_DIR / "backtest_results.json"
    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        json.dump({"summary": summary, "trades": trades}, fh, indent=2)
    log.info(f"Full results saved to {out_path}")


if __name__ == "__main__":
    main()
