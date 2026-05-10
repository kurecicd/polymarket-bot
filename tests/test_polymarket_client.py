"""Tests for polymarket_client.py — pure logic, no network calls."""
import pytest

from polymarket_client import PolymarketClient, USDC_ADDRESS


class TestClassifySubgraphTrade:
    """Tests for BUY/SELL classification from raw subgraph event data."""

    # Raw values use 1e6 scaling for both USDC and outcome tokens
    def _buy_row(self, usdc_raw=500_000_000, shares_raw=1_000_000_000):
        """Default: $500 USDC for 1000 shares → price = 0.50"""
        return {
            "makerAssetId": USDC_ADDRESS,
            "takerAssetId": "0xoutcometoken123",
            "makerAmountFilled": str(usdc_raw),
            "takerAmountFilled": str(shares_raw),
        }

    def _sell_row(self, shares_raw=1_000_000_000, usdc_raw=600_000_000):
        """Default: 1000 shares → $600 USDC → price = 0.60"""
        return {
            "makerAssetId": "0xoutcometoken123",
            "takerAssetId": USDC_ADDRESS,
            "makerAmountFilled": str(shares_raw),
            "takerAmountFilled": str(usdc_raw),
        }

    def test_buy_classification(self):
        # $500 USDC for 1000 shares → price = 0.50
        row = self._buy_row(usdc_raw=500_000_000, shares_raw=1_000_000_000)
        side, token_id, price, size_shares = PolymarketClient.classify_subgraph_trade(row)
        assert side == "BUY"
        assert token_id == "0xoutcometoken123"
        assert price == pytest.approx(0.5, rel=1e-4)
        assert size_shares == pytest.approx(1000.0, rel=1e-4)

    def test_sell_classification(self):
        # 1000 shares → $600 USDC → price = 0.60
        row = self._sell_row(shares_raw=1_000_000_000, usdc_raw=600_000_000)
        side, token_id, price, size_shares = PolymarketClient.classify_subgraph_trade(row)
        assert side == "SELL"
        assert token_id == "0xoutcometoken123"
        assert price == pytest.approx(0.6, rel=1e-4)
        assert size_shares == pytest.approx(1000.0, rel=1e-4)

    def test_buy_price_calculation(self):
        # $250 USDC for 500 shares → price = 0.50
        row = self._buy_row(usdc_raw=250_000_000, shares_raw=500_000_000)
        side, _, price, _ = PolymarketClient.classify_subgraph_trade(row)
        assert side == "BUY"
        assert price == pytest.approx(0.5, rel=1e-4)

    def test_zero_shares_does_not_crash(self):
        row = {
            "makerAssetId": USDC_ADDRESS,
            "takerAssetId": "0xtoken",
            "makerAmountFilled": "1000000",
            "takerAmountFilled": "0",
        }
        side, token_id, price, shares = PolymarketClient.classify_subgraph_trade(row)
        assert price == 0.0
        assert shares == 0.0

    def test_case_insensitive_usdc_address(self):
        row = {
            "makerAssetId": USDC_ADDRESS.upper(),
            "takerAssetId": "0xtoken",
            "makerAmountFilled": "500000000",
            "takerAmountFilled": "1000000000",
        }
        side, _, _, _ = PolymarketClient.classify_subgraph_trade(row)
        assert side == "BUY"

    def test_high_price_near_one(self):
        # $950 USDC for 1000 shares → price = 0.95
        row = self._buy_row(usdc_raw=950_000_000, shares_raw=1_000_000_000)
        _, _, price, _ = PolymarketClient.classify_subgraph_trade(row)
        assert price == pytest.approx(0.95, rel=1e-3)


class TestHoursUntilEnd:
    def test_future_market(self):
        from datetime import datetime, timezone, timedelta
        future = (datetime.now(timezone.utc) + timedelta(hours=100)).isoformat()
        hours = PolymarketClient.hours_until_end(future)
        assert 99 < hours < 101

    def test_past_market(self):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        hours = PolymarketClient.hours_until_end(past)
        assert hours < 0

    def test_z_suffix_handled(self):
        from datetime import datetime, timezone, timedelta
        future = (datetime.now(timezone.utc) + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        hours = PolymarketClient.hours_until_end(future)
        assert 47 < hours < 49
