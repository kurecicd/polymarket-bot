"""Tests for wallet ranking logic."""
import pandas as pd
import pytest

from rank_wallets import compute_wallet_stats


def _make_df(rows):
    return pd.DataFrame(rows, columns=[
        "maker_address", "token_id", "condition_id",
        "side", "price", "size_shares", "usdc_amount", "timestamp",
    ])


class TestComputeWalletStats:

    def test_single_winning_trade(self):
        df = _make_df([
            ("0xalice", "tok1", "cond1", "BUY", 0.5, 1000, 500.0, 1000),
        ])
        resolutions = {"cond1": 1.0}  # YES won
        stats = compute_wallet_stats(df, resolutions)
        row = stats[stats["maker_address"] == "0xalice"].iloc[0]
        assert row["wins"] == 1
        assert row["losses"] == 0
        assert row["win_rate"] == pytest.approx(1.0)
        # Bought 1000 shares at 0.5 = $500 in. Won → 1000 * 1.0 = $1000 settlement
        assert row["total_profit_usdc"] == pytest.approx(500.0, rel=1e-3)

    def test_single_losing_trade(self):
        df = _make_df([
            ("0xbob", "tok2", "cond2", "BUY", 0.6, 500, 300.0, 1000),
        ])
        resolutions = {"cond2": 0.0}  # NO won (this token lost)
        stats = compute_wallet_stats(df, resolutions)
        row = stats[stats["maker_address"] == "0xbob"].iloc[0]
        assert row["wins"] == 0
        assert row["losses"] == 1
        assert row["win_rate"] == 0.0
        assert row["total_profit_usdc"] == pytest.approx(-300.0, rel=1e-3)

    def test_partial_sell_before_resolution(self):
        df = _make_df([
            ("0xcarol", "tok3", "cond3", "BUY", 0.5, 1000, 500.0, 1000),
            ("0xcarol", "tok3", "cond3", "SELL", 0.7, 500, 350.0, 2000),
        ])
        resolutions = {"cond3": 1.0}  # remaining 500 shares settle at 1.0
        stats = compute_wallet_stats(df, resolutions)
        row = stats[stats["maker_address"] == "0xcarol"].iloc[0]
        # In: $500. Out: $350 (sell) + $500 (settlement on 500 shares) = $850
        assert row["total_profit_usdc"] == pytest.approx(350.0, rel=1e-3)

    def test_unresolved_market_excluded_from_win_rate(self):
        df = _make_df([
            ("0xdave", "tok4", "cond4", "BUY", 0.4, 1000, 400.0, 1000),
        ])
        resolutions = {"cond4": None}  # unresolved
        stats = compute_wallet_stats(df, resolutions)
        row = stats[stats["maker_address"] == "0xdave"].iloc[0]
        assert row["resolved_trades"] == 0
        assert row["wins"] == 0
        assert row["win_rate"] == 0.0

    def test_multiple_wallets(self):
        df = _make_df([
            ("0xalice", "tok1", "cond1", "BUY", 0.5, 1000, 500.0, 1000),
            ("0xbob", "tok2", "cond2", "BUY", 0.8, 500, 400.0, 1000),
        ])
        resolutions = {"cond1": 1.0, "cond2": 0.0}
        stats = compute_wallet_stats(df, resolutions)
        assert len(stats) == 2
        alice = stats[stats["maker_address"] == "0xalice"].iloc[0]
        bob = stats[stats["maker_address"] == "0xbob"].iloc[0]
        assert alice["wins"] == 1
        assert bob["losses"] == 1

    def test_empty_dataframe(self):
        df = _make_df([])
        stats = compute_wallet_stats(df, {})
        assert len(stats) == 0

    def test_no_buy_trades_ignored(self):
        df = _make_df([
            ("0xeve", "tok5", "cond5", "SELL", 0.5, 500, 250.0, 1000),
        ])
        resolutions = {"cond5": 1.0}
        stats = compute_wallet_stats(df, resolutions)
        # SELL-only wallet should be excluded (no buy_count)
        assert len(stats) == 0
